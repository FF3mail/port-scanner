#!/usr/bin/env python3
"""Integration tests for manual deployment and secret rotation (isolated temp state)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import port_scanner_runtime as runtime  # noqa: E402


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_script(name: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPTS / name), *args],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


class RotateSecretTokenTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name)
        self.port = str(free_tcp_port())
        self.env = {
            "PORT_SCANNER_STATE_DIR": str(self.state_dir),
            "PORT_SCANNER_LISTEN_PORT": self.port,
            "PORT_SCANNER_LISTEN_HOST": "127.0.0.1",
            "PORT_SCANNER_START_TIMEOUT": "15",
            "PORT_SCANNER_STOP_TIMEOUT": "15",
        }

    def tearDown(self) -> None:
        stop = run_script("port_scanner_ctl.sh", "stop", env=self.env)
        self._tmp.cleanup()

    def test_init_refuses_demo_secret_on_start(self) -> None:
        secret_file = self.state_dir / "secret.env"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        runtime.write_secret_file_atomic(secret_file, runtime.DEMO_SECRET_TOKEN)
        result = run_script("port_scanner_ctl.sh", "start", env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("demo secret", result.stderr.lower())

    def test_full_rotation_success(self) -> None:
        init = run_script("port_scanner_ctl.sh", "init", env=self.env)
        self.assertEqual(init.returncode, 0, init.stderr)
        start = run_script("port_scanner_ctl.sh", "start", env=self.env)
        self.assertEqual(start.returncode, 0, start.stderr + start.stdout)

        backup_before = runtime.read_secret_file(self.state_dir / "secret.env")
        rotate = run_script("rotate_secret_token.sh", env=self.env)
        self.assertEqual(rotate.returncode, 0, rotate.stderr + rotate.stdout)

        new_secret = runtime.read_secret_file(self.state_dir / "secret.env")
        self.assertNotEqual(backup_before, new_secret)

        status = runtime.post_scan_status("127.0.0.1", int(self.port), new_secret)
        self.assertEqual(status, 200)
        old_status = runtime.post_scan_status("127.0.0.1", int(self.port), backup_before)
        self.assertEqual(old_status, 401)

    def test_invalid_custom_secret_leaves_server_unchanged(self) -> None:
        run_script("port_scanner_ctl.sh", "init", env=self.env)
        run_script("port_scanner_ctl.sh", "start", env=self.env)
        original = runtime.read_secret_file(self.state_dir / "secret.env")

        bad_env = {**self.env, "PORT_SCANNER_TEST_CUSTOM_SECRET": "invalid secret value"}
        rotate = run_script("rotate_secret_token.sh", "--custom", env=bad_env)
        self.assertNotEqual(rotate.returncode, 0)
        self.assertIn("invalid", rotate.stderr.lower())

        self.assertEqual(runtime.read_secret_file(self.state_dir / "secret.env"), original)
        self.assertEqual(run_script("port_scanner_ctl.sh", "status", env=self.env).returncode, 0)
        self.assertEqual(
            runtime.post_scan_status("127.0.0.1", int(self.port), original),
            200,
        )

    def test_valid_custom_secret_rotation(self) -> None:
        run_script("port_scanner_ctl.sh", "init", env=self.env)
        run_script("port_scanner_ctl.sh", "start", env=self.env)
        original = runtime.read_secret_file(self.state_dir / "secret.env")
        custom = "CustomMasterSecretForRotationTest99"

        rotate = run_script(
            "rotate_secret_token.sh",
            env={**self.env, "PORT_SCANNER_TEST_CUSTOM_SECRET": custom},
        )
        self.assertEqual(rotate.returncode, 0, rotate.stderr + rotate.stdout)
        self.assertEqual(runtime.read_secret_file(self.state_dir / "secret.env"), custom)
        self.assertEqual(runtime.post_scan_status("127.0.0.1", int(self.port), custom), 200)
        self.assertEqual(runtime.post_scan_status("127.0.0.1", int(self.port), original), 401)

    def test_rotate_fails_when_server_not_running(self) -> None:
        run_script("port_scanner_ctl.sh", "init", env=self.env)
        result = run_script("rotate_secret_token.sh", env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not running", result.stderr.lower())

    def test_stop_refuses_unrelated_pid(self) -> None:
        run_script("port_scanner_ctl.sh", "init", env=self.env)
        run_script("port_scanner_ctl.sh", "start", env=self.env)
        pid_file = self.state_dir / "server.pid"
        run_script("port_scanner_ctl.sh", "stop", env=self.env)

        # Plant unrelated PID (sleep) in pid file.
        sleeper = subprocess.Popen(["sleep", "300"], cwd=ROOT)
        try:
            pid_file.write_text(str(sleeper.pid), encoding="utf-8")
            stop = run_script("port_scanner_ctl.sh", "stop", env=self.env)
            self.assertNotEqual(stop.returncode, 0)
            self.assertIn("not the managed", stop.stderr.lower())
        finally:
            sleeper.terminate()
            sleeper.wait(timeout=5)
            pid_file.unlink(missing_ok=True)

    def test_rollback_on_verify_failure(self) -> None:
        run_script("port_scanner_ctl.sh", "init", env=self.env)
        run_script("port_scanner_ctl.sh", "start", env=self.env)
        original = runtime.read_secret_file(self.state_dir / "secret.env")

        fail_env = {**self.env, "PORT_SCANNER_TEST_VERIFY_FAIL": "1"}
        rotate = run_script("rotate_secret_token.sh", env=fail_env)
        self.assertNotEqual(rotate.returncode, 0)
        self.assertIn("rollback", rotate.stderr.lower())

        restored = runtime.read_secret_file(self.state_dir / "secret.env")
        self.assertEqual(restored, original)
        status = run_script("port_scanner_ctl.sh", "status", env=self.env)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(
            runtime.post_scan_status("127.0.0.1", int(self.port), original),
            200,
        )


if __name__ == "__main__":
    unittest.main()
