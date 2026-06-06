"""

=======================================================
Все настройки приложения в одном месте.
Меняй здесь, не трогая основной код.
"""

import os

# ─────────────────────────────────────────────
#  Папка данных приложения (AppData)
# ─────────────────────────────────────────────
APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".paketik")
os.makedirs(APP_DATA_DIR, exist_ok=True)

# ─────────────────────────────────────────────
#  RouterAI / OpenAI-совместимый API
#  API-ключ загружается из license_manager.api_key после активации
# ─────────────────────────────────────────────
ROUTERAI_BASE_URL = "https://routerai.ru/api/v1"
ROUTERAI_API_KEY  = ""   # заполняется динамически из license_manager

# ВАЖНО: модель с поддержкой Vision (изображений)
AI_MODEL        = "deepseek/deepseek-v3.2"          # Vision модель (быстрая, дешёвая, умная)
AI_MODEL_TEXT   = "deepseek/deepseek-v3.2"          # Текстовая модель (та же)

# Использовать ли vision (если False — только HTML-текст)
USE_VISION = False  # Используем структурированные данные, не скриншоты — быстрее и дешевле

# Fallback: локальная Ollama
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL    = "llava:latest"

# ─────────────────────────────────────────────
#  Целевой сайт
# ─────────────────────────────────────────────
TARGET_URL = "https://uup.tigt.site/test/"

# ─────────────────────────────────────────────
#  Браузеры (пути по умолчанию)
# ─────────────────────────────────────────────
BROWSER_PATHS = {
    "Yandex": [
        r"C:\Users\{user}\AppData\Local\Yandex\YandexBrowser\Application\browser.exe",
        r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe",
        "/usr/bin/yandex-browser",
    ],
    "Chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
    ],
}

USER_DATA_BASE = os.path.join(os.path.expanduser("~"), ".paketik_profiles")

# ─────────────────────────────────────────────
#  Тайминги агента (секунды)
# ─────────────────────────────────────────────
DELAY_MIN       = 0.6
DELAY_MAX       = 2.2
SCREENSHOT_WAIT = 0.8
ACTION_RETRIES  = 3
AI_TIMEOUT      = 90   # таймаут AI-запроса, секунды (reasoning-модели думают долго)
AI_MAX_TOKENS   = 4096 # лимит вывода: reasoning-модели (deepseek-v4-pro) тратят
                       # часть токенов на размышление — нужен запас, иначе ответ
                       # обрезается (finish_reason=length) и JSON не доходит

# ─────────────────────────────────────────────
#  Browser zoom
# ─────────────────────────────────────────────
BROWSER_ZOOM = 0.75

# ─────────────────────────────────────────────
#  Лицензирование
# ─────────────────────────────────────────────
LICENSE_SERVER_URL = "https://license.example.com/api/v1"
APP_VERSION        = "4.7.1"

# ─────────────────────────────────────────────
#  Логирование
# ─────────────────────────────────────────────
LOG_FILE    = os.path.join(APP_DATA_DIR, "paketik.log")
LOG_LEVEL   = "DEBUG"

# ─────────────────────────────────────────────
#  Учётные записи
# ─────────────────────────────────────────────
ACCOUNTS_FILE = os.path.join(APP_DATA_DIR, "accounts.json")

# ─────────────────────────────────────────────
#  Автоматизация — таймауты (секунды)
# ─────────────────────────────────────────────
AUTH_TIMEOUT          = 30     # ожидание страницы авторизации
TESTS_LOAD_TIMEOUT    = 20     # ожидание загрузки списка тестов
START_BUTTON_TIMEOUT  = 15     # ожидание кнопки "ПРИСТУПИТЬ К ВЫПОЛНЕНИЮ"
CLEAR_SESSION_ON_START = False   # чистить cookies перед каждой авторизацией

# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────
WINDOW_TITLE  = f"Paketik  v{APP_VERSION}"
WINDOW_SIZE   = "920x680"
THEME         = "dark"
COLOR_ACCENT  = "#4A9EFF"

# ─────────────────────────────────────────────
#  Тиры лицензии и доступные модели
# ─────────────────────────────────────────────
TIER_MODELS = {
    1: [
        ("qwen/qwen3.5-flash-02-23",        "Qwen 3.5 Flash    (6/26 ₽)",          3.2),
        ("deepseek/deepseek-v4-flash",      "DeepSeek V4 Flash (13/27 ₽)",        3.6),
        ("deepseek/deepseek-v3.2",          "DeepSeek V3.2     (26/36 ₽)",        3.0),
    ],
    2: [
        ("qwen/qwen3.5-flash-02-23",        "Qwen 3.5 Flash    (6/26 ₽)",          3.2),
        ("deepseek/deepseek-v4-flash",      "DeepSeek V4 Flash (13/27 ₽)",        3.6),
        ("google/gemma-4-26b-a4b-it",       "Gemma 4 26B A4B   (5/32 ₽)",        4.0),
        ("deepseek/deepseek-v3.2",          "DeepSeek V3.2     (26/36 ₽)",        3.0),
        ("arcee-ai/trinity-large-thinking", "Arcee Trinity     (24/78 ₽)",        4.2),
    ],
    3: [
        ("qwen/qwen3.5-flash-02-23",        "Qwen 3.5 Flash    (6/26 ₽)",          3.2),
        ("deepseek/deepseek-v4-flash",      "DeepSeek V4 Flash (13/27 ₽)",        3.6),
        ("google/gemma-4-26b-a4b-it",       "Gemma 4 26B A4B   (5/32 ₽)",        4.0),
        ("deepseek/deepseek-v3.2",          "DeepSeek V3.2     (26/36 ₽)",        3.0),
        ("arcee-ai/trinity-large-thinking", "Arcee Trinity     (24/78 ₽)",        4.2),
        ("deepseek/deepseek-v4-pro",        "DeepSeek V4 Pro   (42/85 ₽)",        4.6),
        ("minimax/minimax-m2.7",            "MiniMax M2.7      (29/117 ₽)",       4.4),
    ],
}
TIER_NAMES  = {0: "Demo",   1: "Pro",     2: "Ultra",     3: "Ultimate"}
TIER_COLORS = {0: "#808090", 1: "#5c9cf5", 2: "#b06cf5",   3: "#3ddc97"}