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
    "bundesliga": "L1",   # проверь соответствует ли твоему парсеру
    "ligue1": "FR1",
    "rpl": "RU1",
}

# (Опционально) список команд для синхронизации по лигам
TOURNAMENT_TEAMS = {
    "epl": [
        "arsenal", "aston_villa", "bournemouth", "brentford", "brighton_hove_albion",
        "chelsea", "crystal_palace", "everton", "fulham", "ipswich_town", "leicester_city",
        "liverpool", "manchester_city", "manchester_united", "newcastle_united",
        "nottingham_forest", "southampton", "tottenham_hotspur", "west_ham_united",
        "wolverhampton_wanderers"
    ],
    # при необходимости добавь для других лиг
}

# ------------------------------------------------------------------------------
# Transfermarkt – базовые домены и пути
# ------------------------------------------------------------------------------
TM_BASE_WORLD = os.getenv("TM_BASE_WORLD", "https://www.transfermarkt.world")
TM_BASE_COM = os.getenv("TM_BASE_COM", "https://www.transfermarkt.com")

# Шаблон пути «gesamtspielplan» (используется для полноформатного календаря)
# {slug} = локализованный slug лиги (например 'premier-league' или 'premer-liga')
# {code} = код турнира (GB1 и т.д.)
TM_GESAMTSPIELPLAN_PATH = "/{slug}/gesamtspielplan/wettbewerb/{code}"

# Параметры фильтрации по туру: ?saison_id=YYYY&spieltagVon=X&spieltagBis=Y
TM_QUERY_SEASON_PARAM = "saison_id"
TM_QUERY_MD_FROM = "spieltagVon"
TM_QUERY_MD_TO = "spieltagBis"

# ------------------------------------------------------------------------------
# ПАРАМЕТРЫ ПАРСЕРА КАЛЕНДАРЯ
# ------------------------------------------------------------------------------
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))

# Сколько подряд туров (matchdays) можно просмотреть вперёд/вниз при поиске
TM_MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "12"))

# Сколько матчдей одновременно пытаться грузить (если реализован параллелизм)
TM_MATCHDAY_PARALLEL = int(os.getenv("TM_MATCHDAY_PARALLEL", "2"))

# Расширенная отладка календаря
TM_CALENDAR_DEBUG = os.getenv("TM_CALENDAR_DEBUG", "0") == "1"

# Минимальное количество предстоящих матчей для остановки сканирования (если нужно)
TM_MIN_UPCOMING_STOP = int(os.getenv("TM_MIN_UPCOMING_STOP", "5"))

# ------------------------------------------------------------------------------
# HTTP / ЗАДЕРЖКИ
# ------------------------------------------------------------------------------
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20.0"))
TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.0"))  # базовая задержка между запросами
TM_DELAY_JITTER = float(os.getenv("TM_DELAY_JITTER", "1.3"))  # добавочный случайный разброс

# ------------------------------------------------------------------------------
# СИНХРОНИЗАЦИЯ / ПРЕДИКТЫ (Job Queue / Scheduler)
# ------------------------------------------------------------------------------
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 3600)))         # каждые 6 часов
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 3600 + 600)))  # +10 мин
FIRST_SYNC_DELAY_SEC = int(os.getenv("FIRST_SYNC_DELAY_SEC", "10"))
FIRST_PREDICT_DELAY_SEC = int(os.getenv("FIRST_PREDICT_DELAY_SEC", "40"))

# ------------------------------------------------------------------------------
# ПРОЧИЕ НАСТРОЙКИ ПРЕДИКТОВ (можешь расширять)
# ------------------------------------------------------------------------------
DEFAULT_PREDICTION_SOURCE = os.getenv("DEFAULT_PREDICTION_SOURCE", "baseline")

# ------------------------------------------------------------------------------
# УТИЛИТАРНЫЕ ФУНКЦИИ / ВСПОМОГАТЕЛЬНЫЕ
# ------------------------------------------------------------------------------
def get_transfermarkt_full_url(slug: str, code: str, season_year: int,
                               md_from: int | None = None, md_to: int | None = None) -> str:
    """
    Формирует полный URL (world-домен по умолчанию) для страницы календаря
    с опциональной фильтрацией по туру.
    """
    base = TM_BASE_WORLD  # можно переключать на COM если нужно
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
_missing = []
for name in ["LEAGUE_CODES", "LEAGUE_DISPLAY", "LEAGUE_TM_CODES"]:
    if name not in globals():
        _missing.append(name)
if _missing:
    logger.error("Config missing required constants: %s", ", ".join(_missing))
else:
    logger.debug("Config loaded. Leagues: %s", ", ".join(LEAGUE_CODES))
