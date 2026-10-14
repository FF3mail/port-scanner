# Port Scanner

Client-server application that compares port scan results: the server scans only `127.0.0.1`, the Android client scans the same host from the outside.

## Goal

Detect differences between local and external port accessibility (NAT, firewall, port forwarding).

## Repository structure

**Current**

```
port-scanner/
├── README.md
├── ROADMAP.md
└── prompts/
    ├── 00_overview.md
    ├── 01_server.md
    ├── 02_android_client.md
    └── 03_integration.md
```

**Planned**

```
port-scanner/
├── server/
│   └── server.py
└── android/
    └── (Android Studio project)
```

## Quick start

### Server

Requirements: Python 3, Ubuntu (or any host with Python 3).

```bash
python3 server.py
```

Run from the `server/` directory (when `server.py` is added).

Listens on port `8080`. Stop with `Ctrl+C`.

### Android client

Requirements: Android 8+ (minSdk 26), Android Studio.

1. Open the `android/` project in Android Studio.
2. Build and install on a device or emulator.
3. Ensure the device can reach the server (same network or routed access).

## Basic usage

1. Start the server on the machine whose ports you want to check locally.
2. In the app, enter the server IP, bearer token, and ports (e.g. `22, 80, 443`).
3. Tap run. The app requests a server scan and scans the same ports from the device.
4. Read the comparison in the system notification (not on the main screen).

Example notification line:

```
Port 80: Server OPEN, Client CLOSED → blocked by NAT/firewall
```

## API (short)

| Item | Value |
|------|--------|
| Endpoint | `POST http://<IP>:8080/scan` |
| Auth | `Authorization: Bearer <token>` |
| Body | `{"ports": [22, 80, 443]}` |
| Success | `200` — `{"results": {"22": "OPEN", "80": "CLOSED", ...}}` |
| Port status | `"OPEN"` or `"CLOSED"` only |
| Errors | `401` Unauthorized, `400` Bad Request — `{"error": "..."}` |

Full contract: [prompts/00_overview.md](prompts/00_overview.md).

## Documentation

| Document | Description |
|----------|-------------|
| [ROADMAP.md](ROADMAP.md) | Development plan and checklist |
| [prompts/00_overview.md](prompts/00_overview.md) | API contract and overview |
| [prompts/01_server.md](prompts/01_server.md) | Server specification |
| [prompts/02_android_client.md](prompts/02_android_client.md) | Android client specification |
| [prompts/03_integration.md](prompts/03_integration.md) | Integration test scenarios |

## Status

Specification only — server and Android code are under development.

| Component | Stack |
|-----------|--------|
| Server | Python 3, Ubuntu |
| Client | Android 8+ (minSdk 26), Kotlin |
