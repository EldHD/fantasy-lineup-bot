import os
from datetime import timedelta

# === Telegram ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# === Сезон ===
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", 2025))

# Лиги (внутренние коды)
LEAGUE_CODES = ["epl", "laliga", "serie_a", "bundesliga", "ligue1", "rpl"]

LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "serie_a": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

# Коды соревнований Transfermarkt
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "serie_a": "IT1",
    "bundesliga": "L1",
    "ligue1": "FR1",
    "rpl": "RU1",
}

# Соответствие кода лиги → код турнира в таблице tournaments
TOURNAMENT_CODE_MAP = {
    "epl": "epl",
    "laliga": "laliga",
    "serie_a": "serie_a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue1",
    "rpl": "rpl",
}

# === Парсер / сеть ===
TM_BASE_DOMAIN = os.getenv("TM_BASE_DOMAIN", "www.transfermarkt.com")
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", 15))
TM_REQUEST_DELAY_SEC = float(os.getenv("TM_REQUEST_DELAY_SEC", 0.4))
TM_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", 15))  # сколько туров сканируем

# === Кеширование матчей ===
FIXTURES_TTL_HOURS = int(os.getenv("FIXTURES_TTL_HOURS", 6))
FIXTURES_TTL = timedelta(hours=FIXTURES_TTL_HOURS)
FETCH_LIMIT_PER_LEAGUE = int(os.getenv("FETCH_LIMIT_PER_LEAGUE", 15))

# === База данных ===
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql+asyncpg://user:pass@host:port/db

# === Локальные настройки логики ===
# Можно расширять при необходимости.
