import asyncio
import logging
import random
from typing import List

from bot.config import TOURNAMENT_TEAMS, TM_DELAY_BASE, TM_DELAY_JITTER
from bot.services.roster import sync_multiple_teams

# Если есть реальная функция генерации предиктов – импортируй её тут.
try:
    from bot.services.predictions import regenerate_predictions_for_all_matches
except ImportError:
    async def regenerate_predictions_for_all_matches() -> int:
        await asyncio.sleep(0.1)
        return 0

logger = logging.getLogger(__name__)


def chunked(seq: List[str], size: int) -> List[List[str]]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


async def job_sync_rosters(context) -> None:
    """
    Периодический синк ростеров всех команд EPL.
    """
    tournament_code = "epl"
    teams_map = TOURNAMENT_TEAMS.get(tournament_code, {}).get("teams", {})
    if not teams_map:
        logger.warning("[JobQueue] No teams in TOURNAMENT_TEAMS for %s", tournament_code)
        return

    team_display_names = list(teams_map.values())   # Берём отображаемые имена, т.к. ensure_teams_exist работает по name
    logger.info("[JobQueue] Roster sync started for %d teams", len(team_display_names))

    batch_size = 4
    for batch_idx, group in enumerate(chunked(team_display_names, batch_size), start=1):
        try:
            delay = TM_DELAY_BASE + random.uniform(0, TM_DELAY_JITTER)
            lines = await sync_multiple_teams(group, tournament_code=tournament_code, delay_between=delay)
            logger.info("[JobQueue] Batch %d done: %s", batch_idx, "; ".join(lines))
        except Exception as e:
            logger.exception("Batch %d failed", batch_idx)

    logger.info("[JobQueue] Roster sync finished.")


async def job_generate_predictions(context) -> None:
    try:
        updated = await regenerate_predictions_for_all_matches()
        logger.info("[JobQueue] Predictions updated matches=%s", updated)
    except Exception:
        logger.exception("Error in job_generate_predictions")
