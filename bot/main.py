import os
import logging
from datetime import timedelta
from typing import Optional

from telegram.ext import Application

# Хендлеры (в handlers.py должна быть функция register_handlers(app))
from bot.handlers import register_handlers

# Пытаемся импортировать задания (если есть)
try:
    from bot.services.job_tasks import job_sync_rosters, job_generate_predictions
    JOB_TASKS_AVAILABLE = True
except ImportError:
    JOB_TASKS_AVAILABLE = False

# --------- ЛОГИ ---------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning("Env %s=%r не int – используем %d", name, val, default)
        return default


def build_application() -> Application:
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN (или BOT_TOKEN) не задан")

    logger.info("Используем токен из env")

    app = Application.builder().token(token).build()

    # Регистрируем хендлеры
    register_handlers(app)

    # Настраиваем задачи (JobQueue)
    jq = app.job_queue
    if jq is None:
        # Теоретически не должно случиться в PTB>=20, но на всякий случай
        logger.warning("JobQueue недоступен – периодические задачи не будут запущены.")
        return app

    if JOB_TASKS_AVAILABLE:
        # Интервалы
        sync_interval = _env_int("SYNC_INTERVAL_SEC", 21600)         # 6 часов
        predict_interval = _env_int("PREDICT_INTERVAL_SEC", 22200)   # 6 ч 10 мин

        # Стартовые одноразовые (через небольшую задержку, чтобы бот успел подняться)
        jq.run_once(job_sync_rosters, when=10)     # первая синхронизация ростеров
        jq.run_once(job_generate_predictions, when=40)  # первая генерация предиктов

        # Периодические
        jq.run_repeating(
            job_sync_rosters,
            interval=sync_interval,
            first=sync_interval,   # следующая после интервала (или можно поставить фиксированное время)
            name="job_sync_rosters"
        )
        jq.run_repeating(
            job_generate_predictions,
            interval=predict_interval,
            first=predict_interval,
            name="job_generate_predictions"
        )

        logger.info(
            "JobQueue задачи зарегистрированы: sync=%ds predict=%ds",
            sync_interval, predict_interval
        )
    else:
        logger.warning(
            "Модуль job_tasks не найден – задачи синхронизации и предиктов не активированы."
        )

    return app


def main():
    app = build_application()

    # allowed_updates опционально – можно не указывать (PTB подтянет нужные)
    logger.info("Bot starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
