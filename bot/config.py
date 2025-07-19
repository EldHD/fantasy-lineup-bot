import os

# ---------- Интервалы и задержки для фоновых задач (JobQueue) ----------
# Периодичность синка ростеров (в секундах). По умолчанию 6 часов.
SYNC_INTERVAL_SEC = int(os.environ.get("SYNC_INTERVAL_SEC", str(6 * 60 * 60)))  # 21600

# Периодичность генерации предиктов (в секундах). По умолчанию 6ч + 10 минут.
PREDICT_INTERVAL_SEC = int(os.environ.get("PREDICT_INTERVAL_SEC", str(6 * 60 * 60 + 600)))  # 22200

# Задержка перед первым автоматическим синком (сек)
FIRST_SYNC_DELAY = int(os.environ.get("FIRST_SYNC_DELAY", "10"))

# Задержка перед первой автогенерацией предиктов (сек)
FIRST_PREDICT_DELAY = int(os.environ.get("FIRST_PREDICT_DELAY", "40"))

# Установи DISABLE_JOBS=1 в переменных окружения, если хочешь полностью отключить автозадачи.
DISABLE_JOBS = os.environ.get("DISABLE_JOBS", "0") == "1"

# ---------- Константы турнир / охват ----------
EPL_TOURNAMENT_CODE = "epl"

# Сколько дней вперёд генерировать предикты (для job_generate_predictions)
PREDICT_DAYS_AHEAD = int(os.environ.get("PREDICT_DAYS_AHEAD", "7"))

# Полный список команд EPL (поддерживаемый синк)
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

# Можно позже добавить аналогичные списки для других лиг:
# LALIGA_TEAM_NAMES = [...]
# SERIEA_TEAM_NAMES = [...]
# и т.д.
