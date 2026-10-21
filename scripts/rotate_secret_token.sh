#!/usr/bin/env bash
# Rotate SECRET_TOKEN for the managed manual Python deployment (run over SSH).
set -euo pipefail
set +x

# shellcheck source=port_scanner_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/port_scanner_lib.sh"

usage() {
  cat <<'EOF'
Usage: rotate_secret_token.sh [--custom]

  Generate a new master secret, persist it atomically, restart the managed server,
  and verify the new secret works while the previous secret is rejected (HTTP 401).

  --custom   Prompt for a custom secret (no echo) instead of auto-generation.

Environment: same as port_scanner_ctl.sh (PORT_SCANNER_STATE_DIR, PORT_SCANNER_LISTEN_PORT, ...).

Android clients must be updated with the new master secret after rotation.
EOF
}

rollback_secret() {
  if [[ -f "${PORT_SCANNER_SECRET_BACKUP}" ]]; then
    cp -f "${PORT_SCANNER_SECRET_BACKUP}" "${PORT_SCANNER_SECRET_FILE}"
    chmod 600 "${PORT_SCANNER_SECRET_FILE}"
  fi
}

main() {
  local custom=0
  if [[ "${1:-}" == "--custom" ]]; then
    custom=1
  elif [[ -n "${1:-}" ]]; then
    usage >&2
    exit 2
  fi

  port_scanner_resolve_paths
  port_scanner_ensure_state_dir

  if [[ ! -f "${PORT_SCANNER_SECRET_FILE}" ]]; then
    echo "Missing ${PORT_SCANNER_SECRET_FILE}. Run port_scanner_ctl.sh init first." >&2
    exit 1
  fi

  local was_running=0
  if pid="$(port_scanner_read_pid_file 2>/dev/null || true)"; then
    if port_scanner_verify_managed_pid "${pid}"; then
      was_running=1
    elif port_scanner_pid_running "${pid}"; then
      echo "Refusing to rotate: PID file points at a non-managed process." >&2
      exit 1
    else
      rm -f "${PORT_SCANNER_PID_FILE}"
      echo "Managed server is not running. Start it before rotation." >&2
      exit 1
    fi
  else
    echo "Managed server is not running. Start it before rotation." >&2
    exit 1
  fi

  cp -f "${PORT_SCANNER_SECRET_FILE}" "${PORT_SCANNER_SECRET_BACKUP}"
  chmod 600 "${PORT_SCANNER_SECRET_BACKUP}"

  local new_secret
  if (( custom )); then
    read -rsp "Enter new master secret: " new_secret
    echo >&2
    read -rsp "Confirm new master secret: " confirm
    echo >&2
    if [[ "${new_secret}" != "${confirm}" ]]; then
      echo "Secrets do not match. Aborting." >&2
      exit 1
    fi
    if [[ -z "${new_secret}" ]]; then
      echo "Empty secret. Aborting." >&2
      exit 1
    fi
  else
    new_secret="$(PYTHONPATH="$(port_scanner_scripts_dir)" python3 "$(port_scanner_scripts_dir)/port_scanner_runtime.py" generate-secret)"
  fi

  if ! port_scanner_stop_managed; then
    echo "Failed to stop managed server before rotation." >&2
    exit 1
  fi

  if ! _PORT_SCANNER_NEW_SECRET="${new_secret}" PYTHONPATH="$(port_scanner_scripts_dir)" python3 -c '
from pathlib import Path
import os
import sys
from port_scanner_runtime import write_secret_file_atomic
write_secret_file_atomic(Path(sys.argv[1]), os.environ["_PORT_SCANNER_NEW_SECRET"])
' "${PORT_SCANNER_SECRET_FILE}"; then
    echo "Failed to write new secret. Restoring backup." >&2
    rollback_secret
    if (( was_running )); then
      port_scanner_start_managed || echo "CRITICAL: rollback write failed and server may be down." >&2
    fi
    exit 1
  fi
  unset new_secret confirm _PORT_SCANNER_NEW_SECRET

  if ! port_scanner_start_managed; then
    echo "Restart with new secret failed. Rolling back." >&2
    rollback_secret
    if ! port_scanner_start_managed; then
      echo "CRITICAL: rollback restart failed. Check ${PORT_SCANNER_LOG_FILE} and secret files." >&2
      exit 1
    fi
    echo "Rollback complete; previous secret restored." >&2
    exit 1
  fi

  verify_failed=0
  if [[ "${PORT_SCANNER_TEST_VERIFY_FAIL:-0}" == "1" ]]; then
    verify_failed=1
  elif ! PYTHONPATH="$(port_scanner_scripts_dir)" python3 "$(port_scanner_scripts_dir)/port_scanner_runtime.py" verify-rotation \
    --host "${PORT_SCANNER_LISTEN_HOST}" \
    --port "${PORT_SCANNER_LISTEN_PORT}" \
    --new-secret-file "${PORT_SCANNER_SECRET_FILE}" \
    --old-secret-file "${PORT_SCANNER_SECRET_BACKUP}"; then
    verify_failed=1
  fi
  if [[ "${verify_failed}" == "1" ]]; then
    echo "Verification failed. Rolling back." >&2
    port_scanner_stop_managed || true
    rollback_secret
    if ! port_scanner_start_managed; then
      echo "CRITICAL: verification and rollback restart failed." >&2
      exit 1
    fi
    echo "Rollback complete; previous secret restored." >&2
    exit 1
  fi

  rm -f "${PORT_SCANNER_SECRET_BACKUP}"
  echo "Master secret rotated successfully. Update Android clients with the new master secret."
}

main "$@"
