import os
from dataclasses import dataclass

# Телеграм
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")

# Базовый URL источника матчей (Sofascore – публичные JSONы)
SOFASCORE_BASE = "https://api.sofascore.com/api/v1"

# Коды турниров Sofascore (unique-tournament IDs)
SOFASCORE_TOURNAMENT_IDS = {
    "epl": 17,      # Premier League
    "laliga": 8,
    "serie_a": 23,
    "bundesliga": 35,
    "ligue1": 34,
    "rpl": 203,     # Russian Premier League
}

# Коды / отображаемые названия
LEAGUE_DISPLAY = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "serie_a": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "Russian Premier League",
}

# Настройки ограничений при запросах матчей
DEFAULT_MATCH_LIMIT = 15

# Настройки JobQueue / APScheduler (если задействованы)
SYNC_INTERVAL_SECONDS = 6 * 60 * 60        # 6 часов
PREDICT_INTERVAL_SECONDS = 6 * 60 * 60 + 600  # через 10 мин после синка

# Формат для логирования ошибок пользователю
END_USER_INTERNAL_ERROR_MESSAGE = "⚠️ Внутренняя ошибка. Сообщите администратору."
