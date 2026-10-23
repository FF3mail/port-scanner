#!/usr/bin/env python3
"""Regression tests for PORT_SCANNER_LISTEN_HOST socket binding."""

from __future__ import annotations

import http.server
import importlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SERVER_DIR = ROOT / "server"
SERVER_PY = SERVER_DIR / "server.py"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def free_tcp_port() -> int:
    import socket

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


def reload_server_module(env_patch: dict[str, str]):
    for key, value in env_patch.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    import server as server_mod

    return importlib.reload(server_mod)


def bind_address_from_module(server_mod, port: int) -> str:
    httpd = http.server.HTTPServer((server_mod.LISTEN_HOST, port), server_mod.ScanRequestHandler)
    try:
        host = httpd.server_address[0]
        return host if host else "0.0.0.0"
    finally:
        httpd.server_close()


def assert_loopback_only(reported_host: str) -> None:
    if reported_host != "127.0.0.1":
        raise AssertionError(f"expected loopback bind 127.0.0.1, got {reported_host}")


def stop_server_subprocess(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def listening_local_addresses(port: int) -> set[str]:
    """Parse ss -ltn for listeners on port (Linux)."""
    if shutil.which("ss") is None:
        raise unittest.SkipTest("ss not available")
    proc = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, check=False)
    hosts: set[str] = set()
    for line in proc.stdout.splitlines():
        if f":{port}" not in line:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        if ":" not in local:
            continue
        host, _, port_part = local.rpartition(":")
        if port_part != str(port):
            continue
        hosts.add(host if host else "0.0.0.0")
    return hosts


class TestParseListenHost(unittest.TestCase):
    def test_defaults(self) -> None:
        import server as server_mod

        self.assertEqual(server_mod.parse_listen_host(""), "")
        self.assertEqual(server_mod.parse_listen_host("0.0.0.0"), "")

    def test_loopback(self) -> None:
        import server as server_mod

        self.assertEqual(server_mod.parse_listen_host("127.0.0.1"), "127.0.0.1")

    def test_invalid_raises(self) -> None:
        import server as server_mod

        with self.assertRaises(ValueError):
            server_mod.parse_listen_host("not-an-ip")


class TestListenBindSocket(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("PORT_SCANNER_LISTEN_HOST", None)

    def test_loopback_bind(self) -> None:
        port = free_tcp_port()
        server_mod = reload_server_module({"PORT_SCANNER_LISTEN_HOST": "127.0.0.1"})
        self.assertEqual(bind_address_from_module(server_mod, port), "127.0.0.1")

    def test_all_interfaces_unset(self) -> None:
        port = free_tcp_port()
        server_mod = reload_server_module({"PORT_SCANNER_LISTEN_HOST": None})
        self.assertEqual(bind_address_from_module(server_mod, port), "0.0.0.0")

    def test_all_interfaces_explicit_zero(self) -> None:
        port = free_tcp_port()
        server_mod = reload_server_module({"PORT_SCANNER_LISTEN_HOST": "0.0.0.0"})
        self.assertEqual(bind_address_from_module(server_mod, port), "0.0.0.0")

    def test_invalid_host_exits_on_reload(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os, sys, importlib; "
                f"sys.path.insert(0, r'{SERVER_DIR}'); "
                "os.environ['PORT_SCANNER_LISTEN_HOST']='bad-host'; "
                "import server as m; importlib.reload(m)",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Invalid PORT_SCANNER_LISTEN_HOST", proc.stderr)

    def test_invalid_host_no_listener(self) -> None:
        port = free_tcp_port()
        proc = subprocess.Popen(
            [sys.executable, str(SERVER_PY)],
            cwd=ROOT,
            env={**os.environ, "PORT_SCANNER_LISTEN_HOST": "not-valid", "PORT_SCANNER_LISTEN_PORT": str(port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            proc.wait(timeout=3)
            self.assertNotEqual(proc.returncode, 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)
        if shutil.which("ss"):
            self.assertNotIn(f":{port}", subprocess.check_output(["ss", "-ltn"], text=True))

    def test_loopback_assertion_rejects_all_interfaces(self) -> None:
        with self.assertRaises(AssertionError):
            assert_loopback_only("0.0.0.0")


class TestManagedCtlBindHost(unittest.TestCase):
    def test_ctl_start_passes_listen_host(self) -> None:
        if shutil.which("bash") is None:
            self.skipTest("bash not available")
        if shutil.which("ss") is None:
            self.skipTest("ss not available (socket bind verification)")

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
            start = run_script("port_scanner_ctl.sh", "start", env=env)
            self.assertEqual(start.returncode, 0, start.stderr)
            try:
                hosts = listening_local_addresses(int(port))
                self.assertIn("127.0.0.1", hosts)
                self.assertNotIn("0.0.0.0", hosts)
            finally:
                run_script("port_scanner_ctl.sh", "stop", env=env)


class TestIntegrationDynamicPort(unittest.TestCase):
    def test_integration_check_on_dynamic_port(self) -> None:
        port = free_tcp_port()
        env = {
            **os.environ,
            "PORT_SCANNER_LISTEN_HOST": "127.0.0.1",
            "PORT_SCANNER_LISTEN_PORT": str(port),
            "SECRET_TOKEN": "my_secret_123",
        }
        proc = subprocess.Popen(
            [sys.executable, str(SERVER_PY)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 10
            import socket

            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                self.fail("server did not become ready")
            check = subprocess.run(
                [sys.executable, str(SCRIPTS / "integration_check.py")],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        finally:
            stop_server_subprocess(proc)


if __name__ == "__main__":
    unittest.main()
