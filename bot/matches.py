from typing import List, Tuple, Optional, Dict, Any
import logging
from datetime import datetime
from bot.external.transfermarkt_fixtures import fetch_current_matchday_upcoming
from bot.config import SEASON_START_YEAR, MAX_MATCHDAY_SCAN

logger = logging.getLogger(__name__)

async def load_matches_for_league(league_code: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Возвращает список матчей (словарей):
      { match_id, home, away, kickoff (datetime|None) }
    или ошибку (строка).
    """
    matches, err = await fetch_current_matchday_upcoming(
        league_code,
        season_year=SEASON_START_YEAR,
        max_md=MAX_MATCHDAY_SCAN,
    )
    if err:
        return [], err
    return matches, None

def render_matches_text(league_display: str, matches: List[Dict[str, Any]]) -> str:
    if not matches:
        return f"Нет матчей (лига: {league_display})"
    # Определим тур — пока просто “Тур (лига)”
    # Если в будущем будем возвращать номер тура — можно добавить поле.
    lines = [f"Матчи (лига: {league_display}):"]
    for m in matches:
        dt = m.get("kickoff")
        if dt:
            # Приведём к удобному формату (UTC)
            lines.append(
                f"- {m['home']} vs {m['away']} "
                f"{dt.strftime('%d/%m/%Y %H:%M')} UTC "
                f"#{m['match_id']}"
            )
        else:
            lines.append(f"- {m['home']} vs {m['away']} (время TBC) #{m['match_id']}")
    return "\n".join(lines)
