import asyncio
from telegram.ext import Application
from bot.config import TELEGRAM_TOKEN
from bot.handlers import register_handlers

def build_application() -> Application:
    return Application.builder().token(TELEGRAM_TOKEN).build()

def main():
    app = build_application()
    register_handlers(app)
    print("Bot starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
