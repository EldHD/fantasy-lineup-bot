import os
from pathlib import Path

def _env(name: str, default=None, cast=str):
    val = os.getenv(name)
    if val is None or val == "":
        return default
    try:
        return cast(val)
    except Exception:
        return default

BASE_DIR = Path(__file__).resolve().parent.parent

# Telegram
TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("ENV TELEGRAM_TOKEN is not set")

LOG_LEVEL = _env("LOG_LEVEL", "INFO")

# Leagues
LEAGUE_CODES = ["epl", "laliga", "serie_a", "bundesliga", "ligue1", "rpl"]
LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "serie_a": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

# Transfermarkt competition codes
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "serie_a": "IT1",
    "bundesliga": "L1",
    "ligue1": "FR1",
    "rpl": "RU1",
}

TM_SEASON_YEAR = _env("TM_SEASON_YEAR", 2025, int)
SEASON_START_YEAR = TM_SEASON_YEAR  # alias
TM_MAX_MATCHDAY_SCAN = _env("TM_MAX_MATCHDAY_SCAN", 15, int)

TM_BASE_COM = "https://www.transfermarkt.com"
TM_BASE_WORLD = "https://www.transfermarkt.world"

TM_TIMEOUT = _env("TM_TIMEOUT", 15, int)
TM_RETRIES = _env("TM_RETRIES", 2, int)
TM_DELAY_BASE = _env("TM_DELAY_BASE", 0.9, float)

TM_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
]

TM_CALENDAR_DEBUG = _env("TM_CALENDAR_DEBUG", 0, int)

PREDICTIONS_LIMIT = _env("PREDICTIONS_LIMIT", 15, int)
