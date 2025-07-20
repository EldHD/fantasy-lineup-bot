# main.py
import logging

from telegram.ext import Application, CommandHandler
from bot.config import TELEGRAM_TOKEN
from bot.db.patch_schema import apply_sync
from bot.handlers import start                 # <-- ваш коллбэк /start

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def main() -> None:
    apply_sync()                               # патч-upgrade БД (синхронно)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    log.info("🤖 Bot starting polling …")
    # ← run_polling() уже сам создаёт/закрывает цикл событий
    app.run_polling()


if __name__ == "__main__":
    main()
