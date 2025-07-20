import logging
import time
from typing import List, Dict, Tuple, Optional

from bot.external.sofascore import (
    get_or_guess_season_id,
    fetch_upcoming_matches,
)

logger = logging.getLogger(__name__)

# Карта наших кодов лиг → SofaScore unique tournament id + ENV для season fallback
TOURNAMENT_MAP = {
    "epl": {
        "unique_tournament_id": 17,
        "season_env": "EPL_SEASON_ID",
        "pretty_name": "Premier League",
    },
    # При необходимости добавите остальные лиги тут
}

def _format_error(debug: Dict[str, any], reason: str) -> str:
    lines = []
    tid = debug.get("tournament_id")
    lines.append(f"Причина: {reason}")
    lines.append(f"Season ID: {debug.get('season_id')}")
    lines.append("Шаги:")
    for st in debug.get("steps", []):
        lines.append(f" - {st}")
    return "\n".join(lines)


async def load_matches_for_league(league_code: str, limit: int = 15) -> Tuple[List[Dict], Optional[str]]:
    """
    Возвращает (matches, error_message_or_none).
    matches = список словарей {home, away, startTimestamp, ...}
    """
    t0 = time.time()
    conf = TOURNAMENT_MAP.get(league_code.lower())
    if not conf:
        return [], f"Неизвестная лига: {league_code}"

    ut_id = conf["unique_tournament_id"]
    season_env = conf["season_env"]

    season_id, debug_season = await get_or_guess_season_id(ut_id, fallback_env_name=season_env)
    if not season_id:
        reason = "Не удалось получить список сезонов (403 / блок или нет ENV fallback)"
        err_txt = (
            f"Нет матчей (лига: {league_code})\n"
            f"{_format_error(debug_season, reason)}\n"
            f"Подсказка: установите переменную окружения {season_env}=<числовой_id_сезона>"
        )
        return [], err_txt

    matches, debug_matches, err_matches = await fetch_upcoming_matches(ut_id, season_id, limit=limit)
    if err_matches or not matches:
        err_txt = (
            f"Нет матчей (лига: {league_code})\n"
            f"Season ID: {season_id}\n"
            f"Причина: {err_matches}\n"
            f"Попытки: {debug_matches.get('attempts')}"
        )
        return [], err_txt

    dt = time.time() - t0
    logger.info("Loaded %d matches for %s in %.2fs (season=%s)",
                len(matches), league_code, dt, season_id)
    return matches, None
