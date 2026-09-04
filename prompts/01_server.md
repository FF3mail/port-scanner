# 01. Server (Python 3, Ubuntu)

## Файл
server.py

## Жёсткие требования
- Только стандартная библиотека: http.server, socket, json, signal, sys
- Однопоточный HTTPServer (запрещено использовать ThreadingMixIn)
- Порт: 8080
- Запуск: python3 server.py
- Корректное завершение по Ctrl+C (обработчик SIGINT)

## Константы (обязательно)
SECRET_TOKEN = "my_secret_123"
SCAN_TIMEOUT = 1.0          # секунды на один порт
MAX_PORTS = 30              # жёсткий лимит количества портов

## Авторизация
Заголовок: Authorization: Bearer my_secret_123
Любое несовпадение токена → HTTP 401 + тело {"error": "Unauthorized"}

## Эндпоинт
POST /scan

### Входной JSON (строго этот формат)
{"ports": [22, 80, 443]}

### Правила обработки входа
- Игнорировать любой ключ "host" (даже если он передан)
- Всегда сканировать ТОЛЬКО 127.0.0.1
- ports должен быть списком целых чисел
- Каждый порт должен быть в диапазоне 1..65535
- Максимум MAX_PORTS портов
- Пустой список / отсутствует ключ "ports" / невалидный JSON → HTTP 400 + {"error": "..."}

### Логика сканирования одного порта
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(SCAN_TIMEOUT)
result = sock.connect_ex(("127.0.0.1", port))
sock.close()
status = "OPEN" if result == 0 else "CLOSED"

### Успешный ответ (HTTP 200)
{
  "results": {
    "22": "OPEN",
    "80": "CLOSED",
    "443": "OPEN"
  }
}

Требования к ответу:
- Content-Type: application/json; charset=utf-8
- Порядок ключей в results должен совпадать с порядком портов во входном списке
- Статусы только "OPEN" или "CLOSED"

### Ошибки
- 400 Bad Request → {"error": "описание"}
- 401 Unauthorized → {"error": "Unauthorized"}
- 405 Method Not Allowed (разрешён только POST)

## Дополнительно
- Сервер должен корректно завершаться по Ctrl+C
- Не использовать потоки и асинхронность
- Весь код должен быть в одном файле server.py с комментариями

## Формат выдачи
Выдай полный готовый файл server.py без сокращений.
