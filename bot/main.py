import os
import sys
import logging

from telegram import Update
from telegram.ext import Application

from bot.handlers import (
    get_handlers,
    error_handler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT TOKEN not set (env TELEGRAM_TOKEN или BOT_TOKEN)")

    app = Application.builder().token(token).build()

    # Регистрация хэндлеров
    for h in get_handlers():
        app.add_handler(h)

    # Глобальный обработчик ошибок
    app.add_error_handler(error_handler)

    return app


def main():
    app = build_application()
    logger.info("Bot starting polling...")
    # Достаточно просто вызвать run_polling() — allowed_updates не обязателен
    # (если хочется явно — можно: allowed_updates=Update.ALL_TYPES)
    app.run_polling()  # или: app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
