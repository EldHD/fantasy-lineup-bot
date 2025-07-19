import os
from typing import Dict, List, Any

# ============================================================================
# Загрузка токена
# ============================================================================
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    # Не падаем сразу: main.py может сам выбросить ошибку с понятным текстом
    pass

# ============================================================================
# База данных (asyncpg URL)
# Пример: postgresql+asyncpg://user:password@host:5432/dbname
# ============================================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/fantasy"
)

# ============================================================================
# Лиги (для клавиатуры)
# code должен совпадать с тем, что используешь в таблице tournaments.code
# ============================================================================
LEAGUES: Dict[str, Dict[str, Any]] = {
    "epl":     {"code": "epl",     "name": "Premier League"},
    "laliga":  {"code": "laliga",  "name": "La Liga"},
    "seriea":  {"code": "seriea",  "name": "Serie A"},
    "bundes":  {"code": "bundes",  "name": "Bundesliga"},
    "ligue1":  {"code": "ligue1",  "name": "Ligue 1"},
    "rpl":     {"code": "rpl",     "name": "Russian Premier League"},
}

# ============================================================================
# Список команд лиги (минимально для EPL). Здесь slug/код команды → отображаемое имя.
# Можно расширять для других лиг. Используется в массовом ресинке.
# ============================================================================
EPL_TEAMS: Dict[str, str] = {
    "arsenal": "Arsenal",
    "aston_villa": "Aston Villa",
    "bournemouth": "Bournemouth",
    "brentford": "Brentford",
    "brighton_hove_albion": "Brighton & Hove Albion",
    "chelsea": "Chelsea",
    "crystal_palace": "Crystal Palace",
    "everton": "Everton",
    "fulham": "Fulham",
    "ipswich_town": "Ipswich Town",
    "leicester_city": "Leicester City",
    "liverpool": "Liverpool",
    "manchester_city": "Manchester City",
    "manchester_united": "Manchester United",
    "newcastle_united": "Newcastle United",
    "nottingham_forest": "Nottingham Forest",
    "southampton": "Southampton",
    "tottenham_hotspur": "Tottenham Hotspur",
    "west_ham_united": "West Ham United",
    "wolverhampton_wanderers": "Wolverhampton Wanderers",
}

# Общая структура: код турнира → { "teams": {slug:display}, ... }
TOURNAMENT_TEAMS: Dict[str, Dict[str, Any]] = {
    "epl": {
        "teams": EPL_TEAMS
    },
    # При необходимости добавляй другие лиги аналогично:
    # "laliga": {"teams": {...}}
}

# ============================================================================
# Настройки задержек парсинга (Transfermarkt / SofaScore)
# ============================================================================
# Базовая задержка между запросами к TM (секунды)
TM_DELAY_BASE: float = float(os.getenv("TM_DELAY_BASE", "2.2"))
# Дополнительный максимум случайного разброса (0..TM_DELAY_JITTER)
TM_DELAY_JITTER: float = float(os.getenv("TM_DELAY_JITTER", "1.3"))

# Можно аналогично добавить для SofaScore при необходимости
SF_DELAY_BASE: float = float(os.getenv("SF_DELAY_BASE", "1.5"))
SF_DELAY_JITTER: float = float(os.getenv("SF_DELAY_JITTER", "0.8"))

# ============================================================================
# Интервалы задач (секунды)
# ============================================================================
SYNC_INTERVAL_SECONDS: int = int(os.getenv("SYNC_INTERVAL_SECONDS", str(6 * 60 * 60)))       # каждые 6 часов
PREDICT_INTERVAL_SECONDS: int = int(os.getenv("PREDICT_INTERVAL_SECONDS", str(6 * 60 * 60 + 600)))  # через 10 мин после синка

# Начальные отложенные старты (сек), чтобы бот успел подняться
SYNC_INITIAL_DELAY: int = int(os.getenv("SYNC_INITIAL_DELAY", "10"))
PREDICT_INITIAL_DELAY: int = int(os.getenv("PREDICT_INITIAL_DELAY", "40"))

# ============================================================================
# Экспорт / форматирование (можно расширять позже)
# ============================================================================
EXPORT_MAX_ROWS: int = int(os.getenv("EXPORT_MAX_ROWS", "200"))

# ============================================================================
# Прочее
# ============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
