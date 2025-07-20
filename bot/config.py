import os
import random
from datetime import timezone, timedelta

# ====== БАЗОВЫЕ НАСТРОЙКИ БОТА ======
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")  # в Railway переменная TELEGRAM_TOKEN
if not BOT_TOKEN:
    # позволяем стартануть, но логика main может упасть — там отдельная проверка
    pass

# ====== ЛИГИ / КОДЫ ======
# Внутренние короткие коды
LEAGUE_CODES = ["epl"]  # можно добавить: "laliga", "seriea", "bundes", "ligue1", "rpl"

LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundes": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "RPL",
}

# ====== Transfermarkt competition codes ======
# (на случай расширения)
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundes": "L1",
    "ligue1": "FR1",
    "rpl": "RU1",
}

# ====== СЕЗОН ======
# 2025 означает сезон 2025/26 (по TM параметру ?saison_id=2025)
TM_SEASON_YEAR = int(os.getenv("TM_SEASON_YEAR", "2025"))
SEASON_START_YEAR = TM_SEASON_YEAR  # алиас для обратной совместимости

# ====== БАЗОВЫЕ ДОМЕНЫ TM ======
# Раньше не хватало TM_BASE_COM — добавляем (классический домен .com)
TM_BASE_COM = "https://www.transfermarkt.com"
TM_BASE_WORLD = "https://www.transfermarkt.world"

# Порядок попыток при парсинге (страницы иногда отличаются локализацией)
TM_FIXTURE_URL_PATTERNS = [
    # full season (вдруг понадобится)
    "{base}/premier-league/gesamtspielplan/wettbewerb/{comp}/saison_id/{season}",
    # фильтр по туру (немецкая локализация)
    "{base}/premier-league/gesamtspielplan/wettbewerb/{comp}?saison_id={season}&spieltagVon={matchday}&spieltagBis={matchday}",
]

# ====== TIMEOUT / RETRIES ======
TM_TIMEOUT = float(os.getenv("TM_TIMEOUT", "18.0"))
TM_MAX_RETRIES = int(os.getenv("TM_MAX_RETRIES", "3"))
TM_RETRY_SLEEP_BASE = float(os.getenv("TM_RETRY_SLEEP_BASE", "2.0"))
TM_RETRY_SLEEP_JITTER = float(os.getenv("TM_RETRY_SLEEP_JITTER", "1.2"))

# Задержки между пакетами синка составов
TM_DELAY_BASE = float(os.getenv("TM_DELAY_BASE", "2.5"))
TM_DELAY_JITTER = float(os.getenv("TM_DELAY_JITTER", "1.6"))

# ====== USER-AGENTS ======
TM_USER_AGENTS = [
    # Можно добавить свои
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko)"
    " Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/123.0.0.0 Safari/537.36",
]

def pick_user_agent() -> str:
    return random.choice(TM_USER_AGENTS)

# ====== ПРЕДИКТЫ / МАТЧИ ======
DEFAULT_MAX_INLINE_BUTTONS = 15
DEFAULT_MATCH_LIMIT = 15

# Сколько туров подряд можем сканировать fallback’ом (если нужно — оставим, иначе не используется)
MAX_MATCHDAY_SCAN = int(os.getenv("MAX_MATCHDAY_SCAN", "6"))

# ====== ИНТЕРВАЛЫ JOB QUEUE ======
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", str(6 * 60 * 60)))            # 6h
PREDICT_INTERVAL_SEC = int(os.getenv("PREDICT_INTERVAL_SEC", str(6 * 60 * 60 + 600))) # 6h10m
FIRST_SYNC_DELAY_SEC = int(os.getenv("FIRST_SYNC_DELAY_SEC", "10"))
FIRST_PREDICT_DELAY_SEC = int(os.getenv("FIRST_PREDICT_DELAY_SEC", "40"))

# ====== ЧАСОВОЙ ПОЯС ======
LOCAL_TZ = timezone(timedelta(hours=0))  # пока в UTC

# ====== BACKWARD COMPATIBILITY ALIASES ======
# Если старый код где-то еще это дергает
LEAGUES = LEAGUE_CODES
TM_SEASON_START_YEAR = TM_SEASON_YEAR  # иногда упоминалось
