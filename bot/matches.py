from typing import List, Dict, Any, Tuple
from datetime import datetime

from bot.config import (
    LEAGUE_DISPLAY,
)
from bot.transfermarkt_fixtures import fetch_current_matchday_upcoming


def load_matches_for_league(league_code: str, limit: int = 15) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Синхронный интерфейс (парсер сейчас синхронный).
    Возвращает (matches, meta).
    """
    matches, meta = fetch_current_matchday_upcoming(league_code, limit=limit)
    return matches, meta


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
            for a in attempts[:5]:  # не спамим
                parts.append(f" - MD {a['md']}: status={a['status']} {a.get('err','')}")
        return "\n".join(parts)

    md = meta.get("matchday")
    title = f"Тур {md} ({display}):" if md else f"{display}:"
    lines = [title]
    for m in matches:
        dt: datetime = m.get("datetime")
        if dt:
            date_str = dt.strftime("%d/%m/%Y %H:%M")
        else:
            date_str = "TBD"
        lines.append(f"- {m['home']} vs {m['away']} {date_str} #{m['id']}")
    return "\n".join(lines)
