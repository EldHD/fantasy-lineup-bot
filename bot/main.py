import logging
import os

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.config import (
    BOT_TOKEN,
    SYNC_INTERVAL_SECONDS,
    PREDICT_INTERVAL_SECONDS,
    SYNC_INITIAL_DELAY,
    PREDICT_INITIAL_DELAY,
)

from bot.handlers import (
    start_cmd,
    league_callback,
    error_handler,
)
from bot.services.job_tasks import (
    job_sync_rosters,
    job_generate_predictions,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s:%(name)s:%(message)s")


def build_application():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN (или TELEGRAM_TOKEN) не задан в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))

    # Error handler
    app.add_error_handler(error_handler)

    # JobQueue
    jq = app.job_queue
    # Одноразовый старт через несколько секунд:
    jq.run_once(job_sync_rosters, when=SYNC_INITIAL_DELAY)
    jq.run_once(job_generate_predictions, when=PREDICT_INITIAL_DELAY)
    # Периодические:
    jq.run_repeating(job_sync_rosters, interval=SYNC_INTERVAL_SECONDS, first=SYNC_INTERVAL_SECONDS)
    jq.run_repeating(job_generate_predictions, interval=PREDICT_INTERVAL_SECONDS, first=PREDICT_INTERVAL_SECONDS)

    return app


def main():
    app = build_application()
    logger.info("Bot starting polling...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
