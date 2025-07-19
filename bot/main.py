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
    ping,
    debug_catch_all,
)
from bot.db.seed import auto_seed

TOKEN = os.environ["TELEGRAM_TOKEN"]


async def post_init(app: Application):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        print("Webhook cleared.")
    except Exception as e:
        print("Webhook clear err:", e)
    await auto_seed()
    print("DB init / seed complete.")


async def error_handler(update, context):
    import traceback, sys
    print("=== ERROR HANDLER START ===")
    print("Update:", update)
    print("Exception:", context.error)
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__, file=sys.stdout)
    print("=== ERROR HANDLER END ===")
    try:
        if update and hasattr(update, "callback_query") and update.callback_query:
            await update.callback_query.edit_message_text("⚠️ Внутренняя ошибка. Попробуйте ещё раз.")
        elif update and update.effective_chat:
            await context.bot.send_message(update.effective_chat.id, "⚠️ Ошибка обработчика.")
    except Exception:
        pass


def main():
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))

    # Callback-и по паттернам
    application.add_handler(CallbackQueryHandler(back_to_leagues, pattern=r"^back_leagues$"))
    application.add_handler(CallbackQueryHandler(handle_league_selection, pattern=r"^league_"))
    application.add_handler(CallbackQueryHandler(handle_db_match_selection, pattern=r"^matchdb_"))
    application.add_handler(CallbackQueryHandler(handle_team_selection, pattern=r"^teamdb_"))

    # Catch-all (ставим ПОСЛЕ специфичных)
    application.add_handler(CallbackQueryHandler(debug_catch_all))

    application.add_error_handler(error_handler)

    print("Starting bot (polling)...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
