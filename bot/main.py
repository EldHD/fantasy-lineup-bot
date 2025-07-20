# bot/main.py  (полный файл)

import logging
from telegram.ext import Application
from bot.config import TELEGRAM_TOKEN
from bot.db.patch_schema import apply_sync   # ← остаётся sync-версия!

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s: %(message)s",
)

def main() -> None:
    logging.info("🔧 Проверка схемы БД …")
    apply_sync()                          # ← патчим таблицы (sync)

    logging.info("🤖 Bot starting polling …")
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # 👇 регистрируем обработчики
    from bot.handlers import register_handlers
    register_handlers(app)

    # единственная строка, которая *реально* запускает бота,
    # блокирует поток и держит event-loop до Ctrl-C
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
