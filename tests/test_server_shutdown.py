#!/usr/bin/env python3
"""Verify server SIGINT/SIGTERM shutdown does not deadlock and exits promptly."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


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


def free_tcp_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TestServerShutdown(unittest.TestCase):
    def test_sigint_shuts_down_within_five_seconds(self) -> None:
        port = free_tcp_port()
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "server" / "server.py")],
            env={**os.environ, "PORT_SCANNER_LISTEN_PORT": str(port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(0.8)
            started = time.monotonic()
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=5)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 5.0, f"shutdown took {elapsed:.2f}s")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)

    def test_managed_ctl_stop_is_prompt(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            port = str(free_tcp_port())
            env = {
                "PORT_SCANNER_STATE_DIR": tmp,
                "PORT_SCANNER_LISTEN_PORT": port,
                "PORT_SCANNER_LISTEN_HOST": "127.0.0.1",
                "PORT_SCANNER_START_TIMEOUT": "15",
                "PORT_SCANNER_STOP_TIMEOUT": "15",
            }
            self.assertEqual(run_script("port_scanner_ctl.sh", "init", env=env).returncode, 0)
            self.assertEqual(run_script("port_scanner_ctl.sh", "start", env=env).returncode, 0)
            started = time.monotonic()
            stop = run_script("port_scanner_ctl.sh", "stop", env=env)
            elapsed = time.monotonic() - started
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertLess(elapsed, 8.0, f"ctl stop took {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
