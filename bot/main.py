# bot/main.py
import logging
from telegram.ext import ApplicationBuilder

from bot.config import TELEGRAM_TOKEN
from bot.handlers import handlers
from bot.db.patch_schema import apply_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s: %(message)s"
)

def main():
    apply_sync()  # применим патчи к базе перед стартом бота

    logging.info("🤖 Bot starting polling …")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    handlers(app)  # подключаем хендлеры команд
    app.run_polling()  # <-- работает синхронно, сам поднимает event loop

if __name__ == "__main__":
    main()
