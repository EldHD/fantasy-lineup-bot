import logging
from telegram.ext import Application
from bot.config import TELEGRAM_TOKEN
from bot.handlers import register_handlers

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def build_app() -> Application:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN not set")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)
    return app

def main():
    app = build_app()
    log.info("Bot starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
