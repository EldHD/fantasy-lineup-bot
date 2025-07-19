import asyncio
import logging
import random
from typing import List, Dict, Any

from bot.config import (
    TM_DELAY_BASE,
    TM_DELAY_JITTER,
    TOURNAMENT_TEAMS,
)

# Предполагаем, что функции синка и генерации уже есть в roster / predictions
# Если их нет — делаем безопасные заглушки.

try:
    from bot.services.roster import sync_multiple_teams
except ImportError:
    async def sync_multiple_teams(team_names: List[str], tournament_code: str = "epl",
                                  delay_between: float = 2.0) -> List[str]:
        # Возвращаем отчёт по каждой команде в формате строк
        await asyncio.sleep(0.1)
        return [f"{name}: dummy sync" for name in team_names]

try:
    from bot.services.predictions import regenerate_predictions_for_all_matches
except ImportError:
    async def regenerate_predictions_for_all_matches() -> int:
        await asyncio.sleep(0.1)
        return 0


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Вспом. функция: разбивает список на чанки
# -----------------------------------------------------------------------------
def chunked(seq: List[str], size: int) -> List[List[str]]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


# -----------------------------------------------------------------------------
# Задача: синк ростеров турнирных команд (используется JobQueue)
# context.job.data можно не использовать тут
# -----------------------------------------------------------------------------
async def job_sync_rosters(context) -> None:
    """
    Периодический синк ростеров всех известных команд (с задержками).
    context передаёт python-telegram-bot JobContext (можем не использовать).
    """
    # Для простоты — только EPL пока
    tournament_code = "epl"
    teams_map = TOURNAMENT_TEAMS.get(tournament_code, {}).get("teams", {})
    team_keys = list(teams_map.keys())
    if not team_keys:
        logger.info("[JobQueue] No teams configured for %s", tournament_code)
        return

    logger.info("[JobQueue] Roster sync started for %d teams", len(team_keys))

    batch_size = 4  # сколько команд за один под-батч
    for idx, group in enumerate(chunked(team_keys, batch_size), start=1):
        report_lines = []
        # Преобразуем slug -> display name для UI/логов
        display_names = [teams_map[k] for k in group]
        # Запускаем синк
        try:
            lines = await sync_multiple_teams(display_names, tournament_code=tournament_code,
                                              delay_between=TM_DELAY_BASE + random.uniform(0, TM_DELAY_JITTER))
            report_lines.extend(lines)
        except Exception as e:
            logger.exception("Batch %d error syncing teams %s", idx, group)
            report_lines.append(f"Batch {idx} unexpected error: {e}")

        logger.info("[JobQueue] Batch %d done: %s", idx, "; ".join(report_lines))

    logger.info("[JobQueue] Roster sync finished.")


# -----------------------------------------------------------------------------
# Задача: пересчёт предиктов
# -----------------------------------------------------------------------------
async def job_generate_predictions(context) -> None:
    try:
        updated = await regenerate_predictions_for_all_matches()
        logger.info("[JobQueue] Predictions updated matches=%s", updated)
    except Exception:
        logger.exception("Error in job_generate_predictions")
