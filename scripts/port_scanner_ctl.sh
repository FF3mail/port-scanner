#!/usr/bin/env bash
# Manual lifecycle control for port-scanner server (Linux, no systemd required).
set -euo pipefail

# shellcheck source=port_scanner_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/port_scanner_lib.sh"

usage() {
  cat <<'EOF'
Usage: port_scanner_ctl.sh <init|start|stop|status>

  init   Create state dir and secret.env (generate if missing).
  start  Start managed server using secret.env (refuses demo secret unless allowed).
  stop   Stop managed server (SIGINT, then SIGTERM).
  status Report whether the managed server is running.

Environment:
  PORT_SCANNER_STATE_DIR       State directory (default: /var/lib/port-scanner)
  PORT_SCANNER_LISTEN_PORT     HTTP port (default: 8080)
  PORT_SCANNER_ALLOW_DEMO_SECRET=1  Allow demo secret in secret.env (dev only)
EOF
}

cmd_init() {
  port_scanner_resolve_paths
  port_scanner_ensure_state_dir
  if [[ -f "${PORT_SCANNER_SECRET_FILE}" ]]; then
    echo "Secret file already exists: ${PORT_SCANNER_SECRET_FILE}"
    return 0
  fi
  local secret
  secret="$(PYTHONPATH="$(port_scanner_scripts_dir)" python3 "$(port_scanner_scripts_dir)/port_scanner_runtime.py" generate-secret)"
  _PORT_SCANNER_NEW_SECRET="${secret}" PYTHONPATH="$(port_scanner_scripts_dir)" python3 -c '
from pathlib import Path
import os
import sys
from port_scanner_runtime import write_secret_file_atomic
write_secret_file_atomic(Path(sys.argv[1]), os.environ["_PORT_SCANNER_NEW_SECRET"])
' "${PORT_SCANNER_SECRET_FILE}"
  unset secret _PORT_SCANNER_NEW_SECRET
  echo "Initialized ${PORT_SCANNER_SECRET_FILE} (permissions 600)."
  echo "Start with: port_scanner_ctl.sh start"
}

cmd_status() {
  port_scanner_resolve_paths
  if pid="$(port_scanner_read_pid_file 2>/dev/null || true)"; then
    if port_scanner_verify_managed_pid "${pid}"; then
      echo "Managed server running (PID ${pid}) on port ${PORT_SCANNER_LISTEN_PORT}."
      return 0
    fi
    echo "Stale PID file (process ${pid} not managed server)." >&2
    return 1
  fi
  echo "Managed server not running."
  return 1
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    init) cmd_init ;;
    start)
      port_scanner_resolve_paths
      port_scanner_start_managed
      ;;
    stop)
      port_scanner_resolve_paths
      port_scanner_stop_managed
      echo "Managed server stopped."
      ;;
    status) cmd_status ;;
    -h|--help|help) usage ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
