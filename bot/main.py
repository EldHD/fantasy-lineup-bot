import asyncio
import logging

from telegram.ext import ApplicationBuilder

from bot.config import TELEGRAM_TOKEN
from bot.handlers import register_handlers
from bot.db.patch_schema import apply_async as patch_schema_async

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def main() -> None:
    # 1️⃣ создаём единый event-loop на всё приложение
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 2️⃣ патчим БД *в этом же* loop
    log.info("🔧 Проверка/патч схемы БД …")
    loop.run_until_complete(patch_schema_async())

    # 3️⃣ Telegram-бот — всё в том же loop
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    log.info("🤖 Bot starting polling …")
    app.run_polling()          # Application возьмёт уже текущий loop


if __name__ == "__main__":
    main()
