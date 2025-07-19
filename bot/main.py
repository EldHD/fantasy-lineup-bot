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
)
from bot.db.seed import auto_seed

TOKEN = os.environ["TELEGRAM_TOKEN"]  # убедись, что переменная названа именно так


async def post_init(app: Application):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        print("Webhook cleared.")
    except Exception as e:
        print("Webhook clear err:", e)
    await auto_seed()
    print("DB init / seed complete.")


def main():
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))

    application.add_handler(CallbackQueryHandler(back_to_leagues, pattern=r"^back_leagues$"))
    application.add_handler(CallbackQueryHandler(handle_league_selection, pattern=r"^league_"))
    application.add_handler(CallbackQueryHandler(handle_db_match_selection, pattern=r"^matchdb_"))
    application.add_handler(CallbackQueryHandler(handle_team_selection, pattern=r"^teamdb_"))

    print("Starting bot (polling)...")
    application.run_polling(allowed_updates=None, drop_pending_updates=True)


if __name__ == "__main__":
    main()
