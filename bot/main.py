"""
Точка входа бота.
Запускает авто-патч схемы БД, регистрирует хендлеры и начинает polling.
"""

import logging

from telegram.ext import ApplicationBuilder

from bot.config import TELEGRAM_TOKEN
from bot.handlers import register_handlers
from bot.db.patch_schema import run_sync as patch_schema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    # ── 1. Патчим БД (безопасно) ────────────────────
    logger.info("🔧 Проверка/патч схемы БД…")
    patch_schema()
    # ── 2. Запускаем Telegram-бота ───────────────────
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    logger.info("🤖 Bot starting polling…")
    app.run_polling()


if __name__ == "__main__":
    main()
