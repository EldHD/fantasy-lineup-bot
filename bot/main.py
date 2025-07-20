# bot/main.py
import asyncio, logging
from telegram.ext import Application
from bot.handlers import register
from bot.db.patch_schema import apply_sync

from bot.config import TELEGRAM_TOKEN

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

async def start_bot():
    # 1) патч/создание схемы
    log.info("🔧 Проверка схемы БД …")
    apply_sync()           # обычная sync-версия

    # 2) сам бот
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    register(app)
    log.info("🤖 Bot starting polling …")
    await app.run_polling(close_loop=False)   # ← никаких .idle()

if __name__ == "__main__":
    asyncio.run(start_bot())
