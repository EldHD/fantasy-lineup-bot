import os
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

from bot.handlers import (
    start,
    handle_league_selection,
    handle_db_match_selection,
    handle_team_selection,
    back_to_leagues,
)
from bot.db.seed import auto_seed

TOKEN = os.environ["TELEGRAM_TOKEN"]  # Убедись, что переменная добавлена в Railway
# DATABASE_URL должен быть в Variables вида:
# postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME

async def init_db():
    await auto_seed()

def main():
    # Выполним авто-сид синхронно до старта polling
    asyncio.run(init_db())

    app = ApplicationBuilder().token(TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", start))

    # Навигация
    app.add_handler(CallbackQueryHandler(back_to_leagues, pattern=r"^back_leagues$"))
    app.add_handler(CallbackQueryHandler(handle_league_selection, pattern=r"^league_"))
    app.add_handler(CallbackQueryHandler(handle_db_match_selection, pattern=r"^matchdb_"))
    app.add_handler(CallbackQueryHandler(handle_team_selection, pattern=r"^teamdb_"))

    print("Bot started (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
