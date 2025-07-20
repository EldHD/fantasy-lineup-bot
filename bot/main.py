import logging
from telegram.ext import Application
from bot.config import TELEGRAM_TOKEN, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)


def build_application() -> Application:
    return Application.builder().token(TELEGRAM_TOKEN).build()


def main():
    app = build_application()
    from bot.handlers import register_handlers
    register_handlers(app)
    log.info("Bot starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
