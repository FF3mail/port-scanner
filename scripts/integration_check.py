#!/usr/bin/env python3
"""
Regression checks against a running port-scanner server (default 127.0.0.1:8080).

Usage:
  python3 server/server.py   # in another terminal
  python3 scripts/integration_check.py
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.error
import urllib.request

HOST = "127.0.0.1"
PORT = 8080
BASE = f"http://{HOST}:{PORT}/scan"

# Must match server/server.py
SECRET_TOKEN = "my_secret_123"
TOKEN_VALIDITY_SECONDS = 6 * 3600


def current_bearer_token(secret: str = SECRET_TOKEN) -> str:
    import hashlib
    import time

    window_id = int(time.time()) // TOKEN_VALIDITY_SECONDS
    return hashlib.sha256(f"{secret}:{window_id}".encode("utf-8")).hexdigest()


def post_scan(
    ports: list[int],
    token: str | None = None,
    host: str = HOST,
    port: int = PORT,
    timeout: float = 5,
    extra_body: dict | None = None,
) -> tuple[int, dict]:
    if token is None:
        token = current_bearer_token()
    url = f"http://{host}:{port}/scan"
    payload = {"ports": ports}
    if extra_body:
        payload.update(extra_body)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    code, data = post_scan([22, 80, 443])
    order = list(data.get("results", {}).keys())
    statuses = set(data.get("results", {}).values())
    check(
        "positive scan",
        code == 200 and order == ["22", "80", "443"] and statuses <= {"OPEN", "CLOSED"},
        f"HTTP {code}, order={order}",
    )

    code, body = post_scan([80], token="bad-token")
    check("401 wrong token", code == 401 and body.get("error") == "Unauthorized", str(body))

    code, body = post_scan([])
    check("400 empty ports", code == 400, str(body))

    code, body = post_scan(list(range(1, 32)))
    check("400 too many ports", code == 400, f"HTTP {code}")

    code, body = post_scan([0])
    check("400 invalid port", code == 400, str(body))

    try:
        post_scan([80], host="192.0.2.1", timeout=2)
        check("unreachable host", False, "expected connection error")
    except (urllib.error.URLError, TimeoutError, OSError):
        check("unreachable host", True, "connection failed as expected")

    # Listener only on 127.0.0.1 — server should report OPEN.
    test_port = 38777
    ready = threading.Event()

    def localhost_listener() -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", test_port))
        srv.listen(1)
        ready.set()
        conn, _ = srv.accept()
        conn.close()
        srv.close()

    thread = threading.Thread(target=localhost_listener, daemon=True)
    thread.start()
    ready.wait(timeout=3)
    code, data = post_scan([test_port], extra_body={"host": "8.8.8.8"})
    server_status = data.get("results", {}).get(str(test_port))
    check(
        "scan localhost only (host key ignored)",
        code == 200 and server_status == "OPEN",
        f"status={server_status}",
    )

    if failures:
        print("\nFailed:", ", ".join(failures))
        return 1

    print("\nAll integration checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
