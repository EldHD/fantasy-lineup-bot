import os
from datetime import timedelta

# ========= Бот / окружение =========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN") or ""
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN not set")

# ========= Лиги / коды =========
# Короткие внутренние коды (используем как callback data)
LEAGUE_CODES = ["epl", "laliga", "seriea", "bundes", "ligue1", "rpl"]

# Отображаемые названия
LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundes": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

# Коды соревнований на Transfermarkt (часть URL “wettbewerb/XXX”)
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundes": "L1",
    "ligue1": "FR1",
    "rpl": "RU1",
}

# Год начала сезона (для ?saison_id=)
SEASON_START_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))

# Сканируем туры от 1 до MAX_MATCHDAY_SCAN, пока не найдём ближайшие несыгранные матчи
MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "8"))

# HTTP настройки Transfermarkt
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "12"))
TM_MAX_RETRIES = int(os.getenv("TM_MAX_RETRIES", "2"))

# Базы (домены)
TM_BASE_COM = "https://www.transfermarkt.com"
TM_BASE_WORLD = "https://www.transfermarkt.world"

# Пользовательские агенты (будем рандомизировать)
TM_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
]

# Фича: ограничение количества итоговых матчей в выводе
MAX_OUTPUT_MATCHES = 15

# Интервалы фоновых задач (если используешь APS/JobQueue) – здесь просто как константы
SYNC_INTERVAL = timedelta(hours=6)
PREDICT_INTERVAL = timedelta(hours=6, minutes=10)

# Вкл/выкл verbose debug парсера
TM_CALENDAR_DEBUG = bool(int(os.getenv("TM_CALENDAR_DEBUG", "0")))
