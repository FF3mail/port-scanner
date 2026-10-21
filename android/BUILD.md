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

1. Start the Python server on the host machine (`python3 server.py` in `server/`).
2. In the app, enter server IP, token (`my_secret_123` by default), and ports (e.g. `22, 80, 443`).
3. Tap **Запустить проверку**.
4. Grant notification permission on Android 13+ when prompted.
5. Read the comparison in the system notification.

Device and server must be on a network where HTTP port 8080 is reachable.

## HTTP timeouts (`NetworkClient`)

- **Connect timeout:** `CONNECT_TIMEOUT_MS` (3 s) — time to establish TCP to the server.
- **Read timeout:** `HTTP_READ_TIMEOUT_MS` (35 s with current constants) — waiting for the `/scan` response body while the server may scan up to 30 ports at 1 s each, plus a 5 s safety margin. This is not a guarantee under every network or OS condition.
