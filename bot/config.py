import os
from dataclasses import dataclass

# Полный перечень лиг, который используем в интерфейсе
LEAGUES = {
    "EPL":     {"code": "epl",     "name": "Premier League"},
    "LALIGA":  {"code": "laliga",  "name": "La Liga"},
    "SERIEA":  {"code": "seriea",  "name": "Serie A"},
    "BUNDES":  {"code": "bundes",  "name": "Bundesliga"},
    "LIGUE1":  {"code": "ligue1",  "name": "Ligue 1"},
    "RPL":     {"code": "rpl",     "name": "Russian Premier League"},
}

# Пакетные настройки (пример — можно расширять)
DEFAULT_FORMATION = "4-2-3-1"

@dataclass
class Settings:
    bot_token: str

def load_settings() -> Settings:
    token = (
        os.getenv("TELEGRAM_TOKEN")
        or os.getenv("BOT_TOKEN")
        or ""
    )
    if not token:
        raise RuntimeError("BOT_TOKEN / TELEGRAM_TOKEN not set")
    return Settings(bot_token=token)
