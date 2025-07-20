from typing import Tuple, List, Optional
import bot.config as cfg
from bot.external.transfermarkt_fixtures import fetch_current_matchday_upcoming

"""
API для хэндлеров:
- load_matches_for_league(league_code) -> (fixtures, error)
Фикстуры — список dict с ключами: match_id, home, away, dt_str, raw_date, raw_time, season
"""

async def load_matches_for_league(league_code: str, matchday: int = 1) -> Tuple[List[dict], Optional[str]]:
    fixtures, err, _debug = await fetch_current_matchday_upcoming(league_code, matchday=matchday)
    if err:
        return [], err
    return fixtures, None

def render_fixtures_text(league_code: str, fixtures: List[dict], matchday: int) -> str:
    league_name = cfg.LEAGUE_DISPLAY.get(league_code, league_code)
    if not fixtures:
        return f"Нет матчей (лига: {league_name})"
    lines = [f"Тур {matchday} ({league_name}):"]
    for fx in fixtures:
        lines.append(
            f"- {fx['home']} vs {fx['away']} {fx['dt_str'] or ''} #{fx['match_id'] or ''}"
        )
    return "\n".join(lines)
