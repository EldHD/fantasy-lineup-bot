import asyncio, logging
from telegram.ext import ApplicationBuilder
from bot.config import TELEGRAM_TOKEN
from bot.handlers import register_handlers
from bot.db.patch_schema import apply_async

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s:%(name)s: %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    asyncio.run(start_bot())            # единая точка входа


async def start_bot() -> None:
    log.info("🔧 Проверка схемы БД …")
    await apply_async()                 # дождались, что всё ок

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    log.info("🤖 Bot starting polling …")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()


if __name__ == "__main__":
    main()
