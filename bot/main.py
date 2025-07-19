import os
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import start, handle_league_selection

TOKEN = os.environ["TELEGRAM_TOKEN"]

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_league_selection, pattern=r'^league_'))

    print("Bot started (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
