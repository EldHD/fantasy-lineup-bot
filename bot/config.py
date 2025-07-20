import os
from datetime import datetime, timezone

# --- BOT / DB ------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN (или TELEGRAM_TOKEN) не установлен")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
)

# --- Лиги ----------------------------------------------------
LEAGUES = ["epl", "laliga", "serie_a", "bundesliga", "ligue1", "rpl"]

LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "serie_a": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "Russian Premier League",
}

TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "serie_a": "IT1",
    "bundesliga": "L1",
    "ligue1": "FR1",
    "rpl": "RU1",
}

TM_WORLD_LOCAL_SLUG = {
    "epl": "premer-liga",
    "laliga": "laliga",
    "serie_a": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",
}

TM_WORLD_EN_SLUG = {
    "epl": "premier-league",
    "laliga": "laliga",
    "serie_a": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",
}
TM_COM_EN_SLUG = TM_WORLD_EN_SLUG.copy()

LEAGUE_MATCHES_PER_ROUND = {
    "epl": 10,
    "laliga": 10,
    "serie_a": 10,
    "bundesliga": 9,
    "ligue1": 9,
    "rpl": 8,
}

USE_TRANSFERMARKT = True
USE_SOFASCORE = False
SHOW_ONLY_NEXT_MATCHDAY = True

DEFAULT_MATCH_LIMIT = 60  # запас

TM_BASE_WORLD = "https://www.transfermarkt.world"
TM_BASE_COM = "https://www.transfermarkt.com"

TM_TIMEOUT = 25.0
TM_CACHE_TTL = 300
TM_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

TM_CALENDAR_DEBUG = os.getenv("TM_CALENDAR_DEBUG", "0") == "1"

SYNC_INTERVAL_SEC = 6 * 3600
PREDICT_INTERVAL_SEC = SYNC_INTERVAL_SEC + 600
JOB_INITIAL_DELAY_SYNC = 10
JOB_INITIAL_DELAY_PREDICT = 40


def _compute_season_start_year() -> int:
    env_year = os.getenv("TM_SEASON_YEAR")
    if env_year and env_year.isdigit():
        return int(env_year)
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 7 else now.year - 1


SEASON_START_YEAR = _compute_season_start_year()
