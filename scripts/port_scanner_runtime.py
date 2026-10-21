#!/usr/bin/env python3
"""
Shared helpers for Linux manual deployment and SECRET_TOKEN rotation.
No secrets are logged or printed by these functions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

DEMO_SECRET_TOKEN = "my_secret_123"
TOKEN_VALIDITY_SECONDS = 6 * 3600
SECRET_LINE_RE = re.compile(r"^SECRET_TOKEN=([^\s#]+)\s*$")
MASTER_SECRET_VALUE_RE = re.compile(r"^[^\s#]+$")


def validate_master_secret_value(secret: str) -> None:
    """
    Validate a master secret before persistence or server stop during rotation.
    Must match the SECRET_TOKEN= single-line file format (no whitespace or #).
    """
    if not secret:
        raise ValueError("Master secret must not be empty")
    if "\n" in secret or "\r" in secret:
        raise ValueError("Master secret must be a single line")
    if not MASTER_SECRET_VALUE_RE.fullmatch(secret):
        raise ValueError(
            "Master secret must not contain whitespace or # (see server/DEPLOY_LINUX.md)"
        )


def generate_master_secret() -> str:
    """Cryptographically strong master secret (URL-safe hex)."""
    return secrets.token_hex(32)


def read_secret_file(path: Path) -> str:
    """Read SECRET_TOKEN from a single-line env file. Raises ValueError on malformed input."""
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = SECRET_LINE_RE.match(stripped)
        if match:
            return match.group(1)
        raise ValueError(f"Malformed secret file: {path}")
    raise ValueError(f"SECRET_TOKEN not found in {path}")


def write_secret_file_atomic(path: Path, secret: str, mode: int = 0o600) -> None:
    """Atomically write SECRET_TOKEN=... with restricted permissions."""
    validate_master_secret_value(secret)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"SECRET_TOKEN={secret}\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".secret.", dir=path.parent, text=True)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def assert_secret_file_permissions(path: Path, max_mode: int = 0o600) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    mode = path.stat().st_mode & 0o777
    if mode > max_mode:
        raise PermissionError(f"Secret file permissions too open: {oct(mode)} (max {oct(max_mode)})")


def bearer_token_for_secret(master_secret: str, unix_seconds: int | None = None) -> str:
    if unix_seconds is None:
        unix_seconds = int(time.time())
    window_id = unix_seconds // TOKEN_VALIDITY_SECONDS
    payload = f"{master_secret}:{window_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def post_scan_status(
    host: str,
    port: int,
    master_secret: str,
    ports: list[int] | None = None,
    timeout: float = 5.0,
) -> int:
    """Return HTTP status for POST /scan using a derived bearer token (no logging)."""
    if ports is None:
        ports = [80]
    token = bearer_token_for_secret(master_secret)
    url = f"http://{host}:{port}/scan"
    body = json.dumps({"ports": ports}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def wait_for_tcp_port(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def resolve_integration_secret() -> str:
    """Secret for integration_check: env override, else demo default (CI/dev)."""
    return os.environ.get("SECRET_TOKEN", DEMO_SECRET_TOKEN)


def cmd_verify_rotation(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify master-secret rotation via local HTTP probes.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--new-secret-file", type=Path, required=True)
    parser.add_argument("--old-secret-file", type=Path, required=True)
    args = parser.parse_args(argv)

    new_secret = read_secret_file(args.new_secret_file)
    old_secret = read_secret_file(args.old_secret_file)
    new_status = post_scan_status(args.host, args.port, new_secret)
    old_status = post_scan_status(args.host, args.port, old_secret)
    if new_status != 200:
        print(f"Rotation verify failed: new secret HTTP {new_status} (expected 200)", file=sys.stderr)
        return 1
    if old_status != 401:
        print(f"Rotation verify failed: old secret HTTP {old_status} (expected 401)", file=sys.stderr)
        return 1
    print("Rotation verify: new secret accepted, old secret rejected.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "generate-secret":
        sys.stdout.write(generate_master_secret())
        raise SystemExit(0)
    if len(sys.argv) >= 2 and sys.argv[1] == "verify-rotation":
        raise SystemExit(cmd_verify_rotation(sys.argv[2:]))
    print("Usage: port_scanner_runtime.py generate-secret|verify-rotation ...", file=sys.stderr)
    raise SystemExit(2)
