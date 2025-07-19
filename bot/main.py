import os
import logging
from datetime import timedelta

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

# Импорты твоих обработчиков
from bot.handlers import (
    start_cmd,
    league_callback,
    match_callback,
    team_callback,
    back_to_leagues_callback,
    back_to_matches_callback,
    sync_roster_cmd,
    resync_all_cmd,
    export_cmd,
)

# Задачи (jobs)
from bot.services.job_tasks import job_sync_rosters, job_generate_predictions

# Конфиг (если есть параметры интервалов там)
try:
    from bot.config import (
        SYNC_INTERVAL_MIN,
        PREDICT_INTERVAL_MIN,
    )
except ImportError:
    # fallback значения если не объявлены
    SYNC_INTERVAL_MIN = int(os.getenv("SYNC_INTERVAL_MIN", "360"))  # 6 часов
    PREDICT_INTERVAL_MIN = int(os.getenv("PREDICT_INTERVAL_MIN", "370"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
log = logging.getLogger(__name__)


def get_bot_token() -> str:
    """
    Приоритет: TELEGRAM_TOKEN (ты так назвал env), затем BOT_TOKEN.
    """
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Bot token not set (need TELEGRAM_TOKEN or BOT_TOKEN in env).")
    log.info("Using bot token from env var: %s", "TELEGRAM_TOKEN" if os.getenv("TELEGRAM_TOKEN") else "BOT_TOKEN")
    return token


def build_application():
    token = get_bot_token()

    app = Application.builder().token(token).build()

    # Регистрация команд
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("sync_roster", sync_roster_cmd))
    app.add_handler(CommandHandler("resync_all", resync_all_cmd))
    app.add_handler(CommandHandler("export", export_cmd))

    # CallbackQuery handlers
    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^LEAGUE:"))
    app.add_handler(CallbackQueryHandler(match_callback, pattern=r"^MATCH:"))
    app.add_handler(CallbackQueryHandler(team_callback, pattern=r"^TEAM:"))
    app.add_handler(CallbackQueryHandler(back_to_leagues_callback, pattern=r"^BACK:LEAGUES$"))
    app.add_handler(CallbackQueryHandler(back_to_matches_callback, pattern=r"^BACK:MATCHES:"))

    # JobQueue
    jq = app.job_queue
    if jq is None:
        # Это случится только если снова не установлены extras.
        log.warning("JobQueue is None (install extras: python-telegram-bot[job-queue]). "
                    "Периодические задачи НЕ будут работать.")
        return app

    # Одноразовые отложенные задачи (первый запуск после старта)
    jq.run_once(job_sync_rosters, when=10)       # через 10 сек после запуска
    jq.run_once(job_generate_predictions, when=40)

    # Периодические задачи
    jq.run_repeating(
        job_sync_rosters,
        interval=timedelta(minutes=SYNC_INTERVAL_MIN),
        first=timedelta(minutes=SYNC_INTERVAL_MIN)  # первый прогон через интервал (или поставь 0 для немедленного)
    )
    jq.run_repeating(
        job_generate_predictions,
        interval=timedelta(minutes=PREDICT_INTERVAL_MIN),
        first=timedelta(minutes=PREDICT_INTERVAL_MIN)
    )

    log.info(
        "JobQueue tasks scheduled: sync=%s min, predict=%s min",
        SYNC_INTERVAL_MIN, PREDICT_INTERVAL_MIN
    )
    return app


def main():
    app = build_application()
    log.info("Bot starting polling...")
    app.run_polling(close_loop=False)  # close_loop=False на всякий случай при Docker


if __name__ == "__main__":
    main()
