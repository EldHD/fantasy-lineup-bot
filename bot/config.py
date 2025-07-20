import os
import logging
import random
from typing import List, Dict

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
# TELEGRAM
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
# ЛИГИ / КОДЫ / ОТОБРАЖЕНИЕ
# ------------------------------------------------------------------------------
LEAGUE_CODES: List[str] = ["epl", "laliga", "seriea", "bundesliga", "ligue1", "rpl"]
LEAGUES = LEAGUE_CODES  # алиас

LEAGUE_DISPLAY: Dict[str, str] = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

LEAGUE_TM_CODES: Dict[str, str] = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",      # при необходимости поправь
    "ligue1": "FR1",
    "rpl": "RU1",
}

EPL_TEAM_NAMES: List[str] = [
    "arsenal", "aston_villa", "bournemouth", "brentford", "brighton_hove_albion",
    "chelsea", "crystal_palace", "everton", "fulham", "ipswich_town",
    "leicester_city", "liverpool", "manchester_city", "manchester_united",
    "newcastle_united", "nottingham_forest", "southampton", "tottenham_hotspur",
    "west_ham_united", "wolverhampton_wanderers"
]

TOURNAMENT_TEAMS = {
    "epl": EPL_TEAM_NAMES,
    # добавь остальные лиги по аналогии
}

# ------------------------------------------------------------------------------
# Transfermarkt – домены и пути
# ------------------------------------------------------------------------------
TM_BASE_WORLD = os.getenv("TM_BASE_WORLD", "https://www.transfermarkt.world")
TM_BASE_COM = os.getenv("TM_BASE_COM", "https://www.transfermarkt.com")
TM_BASE = TM_BASE_WORLD  # алиас

TM_GESAMTSPIELPLAN_PATH = "/{slug}/gesamtspielplan/wettbewerb/{code}"

TM_QUERY_SEASON_PARAM = "saison_id"
TM_QUERY_MD_FROM = "spieltagVon"
TM_QUERY_MD_TO = "spieltagBis"

# ------------------------------------------------------------------------------
# ПАРСЕР КАЛЕНДАРЯ / СЕЗОН
# ------------------------------------------------------------------------------
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))

TM_MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "12"))
MAX_MATCHDAY_SCAN = TM_MAX_MATCHDAY_SCAN  # алиас

TM_MATCHDAY_PARALLEL = int(os.getenv("TM_MATCHDAY_PARALLEL", "2"))
TM_CALENDAR_DEBUG = os.getenv("TM_CALENDAR_DEBUG", "0") == "1"
TM_MIN_UPCOMING_STOP = int(os.getenv("TM_MIN_UPCOMING_STOP", "5"))

# ------------------------------------------------------------------------------
# HTTP / ТАЙМАУТЫ / ЗАДЕРЖКИ / USER-AGENTS
# ------------------------------------------------------------------------------
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "20.0"))
HTTP_TIMEOUT = TM_TIMEOUT  # алиас

TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.0"))
TM_DELAY_JITTER = float(os.getenv("TM_DELAY_JITTER", "1.3"))

# Основной (по умолчанию) User-Agent
TM_USER_AGENT = os.getenv(
    "TM_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Новый список разных User-Agent для ротации (если код его импортирует)
TM_USER_AGENTS: List[str] = [
    TM_USER_AGENT,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

def pick_user_agent() -> str:
    """Возвращает случайный User-Agent из списка."""
    return random.choice(TM_USER_AGENTS)

TM_HEADERS = {
    "User-Agent": pick_user_agent(),
    "Accept-Language": os.getenv("TM_ACCEPT_LANGUAGE", "en-US,en;q=0.9,de;q=0.8"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ------------------------------------------------------------------------------
# СИНХРОНИЗАЦИЯ / ПРЕДИКТЫ (Job Queue)
# ------------------------------------------------------------------------------
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 3600)))              # 6h
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 3600 + 600)))  # 6h10m

SYNC_INTERVAL_MIN = int(SYNC_INTERVAL_SEC / 60)          # алиас для старого кода
PREDICT_INTERVAL_MIN = int(PREDICT_INTERVAL_SEC / 60)

FIRST_SYNC_DELAY_SEC = int(os.getenv("FIRST_SYNC_DELAY_SEC", "10"))
FIRST_PREDICT_DELAY_SEC = int(os.getenv("FIRST_PREDICT_DELAY_SEC", "40"))

# ------------------------------------------------------------------------------
# ПРЕДИКТЫ / ФОРМАЦИИ
# ------------------------------------------------------------------------------
DEFAULT_PREDICTION_SOURCE = os.getenv("DEFAULT_PREDICTION_SOURCE", "baseline")
DEFAULT_FORMATION_FALLBACK = os.getenv("DEFAULT_FORMATION_FALLBACK", "4-2-3-1")

# ------------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ------------------------------------------------------------------------------
def get_transfermarkt_full_url(
    slug: str,
    code: str,
    season_year: int,
    md_from: int | None = None,
    md_to: int | None = None,
    use_world: bool = True
) -> str:
    """
    Формирует полный URL (world или com) для страницы календаря c опциональной фильтрацией по турам.
    """
    base = TM_BASE_WORLD if use_world else TM_BASE_COM
    path = TM_GESAMTSPIELPLAN_PATH.format(slug=slug, code=code)
    query = f"?{TM_QUERY_SEASON_PARAM}={season_year}"
    if md_from is not None:
        query += f"&{TM_QUERY_MD_FROM}={md_from}"
    if md_to is not None:
        query += f"&{TM_QUERY_MD_TO}={md_to}"
    return base + path + query

# ------------------------------------------------------------------------------
# ВАЛИДАЦИЯ ОСНОВНЫХ КОНСТАНТ
# ------------------------------------------------------------------------------
_required = [
    "LEAGUE_CODES", "LEAGUE_DISPLAY", "LEAGUE_TM_CODES",
    "TM_BASE_WORLD", "TM_BASE_COM", "TM_GESAMTSPIELPLAN_PATH",
    "TM_SEASON_YEAR", "TM_MAX_MATCHDAY_SCAN", "TM_MATCHDAY_PARALLEL",
    "TM_TIMEOUT", "TM_DELAY_BASE", "TM_DELAY_JITTER", "TM_HEADERS", "TM_USER_AGENTS"
]
_missing = [n for n in _required if n not in globals()]
if _missing:
    logger.error("Config missing required constants: %s", ", ".join(_missing))
else:
    logger.debug("Config loaded OK. Leagues: %s", ", ".join(LEAGUE_CODES))

logger.debug(
    "Intervals: sync=%ss (%sm) predict=%ss (%sm) delays(base=%.2f, jitter=%.2f)",
    SYNC_INTERVAL_SEC, SYNC_INTERVAL_MIN,
    PREDICT_INTERVAL_SEC, PREDICT_INTERVAL_MIN,
    TM_DELAY_BASE, TM_DELAY_JITTER
)
