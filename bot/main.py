import os
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.handlers import (
    start,
    ping,
    sync_roster_cmd,
    resync_all_cmd,
    gen_demo_preds_cmd,
    export_lineup_cmd,
    handle_league_selection,
    handle_db_match_selection,
    handle_team_selection,
    back_to_leagues,
    debug_db,
)
from bot.services.scheduler import start_scheduler
from bot.config import ENABLE_SCHEDULER

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_bot_token():
    """
    Ищем токен в нескольких ключах, чтобы не путаться.
    Приоритет: BOT_TOKEN > TELEGRAM_BOT_TOKEN > TELEGRAM_TOKEN
    """
    for key in ("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"):
        val = os.environ.get(key)
        if val:
            logger.info("Using bot token from env var: %s", key)
            return val
    return None


def build_app(bot_token: str):
    app = ApplicationBuilder().token(bot_token).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("sync_roster", sync_roster_cmd))
    app.add_handler(CommandHandler("resync_all", resync_all_cmd))
    app.add_handler(CommandHandler("gen_demo_preds", gen_demo_preds_cmd))
    app.add_handler(CommandHandler("export_lineup", export_lineup_cmd))
    app.add_handler(CommandHandler("debugdb", debug_db))

    # Callback query handlers
    app.add_handler(CallbackQueryHandler(back_to_leagues, pattern="^back_leagues$"))
    app.add_handler(CallbackQueryHandler(handle_league_selection, pattern="^league_"))
    app.add_handler(CallbackQueryHandler(handle_db_match_selection, pattern="^matchdb_"))
    app.add_handler(CallbackQueryHandler(handle_team_selection, pattern="^teamdb_"))

    return app


def main():
    token = _get_bot_token()
    if not token:
        env_keys_preview = ", ".join(sorted(list(os.environ.keys())[:25]))
        logger.error("BOT_TOKEN not set. First 25 env keys: %s", env_keys_preview)
        raise RuntimeError("BOT_TOKEN / TELEGRAM_TOKEN not set")

    app = build_app(token)
    scheduler = start_scheduler()
    if ENABLE_SCHEDULER:
        logger.info("Scheduler enabled.")
    else:
        logger.info("Scheduler disabled (set ENABLE_SCHEDULER=1 to enable).")

    logger.info("Bot starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
