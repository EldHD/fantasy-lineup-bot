import os
import logging
from telegram.ext import Application
from bot.config import BOT_TOKEN
from bot.handlers import register_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger(__name__)


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN / TELEGRAM_TOKEN not set")
    app = Application.builder().token(BOT_TOKEN).build()
    register_handlers(app)
    return app


def main():
    app = build_app()
    logger.info("Bot starting polling...")
    # Полноценный список allowed_updates сейчас не нужен – PTB сам определит.
    app.run_polling()


if __name__ == "__main__":
    main()
