#!/usr/bin/env bash
# Shared shell helpers for port-scanner manual deployment (sourced, not executed).
set -euo pipefail

port_scanner_resolve_paths() {
  PORT_SCANNER_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  PORT_SCANNER_STATE_DIR="${PORT_SCANNER_STATE_DIR:-/var/lib/port-scanner}"
  PORT_SCANNER_SECRET_FILE="${PORT_SCANNER_STATE_DIR}/secret.env"
  PORT_SCANNER_SECRET_BACKUP="${PORT_SCANNER_STATE_DIR}/secret.env.pre-rotate"
  PORT_SCANNER_PID_FILE="${PORT_SCANNER_STATE_DIR}/server.pid"
  PORT_SCANNER_META_FILE="${PORT_SCANNER_STATE_DIR}/server.meta"
  PORT_SCANNER_LOG_FILE="${PORT_SCANNER_STATE_DIR}/server.log"
  PORT_SCANNER_LISTEN_HOST="${PORT_SCANNER_LISTEN_HOST:-127.0.0.1}"
  PORT_SCANNER_LISTEN_PORT="${PORT_SCANNER_LISTEN_PORT:-8080}"
  PORT_SCANNER_SERVER_PY="${PORT_SCANNER_REPO_ROOT}/server/server.py"
  PORT_SCANNER_START_TIMEOUT="${PORT_SCANNER_START_TIMEOUT:-30}"
  PORT_SCANNER_STOP_TIMEOUT="${PORT_SCANNER_STOP_TIMEOUT:-30}"
  PORT_SCANNER_DEMO_SECRET="my_secret_123"
}

port_scanner_ensure_state_dir() {
  if [[ ! -d "${PORT_SCANNER_STATE_DIR}" ]]; then
    mkdir -p "${PORT_SCANNER_STATE_DIR}"
  fi
  chmod 700 "${PORT_SCANNER_STATE_DIR}"
}

port_scanner_scripts_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

port_scanner_read_secret_from_file() {
  local file="$1"
  PYTHONPATH="$(port_scanner_scripts_dir)" python3 -c '
from pathlib import Path
import sys
from port_scanner_runtime import read_secret_file
sys.stdout.write(read_secret_file(Path(sys.argv[1])))
' "${file}"
}

port_scanner_load_secret_into_env() {
  local secret
  secret="$(port_scanner_read_secret_from_file "${PORT_SCANNER_SECRET_FILE}")"
  if [[ -z "${secret}" ]]; then
    echo "Secret file is empty or unreadable." >&2
    return 1
  fi
  if [[ "${secret}" == "${PORT_SCANNER_DEMO_SECRET}" && "${PORT_SCANNER_ALLOW_DEMO_SECRET:-0}" != "1" ]]; then
    echo "Refusing demo secret in production path. Set PORT_SCANNER_ALLOW_DEMO_SECRET=1 for development only." >&2
    return 1
  fi
  export SECRET_TOKEN="${secret}"
}

port_scanner_write_meta() {
  {
    echo "repo_root=${PORT_SCANNER_REPO_ROOT}"
    echo "server_py=${PORT_SCANNER_SERVER_PY}"
    echo "listen_port=${PORT_SCANNER_LISTEN_PORT}"
  } > "${PORT_SCANNER_META_FILE}"
  chmod 600 "${PORT_SCANNER_META_FILE}"
}

port_scanner_pid_running() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

port_scanner_verify_managed_pid() {
  local pid="$1"
  if ! port_scanner_pid_running "${pid}"; then
    return 1
  fi
  if [[ ! -r "/proc/${pid}/cmdline" ]]; then
    echo "Cannot verify process ${pid}." >&2
    return 1
  fi
  local cmdline
  cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline")"
  if [[ "${cmdline}" != *"${PORT_SCANNER_SERVER_PY}"* ]]; then
    echo "PID ${pid} is not the managed port-scanner server (unexpected cmdline)." >&2
    return 1
  fi
  if [[ -f "${PORT_SCANNER_META_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${PORT_SCANNER_META_FILE}"
    if [[ "${server_py:-}" != "${PORT_SCANNER_SERVER_PY}" ]]; then
      echo "PID ${pid} meta mismatch (server.py path)." >&2
      return 1
    fi
  fi
  return 0
}

port_scanner_read_pid_file() {
  if [[ ! -f "${PORT_SCANNER_PID_FILE}" ]]; then
    return 1
  fi
  local pid
  pid="$(<"${PORT_SCANNER_PID_FILE}")"
  if [[ ! "${pid}" =~ ^[0-9]+$ ]]; then
    echo "Invalid PID file contents." >&2
    return 1
  fi
  printf '%s' "${pid}"
}

port_scanner_wait_for_port() {
  PYTHONPATH="$(port_scanner_scripts_dir)" python3 -c '
import sys
from port_scanner_runtime import wait_for_tcp_port
host, port, timeout = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
raise SystemExit(0 if wait_for_tcp_port(host, port, timeout) else 1)
' "${PORT_SCANNER_LISTEN_HOST}" "${PORT_SCANNER_LISTEN_PORT}" "${PORT_SCANNER_START_TIMEOUT}"
}

port_scanner_validate_master_secret() {
  local secret="$1"
  PYTHONPATH="$(port_scanner_scripts_dir)" python3 -c '
import sys
from port_scanner_runtime import validate_master_secret_value
try:
    validate_master_secret_value(sys.argv[1])
except ValueError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(1)
' "${secret}"
}

port_scanner_stop_managed() {
  local pid
  local int_wait=0
  local used_sigterm=0
  if ! pid="$(port_scanner_read_pid_file)"; then
    echo "No managed server PID file; nothing to stop." >&2
    return 1
  fi
  if ! port_scanner_verify_managed_pid "${pid}"; then
    echo "Refusing to stop non-managed PID ${pid}." >&2
    return 1
  fi
  kill -INT "${pid}" 2>/dev/null || true
  local waited=0
  while port_scanner_pid_running "${pid}" && (( int_wait < 50 )); do
    sleep 0.2
    int_wait=$((int_wait + 1))
  done
  if port_scanner_pid_running "${pid}"; then
    used_sigterm=1
    kill -TERM "${pid}" 2>/dev/null || true
    waited=0
    while port_scanner_pid_running "${pid}" && (( waited < PORT_SCANNER_STOP_TIMEOUT )); do
      sleep 1
      waited=$((waited + 1))
    done
  fi
  if port_scanner_pid_running "${pid}"; then
    echo "Managed server did not exit within bounded stop timeout." >&2
    return 1
  fi
  if (( used_sigterm )); then
    echo "Warning: managed server required SIGTERM after SIGINT did not stop it promptly." >&2
  fi
  rm -f "${PORT_SCANNER_PID_FILE}"
  return 0
}

port_scanner_start_managed() {
  if [[ ! -f "${PORT_SCANNER_SECRET_FILE}" ]]; then
    echo "Missing ${PORT_SCANNER_SECRET_FILE}. Run port_scanner_ctl.sh init first." >&2
    return 1
  fi
  PYTHONPATH="$(port_scanner_scripts_dir)" python3 -c '
from pathlib import Path
import sys
from port_scanner_runtime import assert_secret_file_permissions
assert_secret_file_permissions(Path(sys.argv[1]))
' "${PORT_SCANNER_SECRET_FILE}"
  if pid="$(port_scanner_read_pid_file 2>/dev/null || true)"; then
    if port_scanner_verify_managed_pid "${pid}"; then
      echo "Managed server already running (PID ${pid})." >&2
      return 1
    fi
    rm -f "${PORT_SCANNER_PID_FILE}"
  fi
  port_scanner_load_secret_into_env
  port_scanner_ensure_state_dir
  (
    cd "${PORT_SCANNER_REPO_ROOT}"
    export PORT_SCANNER_LISTEN_HOST="${PORT_SCANNER_LISTEN_HOST}"
    export PORT_SCANNER_LISTEN_PORT="${PORT_SCANNER_LISTEN_PORT}"
    nohup python3 "${PORT_SCANNER_SERVER_PY}" >>"${PORT_SCANNER_LOG_FILE}" 2>&1 &
    echo $! > "${PORT_SCANNER_PID_FILE}"
  )
  local new_pid
  new_pid="$(<"${PORT_SCANNER_PID_FILE}")"
  sleep 0.5
  if ! port_scanner_verify_managed_pid "${new_pid}"; then
    echo "Server process failed to start. See ${PORT_SCANNER_LOG_FILE}" >&2
    rm -f "${PORT_SCANNER_PID_FILE}"
    return 1
  fi
  port_scanner_write_meta
  if ! port_scanner_wait_for_port; then
    echo "Server did not become ready on ${PORT_SCANNER_LISTEN_HOST}:${PORT_SCANNER_LISTEN_PORT}." >&2
    port_scanner_stop_managed || true
    return 1
  fi
  echo "Managed server started (PID ${new_pid})."
  return 0
}
