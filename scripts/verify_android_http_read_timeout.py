#!/usr/bin/env python3
"""
Regression checks for Android HTTP_READ_TIMEOUT_MS vs server worst-case scan time.

Parses NetworkClient.kt constants and verifies a delayed HTTP response can be read
after the legacy 3 s budget but within the configured read timeout (stdlib only).
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NETWORK_CLIENT = (
    ROOT / "android/app/src/main/java/com/example/portscanner/data/NetworkClient.kt"
)


def parse_long_constant(name: str, source: str) -> int:
    match = re.search(rf"const val {name} = (\d+)L?", source)
    if not match:
        raise AssertionError(f"Missing constant {name} in NetworkClient.kt")
    return int(match.group(1))


def parse_max_ports(source: str) -> int:
    return parse_long_constant("MAX_PORTS", source)


def parse_read_timeout_ms(source: str) -> int:
    per_port = parse_long_constant("SERVER_SCAN_TIMEOUT_PER_PORT_MS", source)
    margin = parse_long_constant("HTTP_READ_SAFETY_MARGIN_MS", source)
    max_ports = parse_max_ports(source)
    if "HTTP_READ_TIMEOUT_MS =" not in source:
        raise AssertionError("HTTP_READ_TIMEOUT_MS not defined")
    expected = max_ports * per_port + margin
    # Allow explicit literal override only if it matches the documented formula.
    literal = re.search(r"HTTP_READ_TIMEOUT_MS\s*=\s*(\d+)L", source)
    if literal:
        actual = int(literal.group(1))
        if actual != expected:
            raise AssertionError(
                f"HTTP_READ_TIMEOUT_MS literal {actual} != formula {expected}"
            )
        return actual
    return expected


class DelayedHandler(BaseHTTPRequestHandler):
    delay_seconds: float = 4.0

    def do_POST(self) -> None:
        time.sleep(self.delay_seconds)
        body = json.dumps({"results": {"80": "CLOSED"}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    failures: list[str] = []
    source = NETWORK_CLIENT.read_text(encoding="utf-8")

    try:
        connect_ms = parse_long_constant("CONNECT_TIMEOUT_MS", source)
        read_ms = parse_read_timeout_ms(source)
        if "connection.readTimeout = HTTP_READ_TIMEOUT_MS" not in source:
            failures.append("readTimeout must use HTTP_READ_TIMEOUT_MS")
        if connect_ms >= read_ms:
            failures.append("CONNECT_TIMEOUT_MS must stay below HTTP_READ_TIMEOUT_MS")
        if read_ms < 30_000:
            failures.append("HTTP_READ_TIMEOUT_MS must cover 30 s server scan")
    except AssertionError as exc:
        failures.append(str(exc))

    if failures:
        for item in failures:
            print(f"[FAIL] {item}")
        return 1

    server = HTTPServer(("127.0.0.1", 0), DelayedHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/scan"
    req = urllib.request.Request(
        url,
        data=json.dumps({"ports": [80]}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    legacy_budget_s = 3.0
    if DelayedHandler.delay_seconds <= legacy_budget_s:
        failures.append("Test delay must exceed legacy 3 s read budget")

    try:
        with urllib.request.urlopen(req, timeout=read_ms / 1000.0) as resp:
            status = resp.status
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        failures.append(f"Delayed response not read within {read_ms} ms: {exc}")
        status = 0
        payload = {}

    if status != 200 or payload.get("results", {}).get("80") != "CLOSED":
        failures.append(f"Unexpected delayed response: HTTP {status} {payload}")

    try:
        with urllib.request.urlopen(req, timeout=legacy_budget_s) as _:
            failures.append("Legacy 3 s budget should have timed out on delayed handler")
    except (urllib.error.URLError, TimeoutError):
        pass
    except Exception as exc:
        failures.append(f"Unexpected error on legacy timeout probe: {exc}")
    finally:
        server.shutdown()

    if failures:
        for item in failures:
            print(f"[FAIL] {item}")
        return 1

    print(
        f"[PASS] HTTP_READ_TIMEOUT_MS={read_ms} (connect={connect_ms} ms); "
        f"delayed {DelayedHandler.delay_seconds}s response OK"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
