#!/usr/bin/env python3
"""
Однопоточный HTTP-сервер сканирования локальных портов (127.0.0.1).
Спецификация: prompts/01_server.md
"""

import hashlib
import http.server
import json
import os
import signal
import socket
import sys
import threading
import time

# --- Константы (обязательные) ---
# Demo default kept for backward compatibility; prefer SECRET_TOKEN env in production.
SECRET_TOKEN = os.environ.get("SECRET_TOKEN", "my_secret_123")
TOKEN_VALIDITY_SECONDS = 6 * 3600  # окно действия Bearer-токена (6 часов)
SCAN_TIMEOUT = 1.0  # секунды на один порт
MAX_PORTS = 30  # жёсткий лимит количества портов

LISTEN_HOST = ""  # все интерфейсы
LISTEN_PORT = int(os.environ.get("PORT_SCANNER_LISTEN_PORT", "8080"))
SCAN_HOST = "127.0.0.1"


def scan_port(port: int) -> str:
    """Проверка одного порта на 127.0.0.1."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(SCAN_TIMEOUT)
    result = sock.connect_ex((SCAN_HOST, port))
    sock.close()
    return "OPEN" if result == 0 else "CLOSED"


def _is_valid_port(value) -> bool:
    """Порт — целое число 1..65535 (bool исключаем: подкласс int в Python)."""
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def _token_window_id(unix_timestamp: int) -> int:
    """Номер 6-часового окна для Unix-времени в секундах."""
    return unix_timestamp // TOKEN_VALIDITY_SECONDS


def generate_time_limited_token(
    master_secret: str = SECRET_TOKEN,
    window_id: int | None = None,
    unix_timestamp: int | None = None,
) -> str:
    """
    Детерминированный Bearer-токен: SHA-256(master_secret + ':' + str(window_id)), hex.
    По умолчанию — токен для текущего окна.
    """
    if window_id is None:
        if unix_timestamp is None:
            unix_timestamp = int(time.time())
        window_id = _token_window_id(unix_timestamp)
    digest = hashlib.sha256(f"{master_secret}:{window_id}".encode("utf-8")).hexdigest()
    return digest


def _accepted_bearer_tokens(master_secret: str = SECRET_TOKEN, unix_timestamp: int | None = None) -> frozenset[str]:
    """Токены текущего и предыдущего окна (граница смены окна)."""
    if unix_timestamp is None:
        unix_timestamp = int(time.time())
    window_id = _token_window_id(unix_timestamp)
    return frozenset(
        {
            generate_time_limited_token(master_secret, window_id=window_id),
            generate_time_limited_token(master_secret, window_id=window_id - 1),
        }
    )


class ScanRequestHandler(http.server.BaseHTTPRequestHandler):
    """Обработчик POST /scan с Bearer-авторизацией."""

    server_version = "PortScanner/1.0"

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_authorization(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        presented = auth_header[len("Bearer ") :]
        return presented in _accepted_bearer_tokens()

    def _read_json_body(self) -> tuple[dict | None, str | None]:
        """Читает и парсит JSON; при ошибке возвращает (None, сообщение)."""
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return None, "Missing Content-Length"

        try:
            length = int(raw_length)
        except ValueError:
            return None, "Invalid Content-Length"

        if length < 0:
            return None, "Invalid Content-Length"

        try:
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, "Invalid JSON"

        if not isinstance(data, dict):
            return None, "Request body must be a JSON object"

        return data, None

    def _validate_ports(self, data: dict) -> tuple[list[int] | None, str | None]:
        """Валидация списка ports; ключ host игнорируется."""
        return validate_ports_payload(data)

    def do_POST(self) -> None:
        if self.path != "/scan":
            self._send_json(404, {"error": "Not found"})
            return

        if not self._check_authorization():
            self._send_json(401, {"error": "Unauthorized"})
            return

        data, err = self._read_json_body()
        if err is not None:
            self._send_json(400, {"error": err})
            return

        ports, err = self._validate_ports(data)
        if err is not None:
            self._send_json(400, {"error": err})
            return

        # Порядок ключей в results совпадает с порядком во входном списке
        results: dict[str, str] = {}
        for port in ports:
            results[str(port)] = scan_port(port)

        self._send_json(200, {"results": results})

    def do_GET(self) -> None:
        self._send_json(405, {"error": "Method not allowed"})

    def do_PUT(self) -> None:
        self._send_json(405, {"error": "Method not allowed"})

    def do_DELETE(self) -> None:
        self._send_json(405, {"error": "Method not allowed"})

    def do_PATCH(self) -> None:
        self._send_json(405, {"error": "Method not allowed"})

    def log_message(self, format: str, *args) -> None:
        # Без отдельных logging-фреймворков; минимальный вывод в stderr
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))


def validate_ports_payload(data: dict) -> tuple[list[int] | None, str | None]:
    """
    Pure port-list validation mirrored from ScanRequestHandler._validate_ports.
    Extracted for unit tests without binding a socket.
    """
    if "ports" not in data:
        return None, "Missing ports field"

    ports = data["ports"]
    if not isinstance(ports, list):
        return None, "ports must be a list"

    if len(ports) == 0:
        return None, "ports must not be empty"

    if len(ports) > MAX_PORTS:
        return None, f"Too many ports (max {MAX_PORTS})"

    validated: list[int] = []
    for item in ports:
        if not _is_valid_port(item):
            return None, "Each port must be an integer from 1 to 65535"
        validated.append(item)

    return validated, None


def main() -> None:
    # Intentional single-threaded HTTPServer (no ThreadingMixIn per prompts/01_server.md).
    worst_case = MAX_PORTS * SCAN_TIMEOUT
    sys.stderr.write(
        "WARNING: single-threaded server; worst-case scan latency ≈ "
        f"{MAX_PORTS} * {SCAN_TIMEOUT}s = {worst_case:.0f}s when many ports are closed/filtered\n"
    )

    httpd = http.server.HTTPServer((LISTEN_HOST, LISTEN_PORT), ScanRequestHandler)

    def request_shutdown(signum: int, frame) -> None:
        # shutdown() must not run on the serve_forever() thread (deadlock). Signal handler
        # schedules it on a short-lived background thread (SIGINT interactive, SIGTERM from ctl).
        threading.Thread(target=httpd.shutdown, name="port-scanner-shutdown", daemon=True).start()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
