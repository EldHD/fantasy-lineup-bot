import os
from datetime import timedelta

# ================== ОБЩЕЕ ==================
# Telegram Bot Token
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")

# Database URL (async)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
)

# ================== ЛИГИ ==================
# Внутренние коды лиг, которые мы используем в боте:
# epl = Premier League, laliga, seriea, bundesliga, ligue1, rpl
LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

# Если где-то используется набор команд (можно расширять позже)
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
    # Можно добавить аналогично для других лиг
}

# ================== ПАРСЕР ТУРНИРОВ (Transfermarkt) ==================
# Соответствие нашего кода лиги к коду соревнования на Transfermarkt
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",
    "ligue1": "FR1",
    "rpl": "RU1",
}

# Слага для англ/локальных версий (для разных доменов .world/.com)
# ".world" часто использует локализованные пути (пример для русской версии)
TM_WORLD_LOCAL_SLUG = {
    "epl": "premer-liga",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",
}

# Англ слага на world (иногда совпадает с local)
TM_WORLD_EN_SLUG = {
    "epl": "premier-league",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",
}

# Англ слага на .com (иногда отличается от world)
TM_COM_EN_SLUG = {
    "epl": "premier-league",
    "laliga": "laliga",
    "seriea": "serie-a",
    "bundesliga": "bundesliga",
    "ligue1": "ligue-1",
    "rpl": "premier-liga",  # на .com может отличаться, при необходимости поменять
}

TM_BASE_WORLD = "https://www.transfermarkt.world"
TM_BASE_COM = "https://www.transfermarkt.com"

# Таймаут httpx запросов
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "15"))

# User-Agent список (минимум несколько штук для ротации)
TM_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

# TTL кэша результатов (секунды)
TM_CACHE_TTL = int(os.getenv("TM_CACHE_TTL", "900"))

# Стартовый год сезона (2025 для сезона 2025/26)
SEASON_START_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))

# Сколько туров максимум сканируем, чтобы найти первый с несыгранными матчами
MAX_MATCHDAY_SCAN = int(os.getenv("TM_MAX_MATCHDAY_SCAN", "8"))

# Включить/выключить использование Transfermarkt как источника матчей
USE_TRANSFERMARKT = os.getenv("USE_TRANSFERMARKT", "1") == "1"

# Лимит матчей на вывод
DEFAULT_MATCH_LIMIT = int(os.getenv("DEFAULT_MATCH_LIMIT", "15"))

# ================== ПРЕДИКТЫ / РОСТЕРЫ ==================
# Базовая задержка между запросами к Transfermarkt (сек) в батчах
TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.5"))

# ================== ПЛАНИРОВАНИЕ (Job Queue / APS) ==================
# Интервал синхронизации ростеров (сек). Сейчас каждые 6 часов (6*3600=21600)
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 3600)))
# Интервал генерации предиктов (сек) — чуть смещён, чтобы не накладывалось
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 3600 + 600)))

# Можно также дать сдвиги старта (offset)
SYNC_START_DELAY_SEC = int(os.getenv("SYNC_START_DELAY_SEC", "10"))
PREDICT_START_DELAY_SEC = int(os.getenv("PREDICT_START_DELAY_SEC", "40"))

# ================== ПРОЧЕЕ ==================
# Локализация/язык (если понадобится)
DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "ru")

# Защитные параметры для генератора вероятностей
BASE_PROB_MIN = 40
BASE_PROB_MAX = 95

# ================== ВСПОМОГАТЕЛЬНЫЕ ==================
def ensure_bot_token():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set (env TELEGRAM_TOKEN)")

# Возвращает читабельную информацию (удобно для /debug)
def config_summary() -> str:
    return (
        f"Transfermarkt season_year={SEASON_START_YEAR}, "
        f"MAX_MD_SCAN={MAX_MATCHDAY_SCAN}, USE_TM={USE_TRANSFERMARKT}, "
        f"sync_interval={SYNC_INTERVAL_SEC}s, predict_interval={PREDICT_INTERVAL_SEC}s"
    )
