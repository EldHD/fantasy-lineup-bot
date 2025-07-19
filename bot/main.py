import os
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import (
    start,
    handle_league_selection,
    handle_match_selection,
    handle_team_selection,
    back_to_leagues,
)

TOKEN = os.environ["TELEGRAM_TOKEN"]

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(back_to_leagues, pattern="^back_leagues$"))
    app.add_handler(CallbackQueryHandler(handle_league_selection, pattern="^league_"))
    app.add_handler(CallbackQueryHandler(handle_match_selection, pattern="^match_"))
    app.add_handler(CallbackQueryHandler(handle_team_selection, pattern="^team_"))

    print("Bot started (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
