from typing import List, Dict, Any, Tuple
from datetime import datetime

from bot.config import LEAGUE_DISPLAY
from bot.external.transfermarkt_fixtures import fetch_current_matchday_upcoming

def load_matches_for_league(league_code: str, limit: int = 15) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return fetch_current_matchday_upcoming(league_code, limit=limit)

def render_matches_text(league_code: str, matches: List[Dict[str, Any]], meta: Dict[str, Any]) -> str:
    display = LEAGUE_DISPLAY.get(league_code, league_code)
    if not matches:
        err = meta.get("error", "No matches")
        attempts = meta.get("attempts", [])
        parts = [f"Нет матчей (лига: {display})", f"Причина: {err}"]
        if "season_year" in meta:
            parts.append(f"Season: {meta['season_year']}")
        if attempts:
            parts.append("Попытки:")
            for a in attempts[:5]:
                parts.append(f" - MD {a['md']}: status={a['status']} {a.get('err','')}")
        return "\n".join(parts)

    md = meta.get("matchday")
    title = f"Тур {md} ({display}):" if md else f"{display}:"
    lines = [title]
    for m in matches:
        dt: datetime = m.get("datetime")
        ds = dt.strftime("%d/%m/%Y %H:%M") if dt else "TBD"
        lines.append(f"- {m['home']} vs {m['away']} {ds} #{m['id']}")
    return "\n".join(lines)
