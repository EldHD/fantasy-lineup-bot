import os
import logging
import asyncio
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
)
from bot.handlers import (
    start,
    ping,
    sync_roster_cmd,
    gen_demo_preds_cmd,
    handle_league_selection,
    handle_db_match_selection,
    handle_team_selection,
    back_to_leagues,
    debug_db,
    resync_all_cmd,
    export_lineup_cmd,
)
from bot.services.scheduler import start_scheduler
from bot.config import ENABLE_SCHEDULER

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")


def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

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
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")
    app = build_app()
    scheduler = start_scheduler()
    if ENABLE_SCHEDULER:
        logger.info("Scheduler enabled.")
    else:
        logger.info("Scheduler disabled (set ENABLE_SCHEDULER=1 to enable).")
    app.run_polling()


if __name__ == "__main__":
    main()
