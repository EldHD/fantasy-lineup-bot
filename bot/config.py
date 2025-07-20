import os

# -- env переменные на Railway --
DATABASE_URL   = os.environ["DATABASE_URL"]        # postgresql+asyncpg://…
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

# Transfermarkt
TM_COMP_CODES  = {"epl": "GB1"}                    # добавите лиги по мере надобности
SEASON_YEAR    = 2025
USER_AGENT     = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)
