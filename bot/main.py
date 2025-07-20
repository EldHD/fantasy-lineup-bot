import asyncio, logging
from telegram.ext import Application
from bot.config import TELEGRAM_TOKEN
from bot.db.patch_schema import apply_async
from bot.handlers import register_handlers

async def start_bot():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s:%(name)s: %(message)s")
    await apply_async()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(start_bot())
