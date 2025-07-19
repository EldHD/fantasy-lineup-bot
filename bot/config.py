import os

# Telegram
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT_TOKEN")

# Интервалы (секунды)
def _int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, "").strip())
        if v > 0:
            return v
    except Exception:
        pass
    return default

SYNC_INTERVAL_SEC = _int("SYNC_INTERVAL_SEC", 6 * 60 * 60)          # 6 часов
PREDICT_INTERVAL_SEC = _int("PREDICT_INTERVAL_SEC", 6 * 60 * 60 + 600)  # 6ч10м

# Пауза между запросами к Transfermarkt (сек)
TM_DELAY_BASE = float(os.environ.get("TM_DELAY_BASE", "3.0"))

# Лимит игроков на парсинг (страховочный)
MAX_PLAYERS_PER_TEAM = int(os.environ.get("MAX_PLAYERS_PER_TEAM", "60"))

# Включить / отключить Sofascore (1 = отключить)
DISABLE_SOFASCORE = os.environ.get("DISABLE_SOFASCORE") == "1"

# Лиги / команды (упрощённо; для EPL полный список)
EPL_TEAM_NAMES = [
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton & Hove Albion",
    "Chelsea", "Crystal Palace", "Everton", "Fulham", "Ipswich Town",
    "Leicester City", "Liverpool", "Manchester City", "Manchester United",
    "Newcastle United", "Nottingham Forest", "Southampton",
    "Tottenham Hotspur", "West Ham United", "Wolverhampton Wanderers"
]

# Маппинг кода турнира → список команд (можно расширять)
TOURNAMENT_TEAMS = {
    "epl": EPL_TEAM_NAMES,
    # "laliga": [...],
    # "rpl": [...],
}
