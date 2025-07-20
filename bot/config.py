# bot/config.py
import os
from datetime import timedelta

# -------------------------------------------------
# Общие / инфраструктура
# -------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "PUT_YOUR_TOKEN_HERE")

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/fantasy"
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# -------------------------------------------------
# Лиги / отображение
# -------------------------------------------------
# Внутренний код -> человекочитаемое название
LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "Russian Premier League",
}

# Порядок показа в меню
LEAGUE_ORDER = ["epl", "laliga", "seriea", "bundesliga", "ligue1", "rpl"]

# Обратная мапа (если нужно быстро получить код по отображаемому названию)
DISPLAY_TO_CODE = {v: k for k, v in LEAGUE_DISPLAY.items()}

# Для хэндлеров (чтобы легко получить список кодов)
LEAGUE_CODES = list(LEAGUE_DISPLAY.keys())

# -------------------------------------------------
# Transfermarkt / парсинг матчей
# -------------------------------------------------
# Код соревнования на TM для каждой лиги
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",    # На TM Bundesliga обычно "L1"
    "ligue1": "FR1",
    "rpl": "RU1",
}

# Базовые домены (иногда используем для fallback)
TM_BASE_COM   = "https://www.transfermarkt.com"
TM_BASE_WORLD = "https://www.transfermarkt.world"

# Стартовый *первый* год сезона (2025 для сезона 2025/26)
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))

# Сколько туров максимум сканируем в поиске «текущего / ближайшего» тура
TM_MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "12"))

# Таймаут HTTP
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "15"))

# Основные заголовки для запросов (минимум User-Agent)
TM_HEADERS = {
    "User-Agent": os.getenv(
        "TM_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 FantasyBot/1.0"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Пул User-Agent’ов (если захочешь рандомизировать)
TM_USER_AGENTS = [
    TM_HEADERS["User-Agent"],
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Паузы между запросами при батч-синке составов с TM
TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "1.2"))  # базовая часть
TM_DELAY_JITTER = float(os.getenv("TM_DELAY_JITTER", "0.8"))  # случайная добавка

# Флаг дополнительной отладки календаря
TM_CALENDAR_DEBUG = os.getenv("TM_CALENDAR_DEBUG", "0") == "1"

# -------------------------------------------------
# Ростеры / синк игроков (пример — адаптируй под твой код)
# -------------------------------------------------
SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "6"))
PREDICT_INTERVAL_HOURS = int(os.getenv("PREDICT_INTERVAL_HOURS", "6"))

# -------------------------------------------------
# Предикты (заглушки — если нужно)
# -------------------------------------------------
PREDICTION_LOOKAHEAD_DAYS = int(os.getenv("PREDICTION_LOOKAHEAD_DAYS", "14"))

# -------------------------------------------------
# Кэш, лимиты, прочее (если нужно в будущем)
# -------------------------------------------------
HTTP_RETRY = int(os.getenv("HTTP_RETRY", "2"))

# -------------------------------------------------
# Утилиты
# -------------------------------------------------
def get_league_name(code: str) -> str:
    return LEAGUE_DISPLAY.get(code, code)

def is_valid_league(code: str) -> bool:
    return code in LEAGUE_DISPLAY

# (Пример функции для вычисления границ времени, если нужно)
def sync_interval_timedelta() -> timedelta:
    return timedelta(hours=SYNC_INTERVAL_HOURS)
