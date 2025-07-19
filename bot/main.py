import os
import asyncio
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.handlers import (
    start,
    handle_league_selection,
    handle_db_match_selection,
    handle_team_selection,
    back_to_leagues,
)
from bot.db.seed import auto_seed

TOKEN = os.environ["TELEGRAM_TOKEN"]


async def app_main():
    # 1. Автосид (создание таблиц и начальные данные)
    await auto_seed()

    # 2. Создаем приложение
    app = ApplicationBuilder().token(TOKEN).build()

    # 3. Регистрируем хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(back_to_leagues, pattern=r"^back_leagues$"))
    app.add_handler(CallbackQueryHandler(handle_league_selection, pattern=r"^league_"))
    app.add_handler(CallbackQueryHandler(handle_db_match_selection, pattern=r"^matchdb_"))
    app.add_handler(CallbackQueryHandler(handle_team_selection, pattern=r"^teamdb_"))

    print("Bot starting (polling)...")

    # 4. Запускаем polling “вручную”
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("Bot started. Waiting for updates...")
    # 5. Ждём завершения
    await app.updater.idle()
    # 6. Корректное завершение
    await app.stop()
    await app.shutdown()


def main():
    asyncio.run(app_main())


if __name__ == "__main__":
    main()
