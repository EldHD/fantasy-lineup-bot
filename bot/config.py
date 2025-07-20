import os
from datetime import datetime, timezone

# -------------------------------------------------
# Базовые переменные окружения
# -------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN (или TELEGRAM_TOKEN) не установлен")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres")

# -------------------------------------------------
# Лиги / турниры (внутренние коды)
# -------------------------------------------------
LEAGUES = ["epl", "laliga", "serie_a", "bundesliga", "ligue1", "rpl"]

LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "serie_a": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "Russian Premier League",
}

# -------------------------------------------------
# Transfermarkt: коды соревнований
# (см. URL: /wettbewerb/<CODE>/…)
# -------------------------------------------------
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "serie_a": "IT1",
    "bundesliga": "L1",     # Да, Bundesliga = L1 на TM
    "ligue1": "FR1",
    "rpl": "RU1",
}

# Максимально сколько матчей показываем пользователю
DEFAULT_MATCH_LIMIT = 15

# -------------------------------------------------
# Флаги источников
# -------------------------------------------------
USE_SOFASCORE = False        # отключили
USE_TRANSFERMARKT = True     # включили

# -------------------------------------------------
# Transfermarkt парсер – настройки
# -------------------------------------------------
TM_BASE = "https://www.transfermarkt.com"
TM_TIMEOUT = 18.0
TM_MAX_MATCHDAYS_LOOKAHEAD = 6     # сколько вперёд матчдей поглядим
TM_REQUEST_DELAY_BASE = 0.8        # базовая пауза между запросами (сек.)
TM_RANDOM_JITTER = 0.6             # случайный разброс
TM_CACHE_TTL = 300                 # кэширование матчей (сек.)

# User-Agent пул
TM_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

# -------------------------------------------------
# Планировщик / Jobs (оставляем как было, если нужно)
# -------------------------------------------------
SYNC_INTERVAL_SEC = 6 * 3600         # 6 часов
PREDICT_INTERVAL_SEC = SYNC_INTERVAL_SEC + 600  # +10 минут
JOB_INITIAL_DELAY_SYNC = 10
JOB_INITIAL_DELAY_PREDICT = 40

# -------------------------------------------------
# Вспомогательные
# -------------------------------------------------
def current_season_start_year() -> int:
    """
    На Transfermarkt сезон помечается стартовым годом.
    Если сейчас месяц >= 7 (июль или позже) – используем текущий год,
    иначе год - 1.
    """
    now = datetime.now(timezone.utc)
    if now.month >= 7:
        return now.year
    return now.year - 1

SEASON_START_YEAR = current_season_start_year()
