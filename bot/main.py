import asyncio
from telegram.ext import ApplicationBuilder
import bot.config as cfg
from bot.handlers import register_handlers

def build_application():
    if not cfg.BOT_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN (BOT_TOKEN) не установлен в переменных окружения.")

    app = ApplicationBuilder().token(cfg.BOT_TOKEN).build()
    register_handlers(app)
    return app

def main():
    app = build_application()
    print("Bot starting polling...")
    # allowed_updates можно опустить; PTB сам решит
    app.run_polling()

if __name__ == "__main__":
    main()
