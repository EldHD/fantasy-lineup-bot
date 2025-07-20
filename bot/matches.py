from typing import Tuple, List, Dict
from bot.external.transfermarkt_fixtures import fetch_current_matchday_upcoming
from bot.config import MAX_OUTPUT_MATCHES, LEAGUE_DISPLAY

Match = Dict[str, object]


async def load_matches_for_league(league_code: str, limit: int = None) -> Tuple[List[Match], Dict]:
    """
    Асинхронная обёртка над синхронным парсером.
    Возвращает (matches, meta_or_error).
    """
    if limit is None:
        limit = MAX_OUTPUT_MATCHES

    matches, meta = fetch_current_matchday_upcoming(league_code, limit=limit)

    if not matches:
        meta["error"] = meta.get("error") or _diagnostic_from_meta(meta, league_code)
    return matches, meta


def _diagnostic_from_meta(meta: Dict, league_code: str) -> str:
    if meta.get("match_count", 0) == 0:
        return "No matches parsed"
    return "Unknown"


def render_matches_text(league_code: str, matches: List[Match], meta: Dict) -> str:
    league_name = LEAGUE_DISPLAY.get(league_code, league_code)

    if not matches:
        attempts_lines = []
        for a in meta.get("attempts", [])[:6]:
            if "parsed" in a:
                attempts_lines.append(
                    f"- {a.get('url')} | md={a.get('md', '?')} | status={a['status']} | parsed={a['parsed']}"
                )
            else:
                attempts_lines.append(
                    f"- {a.get('url')} | status={a.get('status')} | error"
                )
        attempts_block = "\n".join(attempts_lines)
        parts = [
            f"Нет матчей (лига: {league_name})",
            f"Причина: {meta.get('error','')}",
            f"Season start year: {meta.get('season_start_year')}",
            f"Источник: {meta.get('source')}",
        ]
        if attempts_block:
            parts.append("Попытки:")
            parts.append(attempts_block)
        return "\n".join(parts)

    # Есть матчи
    lines = [f"Матчи (лига: {league_name}):"]
    for m in matches:
        mid = m.get("match_id") or "?"
        dt = m.get("dt_str") or ""
        lines.append(f"- {m['home']} vs {m['away']} {dt} #{mid}")
    return "\n".join(lines)
