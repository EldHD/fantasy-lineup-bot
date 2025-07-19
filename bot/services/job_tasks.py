import logging
import random
from telegram.ext import ContextTypes
from bot.config import TM_DELAY_BASE, TOURNAMENT_TEAMS
from bot.services.roster import sync_multiple_teams
from bot.db.crud import generate_predictions_for_upcoming_matches  # Предполагаем что есть


logger = logging.getLogger(__name__)


async def job_sync_rosters(context: ContextTypes.DEFAULT_TYPE):
    """Периодический сбор ростеров для всех лиг из TOURNAMENT_TEAMS."""
    total_reports = []
    for code, teams in TOURNAMENT_TEAMS.items():
        # Разобьём на куски по 5 чтобы не спамить
        chunk_size = 5
        for i in range(0, len(teams), chunk_size):
            part = teams[i:i + chunk_size]
            rep = await sync_multiple_teams(
                part,
                delay_between=TM_DELAY_BASE + random.uniform(0.5, 1.2)
            )
            total_reports.append(f"[{code} {i//chunk_size + 1}] {rep}")
    logger.info("[JobQueue] Rosters sync done. Batches=%d", len(total_reports))


async def job_generate_predictions(context: ContextTypes.DEFAULT_TYPE):
    """Генерация (или обновление) предиктов по матчам."""
    updated_matches = await generate_predictions_for_upcoming_matches()
    logger.info("[JobQueue] Predictions updated matches=%d", updated_matches)
