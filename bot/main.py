import asyncio
import logging

from telegram.ext import ApplicationBuilder
from bot.config import TELEGRAM_TOKEN
from bot.handlers import register_handlers
from bot.db.patch_schema import apply_async as patch_schema_async

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s:%(name)s: %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    # единый event-loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # патчим БД до старта бота
    log.info("🔧 Проверка/патч схемы БД …")
    loop.run_until_complete(patch_schema_async())

    # Telegram-бот
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    log.info("🤖 Bot starting polling …")
    app.run_polling()          # использует тот же loop


if __name__ == "__main__":
    main()
