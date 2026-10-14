# 02. Android Client (Kotlin)

## Версии
- minSdk = 26
- targetSdk = 35
- compileSdk = 35
- Язык: только Kotlin

## Зависимости (строго эти, больше ничего не добавлять)
implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.4")
implementation("androidx.core:core-ktx:1.13.1")
implementation("com.google.android.material:material:1.12.0")
implementation("androidx.activity:activity-ktx:1.9.2")

## Запрещено
- OkHttp, Retrofit, Ktor, Volley и любые другие HTTP-библиотеки
- Только java.net.HttpURLConnection и java.net.Socket

## Структура пакетов (строго)
com.example.portscanner
├── data
│   └── NetworkClient.kt
├── domain
│   ├── PortStatus.kt
│   ├── ScanResult.kt
│   └── PortComparison.kt
├── presentation
│   ├── MainActivity.kt
│   └── ScanViewModel.kt
└── util
    └── NotificationHelper.kt

## UI (MainActivity) — строго
- 3 поля EditText:
  1. IP или домен сервера
  2. Токен авторизации
  3. Порты (строка вида "22, 80, 443, 3306")
- 1 кнопка "Запустить проверку"
- 1 ProgressBar (indeterminate)
- Никаких TextView, RecyclerView или других элементов для отображения результатов
- Результаты показываются ТОЛЬКО в системном уведомлении

## Константы (обязательно)
CONNECT_TIMEOUT_MS = 3000L
PORT_TIMEOUT_MS = 1500L
MAX_PORTS = 30

## Логика ScanViewModel (строго)

1. Валидация всех полей. При ошибке — Toast и выход.
2. Парсинг строки портов → List<Int>
   - Учитывать пробелы
   - Порты только 1..65535
   - Не больше MAX_PORTS
3. viewModelScope.launch:
   - Запустить две параллельные задачи через async:
     А) postScan на сервер
     Б) scanPorts по внешнему IP
4. Обработка результата сервера:
   - Сервер недоступен (таймаут / ConnectException) → Toast "Сервер недоступен", уведомление НЕ отправлять, выйти
   - 401 → Toast "Неверный токен", выйти
   - 400 или 500 → Toast с текстом ошибки, выйти
5. Дождаться клиентского сканирования (даже если оно упало — уведомление всё равно формируется)
6. Сформировать список PortComparison
7. Отправить уведомление через NotificationHelper

## NetworkClient
Два метода:
- suspend fun postScan(ip: String, token: String, ports: List<Int>): ScanResponse
- suspend fun scanPorts(ip: String, ports: List<Int>): Map<Int, String>

Параметр `token` в postScan — **мастер-секрет** (`SECRET_TOKEN = "my_secret_123"`). Перед запросом клиент вычисляет временной Bearer-токен тем же алгоритмом, что сервер: `SHA-256(master_secret + ":" + window_id)` (hex), где `window_id = floor(unix_seconds / (6*3600))`. В заголовок уходит `Authorization: Bearer <вычисленный_токен>`.

Оба метода обязательно выполнять в withContext(Dispatchers.IO).
Статусы портов строго "OPEN" или "CLOSED".

## Уведомления (NotificationHelper)
- Канал: "port_scanner_channel"
- Важность: IMPORTANCE_HIGH
- Запрос разрешения POST_NOTIFICATIONS через ActivityResultLauncher (Android 13+)
- Если разрешение не выдано — только Toast, уведомление не отправлять
- Стиль: BigTextStyle

Формат текста уведомления (строго):

Порт 22: Сервер OPEN, Клиент OPEN → ✅ Match OK
Порт 80: Сервер OPEN, Клиент CLOSED → ⚠️ Заблокирован файрволом/NAT!
Порт 443: Сервер CLOSED, Клиент CLOSED → ✅ Match OK

Совпадений: 2, Расхождений: 1

Заголовок уведомления: "Результаты сканирования портов"

## Обработка ошибок (приоритет)
1. Сервер недоступен → только Toast, уведомления нет
2. Неверный токен / 400 / 500 → Toast, уведомления нет
3. Ошибка только клиентского сканирования → уведомление всё равно отправляется + пометка об ошибке

## Дополнительные требования
- ViewModel должна переживать поворот экрана (состояние isLoading)
- Все таймауты вынесены в const val
- Нет отображения результатов на экране

## Формат выдачи
Выдай файлы в следующем порядке (каждый файл полностью):

1. AndroidManifest.xml
2. app/build.gradle.kts
3. MainActivity.kt
4. ScanViewModel.kt
5. NetworkClient.kt
6. NotificationHelper.kt
7. Все файлы domain (модели)
8. Краткая инструкция по сборке и запуску
