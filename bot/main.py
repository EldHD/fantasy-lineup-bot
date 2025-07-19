import asyncio
import logging
import os
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler
)

from bot.config import BOT_TOKEN, SYNC_INTERVAL_SEC, PREDICT_INTERVAL_SEC
from bot.handlers import (
    start_cmd,
    handle_league_selection,
    handle_match_selection,
    handle_team_selection,
    back_to_leagues,
    back_to_matches,
    resync_all_cmd,
    sync_roster_cmd,
    modules_cmd,       # опционально /modules
)
from bot.services.job_tasks import (
    job_sync_rosters,
    job_generate_predictions,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger(__name__)


def build_application():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set (need TELEGRAM_TOKEN env var)")

    logger.info("Using bot token from env var: TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("resync_all", resync_all_cmd))
    app.add_handler(CommandHandler("sync_roster", sync_roster_cmd))
    app.add_handler(CommandHandler("modules", modules_cmd))

    # CallbackQuery
    app.add_handler(CallbackQueryHandler(handle_league_selection, pattern=r"^league:"))
    app.add_handler(CallbackQueryHandler(handle_match_selection, pattern=r"^match:"))
    app.add_handler(CallbackQueryHandler(handle_team_selection, pattern=r"^team:"))
    app.add_handler(CallbackQueryHandler(back_to_leagues, pattern=r"^back:leagues$"))
    app.add_handler(CallbackQueryHandler(back_to_matches, pattern=r"^back:matches:"))

    # Планирование через JobQueue (БЕЗ APScheduler)
    jq = app.job_queue

    # Добавим начальный однократный запуск слегка отложенный
    jq.run_once(job_sync_rosters, when=10)

    # Периодические
    jq.run_repeating(
        job_sync_rosters,
        interval=SYNC_INTERVAL_SEC,
        first=SYNC_INTERVAL_SEC + 30,  # чтобы не совпало с началом
        name="sync_rosters"
    )
    jq.run_repeating(
        job_generate_predictions,
        interval=PREDICT_INTERVAL_SEC,
        first=PREDICT_INTERVAL_SEC + 40,
        name="generate_predictions"
    )
    logger.info(
        "JobQueue tasks scheduled: sync=%ss predict=%ss",
        SYNC_INTERVAL_SEC, PREDICT_INTERVAL_SEC
    )
    return app


def main():
    app = build_application()
    logger.info("Bot starting polling...")
    app.run_polling(close_loop=False)  # PTB сам управляет loop


if __name__ == "__main__":
    main()
