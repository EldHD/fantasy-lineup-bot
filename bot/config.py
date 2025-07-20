import os
import logging

# ------------------------------------------------------------------------------
# ЛОГИРОВАНИЕ
# ------------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
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
LEAGUE_CODES = ["epl", "laliga", "seriea", "bundesliga", "ligue1", "rpl"]

LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

# Transfermarkt tournament codes
LEAGUE_TM_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",   # при необходимости поправь
    "ligue1": "FR1",
    "rpl": "RU1",
}

# Команды по турнирам (для массовой синхронизации)
TOURNAMENT_TEAMS = {
    "epl": [
        "arsenal", "aston_villa", "bournemouth", "brentford", "brighton_hove_albion",
        "chelsea", "crystal_palace", "everton", "fulham", "ipswich_town", "leicester_city",
        "liverpool", "manchester_city", "manchester_united", "newcastle_united",
        "nottingham_forest", "southampton", "tottenham_hotspur", "west_ham_united",
        "wolverhampton_wanderers"
    ],
    # добавляй остальные лиги по мере необходимости
}

# ------------------------------------------------------------------------------
# Transfermarkt – базовые домены и пути
# ------------------------------------------------------------------------------
TM_BASE_WORLD = os.getenv("TM_BASE_WORLD", "https://www.transfermarkt.world")
TM_BASE_COM = os.getenv("TM_BASE_COM", "https://www.transfermarkt.com")

# Шаблон пути общего календаря
TM_GESAMTSPIELPLAN_PATH = "/{slug}/gesamtspielplan/wettbewerb/{code}"

# Параметры query
TM_QUERY_SEASON_PARAM = "saison_id"
TM_QUERY_MD_FROM = "spieltagVon"
TM_QUERY_MD_TO = "spieltagBis"

# ------------------------------------------------------------------------------
# ПАРАМЕТРЫ ПАРСЕРА КАЛЕНДАРЯ / СЕЗОН
# ------------------------------------------------------------------------------
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))
TM_MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "12"))
TM_MATCHDAY_PARALLEL = int(os.getenv("TM_MATCHDAY_PARALLEL", "2"))
TM_CALENDAR_DEBUG = os.getenv("TM_CALENDAR_DEBUG", "0") == "1"
TM_MIN_UPCOMING_STOP = int(os.getenv("TM_MIN_UPCOMING_STOP", "5"))

# ------------------------------------------------------------------------------
# HTTP / ТАЙМАУТЫ / ЗАДЕРЖКИ
# ------------------------------------------------------------------------------
# Основной таймаут запросов к Transfermarkt.
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "20.0"))
# Для обратной совместимости, если где-то используется HTTP_TIMEOUT
HTTP_TIMEOUT = TM_TIMEOUT  # алиас
# Задержки (анти-бот / throttle)
TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.0"))
TM_DELAY_JITTER = float(os.getenv("TM_DELAY_JITTER", "1.3"))

# ------------------------------------------------------------------------------
# СИНХРОНИЗАЦИЯ / ПРЕДИКТЫ (Job Queue)
# ------------------------------------------------------------------------------
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 3600)))              # каждые 6 часов
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 3600 + 600)))  # +10 мин
FIRST_SYNC_DELAY_SEC = int(os.getenv("FIRST_SYNC_DELAY_SEC", "10"))
FIRST_PREDICT_DELAY_SEC = int(os.getenv("FIRST_PREDICT_DELAY_SEC", "40"))

# ------------------------------------------------------------------------------
# ПРЕДИКТЫ
# ------------------------------------------------------------------------------
DEFAULT_PREDICTION_SOURCE = os.getenv("DEFAULT_PREDICTION_SOURCE", "baseline")

# ------------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ------------------------------------------------------------------------------
def get_transfermarkt_full_url(slug: str, code: str, season_year: int,
                               md_from: int | None = None, md_to: int | None = None) -> str:
    """
    Формирует полный URL (world-домен по умолчанию) для страницы календаря
    с опциональной фильтрацией по турам.
    """
    base = TM_BASE_WORLD
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
    "TM_TIMEOUT", "TM_DELAY_BASE", "TM_DELAY_JITTER"
]
_missing = [n for n in _required if n not in globals()]
if _missing:
    logger.error("Config missing required constants: %s", ", ".join(_missing))
else:
    logger.debug("Config loaded OK. Leagues: %s", ", ".join(LEAGUE_CODES))
