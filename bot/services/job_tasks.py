import logging
from telegram.ext import ContextTypes
from bot.config import (
    EPL_TEAM_NAMES,
    PREDICT_DAYS_AHEAD,
    EPL_TOURNAMENT_CODE,
    SYNC_INTERVAL_SEC,
    PREDICT_INTERVAL_SEC,
    FIRST_SYNC_DELAY,
    FIRST_PREDICT_DELAY,
    DISABLE_JOBS,
)
from bot.services.roster import ensure_teams_exist, sync_multiple_teams
from bot.services.predictions import generate_predictions_for_upcoming_matches

logger = logging.getLogger(__name__)


# ------- Job Functions (async) ------- #

async def job_sync_rosters(context: ContextTypes.DEFAULT_TYPE):
    """Периодический синк ростеров всех EPL команд."""
    try:
        await ensure_teams_exist(EPL_TEAM_NAMES, tournament_code=EPL_TOURNAMENT_CODE)
        rep = await sync_multiple_teams(EPL_TEAM_NAMES, delay_between=3.5)
        logger.info("[JobQueue] Roster sync OK (truncated): %s", rep[:600])
    except Exception as e:
        logger.exception("[JobQueue] Roster sync failed: %s", e)


async def job_generate_predictions(context: ContextTypes.DEFAULT_TYPE):
    """Периодическая генерация предиктов для ближайших матчей."""
    try:
        updated = await generate_predictions_for_upcoming_matches(
            days_ahead=PREDICT_DAYS_AHEAD,
            tournament_code=EPL_TOURNAMENT_CODE
        )
        logger.info("[JobQueue] Predictions updated matches=%s", updated)
    except Exception as e:
        logger.exception("[JobQueue] Predictions generation failed: %s", e)


# ------- Registration Helper ------- #

def schedule_jobs(job_queue,
                  sync_interval_sec: int = SYNC_INTERVAL_SEC,
                  predict_interval_sec: int = PREDICT_INTERVAL_SEC,
                  first_sync_delay: int = FIRST_SYNC_DELAY,
                  first_predict_delay: int = FIRST_PREDICT_DELAY,
                  disabled: bool = DISABLE_JOBS):
    """
    Регистрирует повторяющиеся задачи в JobQueue PTB.
    """
    if disabled:
        logger.info("JobQueue disabled (DISABLE_JOBS=1).")
        return

    job_queue.run_repeating(
        job_sync_rosters,
        interval=sync_interval_sec,
        first=first_sync_delay,
        name="sync_rosters"
    )

    job_queue.run_repeating(
        job_generate_predictions,
        interval=predict_interval_sec,
        first=first_predict_delay,
        name="generate_predictions"
    )

    logger.info(
        "JobQueue tasks scheduled: sync=%ss (start+%ss) predict=%ss (start+%ss)",
        sync_interval_sec, first_sync_delay,
        predict_interval_sec, first_predict_delay
    )
