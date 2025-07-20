"""
config.py (LITE) — минимально необходимая конфигурация для текущего функционала:
- Лиги
- Парсинг ближайших матчей с Transfermarkt
- Синхронизация ростеров
- Планировщик предиктов
- Базовые параметры сети

Если нужен advanced вариант — расширим позже.
"""

import os
import logging
import random

# ------------------------------------------------------------------------------
# ЛОГИ
# ------------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger("config")

# ------------------------------------------------------------------------------
# TELEGRAM TOKEN
# ------------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN/TELEGRAM_TOKEN не задан — бот не сможет стартовать.")

# ------------------------------------------------------------------------------
# БАЗА ДАННЫХ
# ------------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host/dbname")

# ------------------------------------------------------------------------------
# ЛИГИ
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

# Transfermarkt competition codes
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",      # при необходимости скорректировать на актуальный код
    "ligue1": "FR1",
    "rpl": "RU1",
}

# Slugs (world / com можно унифицировать — использовать world)
TRANSFERMARKT_SLUGS = {
    "epl": "premier-league",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premer-liga",
}

# ------------------------------------------------------------------------------
# КОМАНДЫ для EPL (остальные добавим позже)
# ------------------------------------------------------------------------------
EPL_TEAM_NAMES = [
    "arsenal", "aston_villa", "bournemouth", "brentford", "brighton_hove_albion",
    "chelsea", "crystal_palace", "everton", "fulham", "ipswich_town",
    "leicester_city", "liverpool", "manchester_city", "manchester_united",
    "newcastle_united", "nottingham_forest", "southampton", "tottenham_hotspur",
    "west_ham_united", "wolverhampton_wanderers",
]
TOURNAMENT_TEAMS = {
    "epl": EPL_TEAM_NAMES
}

# ------------------------------------------------------------------------------
# СЕЗОН
# ------------------------------------------------------------------------------
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))
# алиас для кода, который ожидает SEASON_START_YEAR
SEASON_START_YEAR = TM_SEASON_YEAR

# ------------------------------------------------------------------------------
# Transfermarkt URL базовый и функции
# ------------------------------------------------------------------------------
TM_BASE_WORLD = os.getenv("TM_BASE_WORLD", "https://www.transfermarkt.world")
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "18.0"))
TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.0"))
TM_DELAY_JITTER = float(os.getenv("TM_DELAY_JITTER", "1.2"))

# User Agents
TM_USER_AGENTS = [
    os.getenv(
        "TM_USER_AGENT",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

def pick_user_agent():
    return random.choice(TM_USER_AGENTS)

# Для страниц конкретного тура на Transfermarkt используется параметр:
# .../gesamtspielplan/wettbewerb/GB1?saison_id=2025&spieltagVon=1&spieltagBis=1
def build_matchday_url(league_code: str, matchday: int) -> str:
    slug = TRANSFERMARKT_SLUGS.get(league_code, league_code)
    comp = TM_COMP_CODES.get(league_code, "")
    return (
        f"{TM_BASE_WORLD}/{slug}/gesamtspielplan/wettbewerb/{comp}"
        f"?saison_id={TM_SEASON_YEAR}&spieltagVon={matchday}&spieltagBis={matchday}"
    )

# ------------------------------------------------------------------------------
# ПЛАНИРОВЩИК
# (оставим интервалы простыми, можно менять через env)
# ------------------------------------------------------------------------------
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 3600)))
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 3600 + 600)))
FIRST_SYNC_DELAY_SEC = int(os.getenv("FIRST_SYNC_DELAY_SEC", "10"))
FIRST_PREDICT_DELAY_SEC = int(os.getenv("FIRST_PREDICT_DELAY_SEC", "40"))

# ------------------------------------------------------------------------------
# ПРЕДИКТЫ (минимум)
# ------------------------------------------------------------------------------
MIN_STARTERS = 11
DEFAULT_FORMATION_FALLBACK = "4-2-3-1"

# ------------------------------------------------------------------------------
# ПРОВЕРКА
# ------------------------------------------------------------------------------
logger.debug(
    "Config LITE loaded: leagues=%s season=%s base=%s",
    ",".join(LEAGUE_CODES), TM_SEASON_YEAR, TM_BASE_WORLD
)
