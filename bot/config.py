import os
import logging

# ----------------------------------------------------------------------------------
# ЛОГИРОВАНИЕ
# ----------------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------
# TELEGRAM
# ----------------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN (или TELEGRAM_TOKEN) не задан – бот не запустится.")

# ----------------------------------------------------------------------------------
# БД (пример, адаптируй под себя)
# ----------------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host/dbname")

# ----------------------------------------------------------------------------------
# ЛИГИ / ОТОБРАЖЕНИЕ
# ----------------------------------------------------------------------------------
# Коды лиг (внутренние)
LEAGUE_CODES = ["epl", "laliga", "seriea", "bundesliga", "ligue1", "rpl"]

# Отображаемые имена
LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

# Transfermarkt коды турниров
LEAGUE_TM_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",      # (или "Bundesliga" зависит от твоего парсера – проверь)
    "ligue1": "FR1",
    "rpl": "RU1",
}

# При необходимости (если где-то ещё используется)
TOURNAMENT_TEAMS = {
    "epl": [
        "arsenal", "aston_villa", "bournemouth", "brentford", "brighton_hove_albion",
        "chelsea", "crystal_palace", "everton", "fulham", "ipswich_town", "leicester_city",
        "liverpool", "manchester_city", "manchester_united", "newcastle_united",
        "nottingham_forest", "southampton", "tottenham_hotspur", "west_ham_united",
        "wolverhampton_wanderers"
    ],
    # добавь остальные лиги при желании
}

# ----------------------------------------------------------------------------------
# ПАРАМЕТРЫ Transfermarkt ПАРСЕРА
# ----------------------------------------------------------------------------------
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))

# Сколько туров максимум сканировать, чтобы найти ближайший с будущими матчами
TM_MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "8"))

# Параллельные запросы (если используется в твоём fetch_sequential_matchdays)
TM_MATCHDAY_PARALLEL = int(os.getenv("TM_MATCHDAY_PARALLEL", "2"))

# Включить расширенный вывод отладки календаря (используй при проблемах)
TM_CALENDAR_DEBUG = os.getenv("TM_CALENDAR_DEBUG", "0") == "1"

# Базовый тайм-аут HTTPX (если используешь httpx)
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15.0"))

# ----------------------------------------------------------------------------------
# ПАРАМЕТРЫ РОСТЕРОВ / СИНХРОНИЗАЦИИ (если использовались раньше)
# ----------------------------------------------------------------------------------
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 3600)))          # 6h
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 3600 + 600)))

# Задержка между запросами к Transfermarkt (базовая) – если нужно
TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.0"))

# ----------------------------------------------------------------------------------
# ПРОЧЕЕ (если требуется)
# ----------------------------------------------------------------------------------
# Добавляй другие константы здесь
