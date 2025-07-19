import os
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)
from bot.handlers import (
    start,
    handle_league_selection,
    handle_db_match_selection,
    handle_team_selection,
    back_to_leagues,
    force_seed_cmd,  # команда для пересоздания игроков/предиктов (опционально)
)
from bot.db.seed import auto_seed

TOKEN = os.environ["TELEGRAM_TOKEN"]  # переменная должна быть в Railway
# DATABASE_URL также в переменных окружения


async def post_init(app: Application):
    # Чистим webhook на всякий случай, чтобы polling работал
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        print("Webhook cleared.")
    except Exception as e:
        print("Webhook clear error:", e)

    # Создаём таблицы и, если нужно, сидируем
    await auto_seed()
    print("DB init / seed complete.")


def main():
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("force_seed", force_seed_cmd))  # опционально

    # Callback-и
    application.add_handler(CallbackQueryHandler(back_to_leagues, pattern=r"^back_leagues$"))
    application.add_handler(CallbackQueryHandler(handle_league_selection, pattern=r"^league_"))
    application.add_handler(CallbackQueryHandler(handle_db_match_selection, pattern=r"^matchdb_"))
    application.add_handler(CallbackQueryHandler(handle_team_selection, pattern=r"^teamdb_"))

    print("Starting bot (polling)...")
    application.run_polling(
        allowed_updates=None,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
