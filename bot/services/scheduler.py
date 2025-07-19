from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import asyncio
from bot.config import (
    SYNC_INTERVAL_MIN,
    PREDICT_INTERVAL_MIN,
    ENABLE_SCHEDULER,
    EPL_TEAM_NAMES,
    PREDICT_DAYS_AHEAD,
)
from bot.services.roster import ensure_teams_exist, sync_multiple_teams
from bot.services.predictions import generate_predictions_for_upcoming_matches
from bot.db.database import SessionLocal
from bot.db.models import Tournament, Match
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)


async def job_sync_rosters():
    try:
        await ensure_teams_exist(EPL_TEAM_NAMES, tournament_code="epl")
        rep = await sync_multiple_teams(EPL_TEAM_NAMES)
        logger.info("[Scheduler] Roster sync done:\n%s", rep)
    except Exception as e:
        logger.exception("[Scheduler] Roster sync failed: %s", e)


async def job_generate_predictions():
    try:
        # Генерируем предикты для матчей в ближайшие N дней
        await generate_predictions_for_upcoming_matches(days_ahead=PREDICT_DAYS_AHEAD, tournament_code="epl")
        logger.info("[Scheduler] Predictions generation done.")
    except Exception as e:
        logger.exception("[Scheduler] Predictions generation failed: %s", e)


def start_scheduler():
    if not ENABLE_SCHEDULER:
        return None
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Первые задачи (через 10 сек после запуска) – мягкий старт
    scheduler.add_job(lambda: asyncio.create_task(job_sync_rosters()),
                      "date", run_date=datetime.utcnow() + timedelta(seconds=10),
                      id="initial_sync")

    scheduler.add_job(lambda: asyncio.create_task(job_generate_predictions()),
                      "date", run_date=datetime.utcnow() + timedelta(seconds=30),
                      id="initial_predict")

    # Периодические задачи
    scheduler.add_job(lambda: asyncio.create_task(job_sync_rosters()),
                      "interval", minutes=SYNC_INTERVAL_MIN,
                      id="periodic_sync")

    scheduler.add_job(lambda: asyncio.create_task(job_generate_predictions()),
                      "interval", minutes=PREDICT_INTERVAL_MIN,
                      id="periodic_predict")

    scheduler.start()
    return scheduler
