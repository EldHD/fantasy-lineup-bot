import asyncio
import logging

from telegram.ext import ApplicationBuilder

from bot.config import TELEGRAM_TOKEN
from bot.handlers import register_handlers
from bot.db.patch_schema import run_sync as patch_schema

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def main() -> None:
    # 1) патчим таблицы ----------------------------------------------------
    log.info("🔧 Проверка/патч схемы БД …")
    patch_schema()

    # после asyncio.run() нужен новый loop
    asyncio.set_event_loop(asyncio.new_event_loop())

    # 2) запускаем Telegram-бота ------------------------------------------
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    log.info("🤖 Bot starting polling …")
    app.run_polling()


if __name__ == "__main__":
    main()
