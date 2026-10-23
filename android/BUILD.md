# Port Scanner — Android client

## Requirements

- Android Studio (Ladybug or newer recommended)
- JDK 17
- Android SDK with API 35

## Build and run

1. Open the `android/` folder in Android Studio.
2. Wait for Gradle sync to finish.
3. Connect a device or start an emulator (API 26+).
4. Run **app** (green Run button) or from terminal:

```bash
cd android
./gradlew assembleDebug
```

On Windows, if the project path contains non-ASCII characters (e.g. Cyrillic folder names), `android.overridePathCheck=true` in `gradle.properties` allows Gradle CLI builds to proceed. Prefer an ASCII-only path when possible.

APK: `app/build/outputs/apk/debug/app-debug.apk`

## Usage

1. Deploy the Python server behind a **TLS-terminating reverse proxy** that forwards to the plain HTTP backend (see `server/DEPLOY_LINUX.md`). The hostname in the certificate must be trusted by Android (public CA or a CA installed on the device).
2. In the app, enter **server hostname or IP** (without `https://`), optional **HTTPS port** (default **443** if left empty), master secret token, and ports to scan (e.g. `22, 80, 443`).
3. Tap **Запустить проверку**. The client calls `POST https://<host>:<port>/scan` using the platform TLS stack (standard certificate and hostname verification).
4. Grant notification permission on Android 13+ when prompted.
5. Read the comparison in the system notification.

This app does **not** configure the reverse proxy or server TLS. Remote HTTPS scans succeed only after that infrastructure is in place. There is **no** automatic fallback to cleartext HTTP when HTTPS fails.

**Release builds:** `AndroidManifest.xml` still sets `android:usesCleartextTraffic="true"` for local development convenience. Restricting cleartext in release builds is a separate follow-up (network security config).

## HTTP timeouts (`NetworkClient`)

- **Connect timeout:** `CONNECT_TIMEOUT_MS` (3 s) — time to establish TCP to the server.
- **Read timeout:** `HTTP_READ_TIMEOUT_MS` (35 s with current constants) — waiting for the `/scan` response body while the server may scan up to 30 ports at 1 s each, plus a 5 s safety margin. This is not a guarantee under every network or OS condition.
