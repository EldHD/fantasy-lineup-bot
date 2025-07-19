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
    force_seed_cmd, 
)
from bot.db.seed import auto_seed

TOKEN = os.environ["TELEGRAM_TOKEN"]  # проверь, что переменная есть в Railway


async def post_init(application):
    # 1. Чистим webhook, чтобы polling начал получать апдейты
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        print("Webhook cleared (drop_pending_updates=True).")
    except Exception as e:
        print("Webhook clear error:", e)

    # 2. Автосид (только если пусто)
    await auto_seed()
    print("DB init/seed done.")


def main():
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)  # вызовется автоматически перед стартом polling
        .build()
    )

    # Регистрируем handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(back_to_leagues, pattern=r"^back_leagues$"))
    application.add_handler(CallbackQueryHandler(handle_league_selection, pattern=r"^league_"))
    application.add_handler(CallbackQueryHandler(handle_db_match_selection, pattern=r"^matchdb_"))
    application.add_handler(CallbackQueryHandler(handle_team_selection, pattern=r"^teamdb_"))

    print("Starting bot (run_polling)...")
    # drop_pending_updates на случай, если накопились старые апдейты
    application.run_polling(
        allowed_updates=None,
        drop_pending_updates=True,
        stop_signals=None,   # Railway корректно завершит контейнер сам
    )


if __name__ == "__main__":
    main()
