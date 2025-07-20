# bot/main.py  (фрагмент)

import asyncio
import logging
from telegram.ext import Application, CommandHandler
from bot.handlers import register_handlers
from bot.db.patch_schema import apply_async          # ← теперь async-версия
# -------------------------------------------------------------

async def start_bot() -> None:
    """Единая точка входа."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s: %(message)s")
    logging.getLogger(__name__).info("🔧 Проверка схемы БД …")
    await apply_async()                               # ждём патчей

    logging.getLogger(__name__).info("🤖 Bot starting polling …")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    # запускаем polling (в том же loop)
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    # приложение будет работать, пока его не остановят
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(start_bot())
