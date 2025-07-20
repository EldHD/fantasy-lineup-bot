import os
from datetime import timedelta

# ================== TELEGRAM / BOT ==================
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")

# ================== DATABASE ==================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
)

# ================== ЛИГИ / ОТОБРАЖЕНИЕ ==================
LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

# Список кодов лиг, который используют хендлеры (в т.ч. для генерации кнопок)
LEAGUES = [
    "epl",
    "laliga",
    "seriea",
    "bundesliga",
    "ligue1",
    "rpl",
]

# Наборы команд по турнирам (минимум EPL сейчас, можно расширять позже)
TOURNAMENT_TEAMS = {
    "epl": [
        "arsenal",
        "aston_villa",
        "bournemouth",
        "brentford",
        "brighton_hove_albion",
        "chelsea",
        "crystal_palace",
        "everton",
        "fulham",
        "ipswich_town",
        "leicester_city",
        "liverpool",
        "manchester_city",
        "manchester_united",
        "newcastle_united",
        "nottingham_forest",
        "southampton",
        "tottenham_hotspur",
        "west_ham_united",
        "wolverhampton_wanderers",
    ],
    # Добавишь позже для остальных лиг
}

# ================== Transfermarkt КОНФИГ ==================
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",
    "ligue1": "FR1",
    "rpl": "RU1",
}

# Локальные slug-и на .world (может отличаться от англ.)
TM_WORLD_LOCAL_SLUG = {
    "epl": "premer-liga",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",
}

# Англ slug на .world
TM_WORLD_EN_SLUG = {
    "epl": "premier-league",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",
}

# Англ slug на .com
TM_COM_EN_SLUG = {
    "epl": "premier-league",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",
}

TM_BASE_WORLD = "https://www.transfermarkt.world"
TM_BASE_COM = "https://www.transfermarkt.com"

TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "15"))

TM_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

TM_CACHE_TTL = int(os.getenv("TM_CACHE_TTL", "900"))  # 15 мин

# Год начала сезона (2025 => сезон 2025/26)
SEASON_START_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))

# Сколько туров максимум сканируем для поиска ближайшего с несыгранными матчами
MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "8"))

# Включено ли получение матчей с Transfermarkt
USE_TRANSFERMARKT = os.getenv("USE_TRANSFERMARKT", "1") == "1"

# Сколько матчей выводить максимум
DEFAULT_MATCH_LIMIT = int(os.getenv("DEFAULT_MATCH_LIMIT", "15"))

# Задержка между запросами к TM (сек) в батчах при массовом синке
TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.5"))

# ================== ПЛАНИРОВАНИЕ (Job Queue / APS) ==================
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 3600)))         # 6 часов
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 3600 + 600)))  # 6 ч + 10 мин

SYNC_START_DELAY_SEC = int(os.getenv("SYNC_START_DELAY_SEC", "10"))
PREDICT_START_DELAY_SEC = int(os.getenv("PREDICT_START_DELAY_SEC", "40"))

# ================== ВЕРОЯТНОСТИ ==================
BASE_PROB_MIN = 40
BASE_PROB_MAX = 95

# ================== ПРОЧЕЕ ==================
DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "ru")

def ensure_bot_token():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set (env TELEGRAM_TOKEN)")

def config_summary() -> str:
    return (
        f"TM season_year={SEASON_START_YEAR} "
        f"MAX_MD_SCAN={MAX_MATCHDAY_SCAN} "
        f"USE_TM={USE_TRANSFERMARKT} "
        f"sync_interval={SYNC_INTERVAL_SEC}s "
        f"predict_interval={PREDICT_INTERVAL_SEC}s"
    )
