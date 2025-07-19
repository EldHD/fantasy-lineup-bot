import os
from datetime import timedelta

# Включение / выключение планировщика
ENABLE_SCHEDULER = os.environ.get("ENABLE_SCHEDULER", "0") == "1"

# Интервалы (в минутах) – можно переопределить переменными окружения
SYNC_INTERVAL_MIN = int(os.environ.get("SYNC_INTERVAL_MIN", "360"))      # 6h
PREDICT_INTERVAL_MIN = int(os.environ.get("PREDICT_INTERVAL_MIN", "390"))  # 6h30m

# Список клубов EPL для синка (Transfermarkt ID – будет использоваться transfermarkt.py)
EPL_TEAM_NAMES = [
    "Arsenal",
    "Aston Villa",
    "Bournemouth",
    "Brentford",
    "Brighton & Hove Albion",
    "Chelsea",
    "Crystal Palace",
    "Everton",
    "Fulham",
    "Ipswich Town",
    "Leicester City",
    "Liverpool",
    "Manchester City",
    "Manchester United",
    "Newcastle United",
    "Nottingham Forest",
    "Southampton",
    "Tottenham Hotspur",
    "West Ham United",
    "Wolverhampton Wanderers",
]

# Какой турнир-код у нас в таблице tournament для АПЛ (созданный раньше)
EPL_TOURNAMENT_CODE = "epl"

# Ограничение – сколько дней вперёд генерировать предикты
PREDICT_DAYS_AHEAD = int(os.environ.get("PREDICT_DAYS_AHEAD", "7"))
