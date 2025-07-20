"""
Глобальная конфигурация бота (расширенный универсальный config).

Содержит:
- Все ранее применявшиеся константы + алиасы.
- Дополнено SEASON_START_YEAR, SEASON_YEAR, CURRENT_SEASON_YEAR и т.п.
- Функции построения URL для календаря Transfermarkt.

Env переменные (основные):
  TELEGRAM_TOKEN / BOT_TOKEN
  DATABASE_URL
  TM_SEASON_YEAR (например 2025)
  LOG_LEVEL
  (опционально) TM_CALENDAR_DEBUG=1
"""

import os
import logging
import random
from typing import Dict, List, Optional

# ------------------------------------------------------------------------------
# ЛОГИРОВАНИЕ
# ------------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# TELEGRAM TOKEN
# ------------------------------------------------------------------------------
BOT_TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or ""
)
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN / TELEGRAM_TOKEN не задан – бот не запустится.")

# ------------------------------------------------------------------------------
# БАЗА ДАННЫХ
# ------------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@host/dbname"
)

# ------------------------------------------------------------------------------
# ЛИГИ / КОДЫ / DISPLAY
# ------------------------------------------------------------------------------
LEAGUE_CODES: List[str] = ["epl", "laliga", "seriea", "bundesliga", "ligue1", "rpl"]
LEAGUES = LEAGUE_CODES
ALL_LEAGUES = LEAGUE_CODES  # алиас

LEAGUE_DISPLAY: Dict[str, str] = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}
LEAGUE_NAMES = LEAGUE_DISPLAY  # алиас

LEAGUE_TM_CODES: Dict[str, str] = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",   # при необходимости скорректировать
    "ligue1": "FR1",
    "rpl": "RU1",
}
TM_COMP_CODES = dict(LEAGUE_TM_CODES)  # алиас

LEAGUE_SLUGS_COM: Dict[str, str] = {
    "epl": "premier-league",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",
}

LEAGUE_SLUGS_WORLD: Dict[str, str] = {
    "epl": "premier-league",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premer-liga",  # отличается
}

TRANSFERMARKT_SLUGS = {
    code: LEAGUE_SLUGS_WORLD.get(code) or LEAGUE_SLUGS_COM.get(code)
    for code in LEAGUE_CODES
}

# ------------------------------------------------------------------------------
# КОМАНДЫ (пока полный список EPL; другие можно добавить позже)
# ------------------------------------------------------------------------------
EPL_TEAM_NAMES: List[str] = [
    "arsenal", "aston_villa", "bournemouth", "brentford", "brighton_hove_albion",
    "chelsea", "crystal_palace", "everton", "fulham", "ipswich_town",
    "leicester_city", "liverpool", "manchester_city", "manchester_united",
    "newcastle_united", "nottingham_forest", "southampton", "tottenham_hotspur",
    "west_ham_united", "wolverhampton_wanderers"
]

TOURNAMENT_TEAMS = {
    "epl": EPL_TEAM_NAMES,
    # другие лиги позже
}

# ------------------------------------------------------------------------------
# ПАРАМЕТРЫ СЕЗОНА
# ------------------------------------------------------------------------------
# Основной год сезона (верхняя граница, как на TM – напр. 2025)
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))

# Алиасы, которые могут ожидаться кодом:
SEASON_YEAR = TM_SEASON_YEAR
CURRENT_SEASON_YEAR = TM_SEASON_YEAR
SEASON_START_YEAR = TM_SEASON_YEAR  # <-- добавлено по запросу (код его импортирует)

# Если где-то ожидают (например) START_YEAR:
START_YEAR = TM_SEASON_YEAR

# ------------------------------------------------------------------------------
# Transfermarkt базовые адреса и пути
# ------------------------------------------------------------------------------
TM_BASE_WORLD = os.getenv("TM_BASE_WORLD", "https://www.transfermarkt.world")
TM_BASE_COM = os.getenv("TM_BASE_COM", "https://www.transfermarkt.com")
TM_BASE = TM_BASE_WORLD
TM_FALLBACK_BASES = [TM_BASE_WORLD, TM_BASE_COM]

TM_GESAMTSPIELPLAN_PATH = "/{slug}/gesamtspielplan/wettbewerb/{code}"
TM_QUERY_SEASON_PARAM = "saison_id"
TM_QUERY_MD_FROM = "spieltagVon"
TM_QUERY_MD_TO = "spieltagBis"

# ------------------------------------------------------------------------------
# Сканирование туров
# ------------------------------------------------------------------------------
TM_MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "12"))
MAX_MATCHDAY_SCAN = TM_MAX_MATCHDAY_SCAN  # алиас

TM_MATCHDAY_PARALLEL = int(os.getenv("TM_MATCHDAY_PARALLEL", "2"))
TM_CALENDAR_DEBUG = os.getenv("TM_CALENDAR_DEBUG", "0") == "1"
TM_MIN_UPCOMING_STOP = int(os.getenv("TM_MIN_UPCOMING_STOP", "5"))

# ------------------------------------------------------------------------------
# HTTP / СЕТЬ
# ------------------------------------------------------------------------------
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "20.0"))
HTTP_TIMEOUT = TM_TIMEOUT
REQUEST_TIMEOUT = TM_TIMEOUT

TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.0"))
TM_DELAY_JITTER = float(os.getenv("TM_DELAY_JITTER", "1.3"))

TM_USER_AGENT = os.getenv(
    "TM_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

TM_USER_AGENTS: List[str] = [
    TM_USER_AGENT,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

def pick_user_agent() -> str:
    return random.choice(TM_USER_AGENTS)

TM_HEADERS = {
    "User-Agent": pick_user_agent(),
    "Accept-Language": os.getenv("TM_ACCEPT_LANGUAGE", "en-US,en;q=0.9,de;q=0.8,ru;q=0.7"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

# ------------------------------------------------------------------------------
# JOB QUEUE / ПЛАНИРОВАНИЕ
# ------------------------------------------------------------------------------
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 3600)))
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 3600 + 600)))

SYNC_INTERVAL_MIN = SYNC_INTERVAL_SEC // 60
PREDICT_INTERVAL_MIN = PREDICT_INTERVAL_SEC // 60

FIRST_SYNC_DELAY_SEC = int(os.getenv("FIRST_SYNC_DELAY_SEC", "10"))
FIRST_PREDICT_DELAY_SEC = int(os.getenv("FIRST_PREDICT_DELAY_SEC", "40"))

# ------------------------------------------------------------------------------
# ПРЕДИКТЫ / ФОРМАЦИИ
# ------------------------------------------------------------------------------
MIN_STARTERS = 11
DEFAULT_FORMATION_FALLBACK = os.getenv("DEFAULT_FORMATION_FALLBACK", "4-2-3-1")
DEFAULT_PREDICTION_SOURCE = os.getenv("DEFAULT_PREDICTION_SOURCE", "baseline")
FORMATION_PREFERENCE_ORDER = [
    "4-2-3-1", "4-3-3", "4-3-2-1", "4-4-2", "3-4-2-1", "3-4-3", "5-3-2"
]

# ------------------------------------------------------------------------------
# ИСТОЧНИКИ
# ------------------------------------------------------------------------------
SOURCE_PRIORITY = ["transfermarkt", "whoscored", "sofascore", "official", "twitter"]

# ------------------------------------------------------------------------------
# URL helpers
# ------------------------------------------------------------------------------
def get_transfermarkt_full_url(
    slug: str,
    code: str,
    season_year: int,
    md_from: Optional[int] = None,
    md_to: Optional[int] = None,
    base: Optional[str] = None
) -> str:
    base_url = base or TM_BASE_WORLD
    path = TM_GESAMTSPIELPLAN_PATH.format(slug=slug, code=code)
    query = f"?{TM_QUERY_SEASON_PARAM}={season_year}"
    if md_from is not None:
        query += f"&{TM_QUERY_MD_FROM}={md_from}"
    if md_to is not None:
        query += f"&{TM_QUERY_MD_TO}={md_to}"
    return base_url + path + query

def build_league_matchday_url(league_code: str, md: int) -> str:
    slug = TRANSFERMARKT_SLUGS.get(league_code, league_code)
    comp = LEAGUE_TM_CODES.get(league_code, "")
    return get_transfermarkt_full_url(
        slug=slug,
        code=comp,
        season_year=TM_SEASON_YEAR,
        md_from=md,
        md_to=md
    )

# ------------------------------------------------------------------------------
# ВАЛИДАЦИЯ
# ------------------------------------------------------------------------------
_required = [
    "LEAGUE_CODES", "LEAGUE_DISPLAY", "LEAGUE_TM_CODES",
    "TM_COMP_CODES", "TM_BASE_WORLD", "TM_BASE_COM", "TM_GESAMTSPIELPLAN_PATH",
    "TM_SEASON_YEAR", "SEASON_START_YEAR",
    "TM_MAX_MATCHDAY_SCAN", "TM_MATCHDAY_PARALLEL",
    "TM_TIMEOUT", "TM_DELAY_BASE", "TM_DELAY_JITTER",
    "TM_HEADERS", "TM_USER_AGENTS", "TRANSFERMARKT_SLUGS"
]
_missing = [n for n in _required if n not in globals()]
if _missing:
    logger.error("Config missing required constants: %s", ", ".join(_missing))
else:
    logger.debug("Config OK. Leagues: %s", ", ".join(LEAGUE_CODES))

logger.debug(
    "Intervals: sync=%ss (%sm), predict=%ss (%sm), first delays: sync=%ss predict=%ss",
    SYNC_INTERVAL_SEC, SYNC_INTERVAL_MIN,
    PREDICT_INTERVAL_SEC, PREDICT_INTERVAL_MIN,
    FIRST_SYNC_DELAY_SEC, FIRST_PREDICT_DELAY_SEC
)
logger.debug(
    "HTTP: timeout=%.1fs delay_base=%.2fs jitter=%.2fs user_agents=%d",
    TM_TIMEOUT, TM_DELAY_BASE, TM_DELAY_JITTER, len(TM_USER_AGENTS)
)
logger.debug("Season year=%s (aliases: SEASON_START_YEAR=%s)", TM_SEASON_YEAR, SEASON_START_YEAR)
