#!/usr/bin/env python3
"""Tests for scripts/port_scanner_runtime.py (no production SSH or external hosts)."""

from __future__ import annotations

import os
import stat
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import port_scanner_runtime as runtime  # noqa: E402


class TestSecretFile(unittest.TestCase):
    def test_generate_secret_length(self) -> None:
        secret = runtime.generate_master_secret()
        self.assertEqual(len(secret), 64)

    def test_atomic_write_and_permissions(self) -> None:
        with tempfile_dir() as tmp:
            path = tmp / "secret.env"
            runtime.write_secret_file_atomic(path, "test_secret_value_abc")
            self.assertTrue(path.is_file())
            mode = path.stat().st_mode & 0o777
            self.assertLessEqual(mode, 0o600)
            self.assertEqual(runtime.read_secret_file(path), "test_secret_value_abc")

    def test_validate_master_secret_rejects_whitespace(self) -> None:
        with self.assertRaises(ValueError):
            runtime.validate_master_secret_value("bad secret")

    def test_validate_master_secret_rejects_hash(self) -> None:
        with self.assertRaises(ValueError):
            runtime.validate_master_secret_value("secret#comment")

    def test_validate_master_secret_accepts_hex(self) -> None:
        runtime.validate_master_secret_value(runtime.generate_master_secret())

    def test_malformed_secret_file(self) -> None:
        with tempfile_dir() as tmp:
            path = tmp / "bad.env"
            path.write_text("NOT_SECRET=1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                runtime.read_secret_file(path)

    def test_assert_permissions_rejects_world_readable(self) -> None:
        with tempfile_dir() as tmp:
            path = tmp / "secret.env"
            runtime.write_secret_file_atomic(path, "x")
            path.chmod(0o644)
            with self.assertRaises(PermissionError):
                runtime.assert_secret_file_permissions(path)


class TestAuthHelpers(unittest.TestCase):
    def test_bearer_matches_server_module(self) -> None:
        import importlib

        server_dir = ROOT / "server"
        sys.path.insert(0, str(server_dir))
        import server as server_mod  # noqa: E402

        secret = "rotation_test_secret"
        token = runtime.bearer_token_for_secret(secret, unix_seconds=1_000_000)
        expected = server_mod.generate_time_limited_token(secret, unix_timestamp=1_000_000)
        self.assertEqual(token, expected)

    def test_resolve_integration_secret_default(self) -> None:
        old = os.environ.pop("SECRET_TOKEN", None)
        try:
            self.assertEqual(runtime.resolve_integration_secret(), runtime.DEMO_SECRET_TOKEN)
        finally:
            if old is not None:
                os.environ["SECRET_TOKEN"] = old

    def test_resolve_integration_secret_env(self) -> None:
        os.environ["SECRET_TOKEN"] = "from_env"
        try:
            self.assertEqual(runtime.resolve_integration_secret(), "from_env")
        finally:
            os.environ.pop("SECRET_TOKEN", None)


class TestWaitForPort(unittest.TestCase):
    def test_wait_for_closed_port_times_out(self) -> None:
        ok = runtime.wait_for_tcp_port("127.0.0.1", 1, timeout_seconds=0.5)
        self.assertFalse(ok)


class tempfile_dir:
    def __enter__(self) -> Path:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name)

    def __exit__(self, *args) -> None:
        self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
