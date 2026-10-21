# Linux manual deployment and master-secret rotation

This document describes the **supported manual deployment** for the port-scanner Python server on Linux (SSH administration, no systemd/Docker required).

## Prerequisites

- Python 3 (same as `server/server.py`)
- Bash
- Write access to a state directory (default `/var/lib/port-scanner`)
- Port **8080** (or `PORT_SCANNER_LISTEN_PORT`) reachable from Android clients on your network

**Security:** The server uses **plain HTTP**. SSH protects administration only; Bearer tokens on the wire are not encrypted. Use a trusted network or place TLS in front of the service separately.

## One-time setup

1. Clone or install the repository (e.g. `/opt/port-scanner`).
2. Create state directory and an initial master secret (never commit this file):

```bash
cd /opt/port-scanner
export PORT_SCANNER_STATE_DIR=/var/lib/port-scanner   # optional; this is the default
sudo mkdir -p "$PORT_SCANNER_STATE_DIR"
sudo chown "$(whoami)" "$PORT_SCANNER_STATE_DIR"
./scripts/port_scanner_ctl.sh init
```

`init` writes `$PORT_SCANNER_STATE_DIR/secret.env` with mode **600** and a randomly generated `SECRET_TOKEN`.

3. Start the managed server:

```bash
./scripts/port_scanner_ctl.sh start
./scripts/port_scanner_ctl.sh status
```

The production launch path **refuses** the demo secret `my_secret_123` unless `PORT_SCANNER_ALLOW_DEMO_SECRET=1` (development only). Direct `python3 server/server.py` without `secret.env` still uses the demo default for local/CI use.

## Manual launch contract

| Artifact | Purpose |
|----------|---------|
| `secret.env` | `SECRET_TOKEN=...` (mode 600) |
| `server.pid` | PID of the managed `server/server.py` process |
| `server.meta` | Repo path and `server.py` path for PID verification |
| `server.log` | Server stderr/stdout from `nohup` |

Stop: `./scripts/port_scanner_ctl.sh stop` (SIGINT, then SIGTERM; only if `/proc/PID/cmdline` matches this repo’s `server/server.py`).

## Rotate master secret (SSH)

```bash
cd /opt/port-scanner
./scripts/rotate_secret_token.sh
# Optional custom secret (no echo):
./scripts/rotate_secret_token.sh --custom
```

The script:

1. Requires the managed server to be **running**
2. Backs up `secret.env`
3. Stops the managed server
4. Writes a new secret atomically
5. Restarts and waits for the listening port
6. Verifies **new** secret → HTTP 200 and **old** secret → HTTP 401 (local `POST /scan`, no external scan)
7. On any failure, restores the backup and restarts with the **previous** secret

**Success output** does not print secrets or Authorization headers.

### Android after rotation

Users must enter the **new master secret** in the app (the app derives the 6-hour Bearer token locally). There is no grace period for the old master secret after a successful rotation.

## Recovery

| Situation | Action |
|-----------|--------|
| Rotation reported failure but rollback succeeded | Previous secret still in `secret.env`; confirm with `port_scanner_ctl.sh status` |
| Rotation failed and rollback restart failed | Check `server.log`, `secret.env`, and `secret.env.pre-rotate`; manually run `port_scanner_ctl.sh stop` then `start` after fixing `secret.env` |
| Stale `server.pid` | Remove PID file only if no matching `server/server.py` process |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT_SCANNER_STATE_DIR` | `/var/lib/port-scanner` | Config and PID files |
| `PORT_SCANNER_LISTEN_PORT` | `8080` | HTTP port (`PORT_SCANNER_LISTEN_PORT` in server) |
| `PORT_SCANNER_LISTEN_HOST` | `127.0.0.1` | Host for readiness/verify probes |
| `PORT_SCANNER_ALLOW_DEMO_SECRET` | `0` | Set to `1` to allow demo secret in `secret.env` |
| `PORT_SCANNER_TEST_VERIFY_FAIL` | `0` | **Tests only** — force verify failure |

## Verification commands

```bash
python3 scripts/test_server_unit.py -q
python3 scripts/integration_check.py   # with server running; uses SECRET_TOKEN env if set
```
