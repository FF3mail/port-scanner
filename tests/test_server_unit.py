#!/usr/bin/env python3
"""
Unit tests for pure helpers in server/server.py.
No live server or network required.

Run:
  python -m pytest tests/ -q
  # or:
  python scripts/test_server_unit.py
"""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as server_mod  # noqa: E402


class TestTokenWindows(unittest.TestCase):
    def test_window_id_stable_within_window(self) -> None:
        # WINDOW = 21600 seconds
        base = 10 * server_mod.TOKEN_VALIDITY_SECONDS
        self.assertEqual(server_mod._token_window_id(base), 10)
        self.assertEqual(server_mod._token_window_id(base + 1), 10)
        self.assertEqual(
            server_mod._token_window_id(base + server_mod.TOKEN_VALIDITY_SECONDS - 1),
            10,
        )
        self.assertEqual(
            server_mod._token_window_id(base + server_mod.TOKEN_VALIDITY_SECONDS),
            11,
        )

    def test_generate_time_limited_token_matches_sha256(self) -> None:
        secret = "my_secret_123"
        window_id = 42
        expected = hashlib.sha256(f"{secret}:{window_id}".encode("utf-8")).hexdigest()
        actual = server_mod.generate_time_limited_token(secret, window_id=window_id)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 64)
        self.assertEqual(actual, actual.lower())

    def test_generate_token_from_timestamp_uses_window(self) -> None:
        secret = "demo"
        ts = 5 * server_mod.TOKEN_VALIDITY_SECONDS + 100
        token = server_mod.generate_time_limited_token(secret, unix_timestamp=ts)
        expected = server_mod.generate_time_limited_token(secret, window_id=5)
        self.assertEqual(token, expected)


class TestAcceptedBearerTokens(unittest.TestCase):
    def test_accepts_current_and_previous_window(self) -> None:
        secret = "my_secret_123"
        ts = 20 * server_mod.TOKEN_VALIDITY_SECONDS + 50
        accepted = server_mod._accepted_bearer_tokens(secret, unix_timestamp=ts)
        current = server_mod.generate_time_limited_token(secret, window_id=20)
        previous = server_mod.generate_time_limited_token(secret, window_id=19)
        older = server_mod.generate_time_limited_token(secret, window_id=18)
        self.assertEqual(accepted, frozenset({current, previous}))
        self.assertIn(current, accepted)
        self.assertIn(previous, accepted)
        self.assertNotIn(older, accepted)


class TestIsValidPort(unittest.TestCase):
    def test_bool_rejected(self) -> None:
        self.assertFalse(server_mod._is_valid_port(True))
        self.assertFalse(server_mod._is_valid_port(False))

    def test_out_of_range_invalid(self) -> None:
        self.assertFalse(server_mod._is_valid_port(0))
        self.assertFalse(server_mod._is_valid_port(65536))
        self.assertFalse(server_mod._is_valid_port(-1))

    def test_boundaries_valid(self) -> None:
        self.assertTrue(server_mod._is_valid_port(1))
        self.assertTrue(server_mod._is_valid_port(65535))
        self.assertTrue(server_mod._is_valid_port(80))

    def test_non_int_invalid(self) -> None:
        self.assertFalse(server_mod._is_valid_port("80"))
        self.assertFalse(server_mod._is_valid_port(80.0))
        self.assertFalse(server_mod._is_valid_port(None))


class TestValidatePortsPayload(unittest.TestCase):
    def test_valid_list(self) -> None:
        ports, err = server_mod.validate_ports_payload({"ports": [22, 80, 443]})
        self.assertIsNone(err)
        self.assertEqual(ports, [22, 80, 443])

    def test_missing_ports(self) -> None:
        ports, err = server_mod.validate_ports_payload({})
        self.assertIsNone(ports)
        self.assertEqual(err, "Missing ports field")

    def test_empty_list(self) -> None:
        ports, err = server_mod.validate_ports_payload({"ports": []})
        self.assertIsNone(ports)
        self.assertEqual(err, "ports must not be empty")

    def test_not_a_list(self) -> None:
        ports, err = server_mod.validate_ports_payload({"ports": 22})
        self.assertIsNone(ports)
        self.assertEqual(err, "ports must be a list")

    def test_too_many_ports(self) -> None:
        ports, err = server_mod.validate_ports_payload(
            {"ports": list(range(1, server_mod.MAX_PORTS + 2))}
        )
        self.assertIsNone(ports)
        self.assertIn("Too many ports", err or "")

    def test_invalid_port_value(self) -> None:
        ports, err = server_mod.validate_ports_payload({"ports": [80, True]})
        self.assertIsNone(ports)
        self.assertEqual(err, "Each port must be an integer from 1 to 65535")

    def test_host_key_ignored(self) -> None:
        ports, err = server_mod.validate_ports_payload(
            {"host": "evil.example", "ports": [443]}
        )
        self.assertIsNone(err)
        self.assertEqual(ports, [443])


class TestListenPortEnv(unittest.TestCase):
    def test_listen_port_from_env(self) -> None:
        old = os.environ.get("PORT_SCANNER_LISTEN_PORT")
        os.environ["PORT_SCANNER_LISTEN_PORT"] = "9090"
        try:
            importlib.reload(server_mod)
            self.assertEqual(server_mod.LISTEN_PORT, 9090)
        finally:
            if old is None:
                os.environ.pop("PORT_SCANNER_LISTEN_PORT", None)
            else:
                os.environ["PORT_SCANNER_LISTEN_PORT"] = old
            importlib.reload(server_mod)


class TestSecretTokenEnv(unittest.TestCase):
    def test_default_when_env_unset(self) -> None:
        # Module already imported; default demo secret must remain when env was unset
        # at import. Re-import with env cleared to verify preference logic.
        old = os.environ.pop("SECRET_TOKEN", None)
        try:
            importlib.reload(server_mod)
            self.assertEqual(server_mod.SECRET_TOKEN, "my_secret_123")
        finally:
            if old is not None:
                os.environ["SECRET_TOKEN"] = old
            importlib.reload(server_mod)

    def test_env_overrides_default(self) -> None:
        old = os.environ.get("SECRET_TOKEN")
        os.environ["SECRET_TOKEN"] = "production_override_secret"
        try:
            importlib.reload(server_mod)
            self.assertEqual(server_mod.SECRET_TOKEN, "production_override_secret")
        finally:
            if old is None:
                os.environ.pop("SECRET_TOKEN", None)
            else:
                os.environ["SECRET_TOKEN"] = old
            importlib.reload(server_mod)


if __name__ == "__main__":
    unittest.main()
