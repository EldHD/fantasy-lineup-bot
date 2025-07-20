from typing import List, Tuple, Optional, Dict

from bot.config import (
    DEFAULT_MATCH_LIMIT,
    LEAGUE_DISPLAY,
    USE_TRANSFERMARKT,
)
from bot.external.transfermarkt_fixtures import fetch_next_matchday_fixtures

MatchDict = Dict[str, str | int | None]


async def load_matches_for_league(
    league_code: str,
    *,
    limit: int | None = None
) -> Tuple[List[MatchDict], Optional[dict]]:
    limit = limit or DEFAULT_MATCH_LIMIT
    if USE_TRANSFERMARKT:
        fixtures, err = await fetch_next_matchday_fixtures(league_code, limit)
        if err:
            return [], err
        norm: List[MatchDict] = []
        for f in fixtures:
            norm.append({
                "id": f.get("id"),
                "home": f.get("home"),
                "away": f.get("away"),
                "ts": f.get("timestamp"),
                "date": f.get("date_str"),
                "time": f.get("time_str"),
                "matchday": f.get("matchday"),
            })
        return norm, None
    return [], {"message": "No enabled sources"}


def render_matches_text(league_code: str, matches: List[MatchDict]) -> str:
    disp = LEAGUE_DISPLAY.get(league_code, league_code)
    if not matches:
        return f"Нет матчей (лига: {disp})"
    md = matches[0].get("matchday")
    md_part = f"Тур {md}" if md else "Ближайшие матчи"
    lines = [f"{md_part} ({disp}):"]
    for m in matches:
        dt_part = ""
        if m.get("date") and m.get("time"):
            dt_part = f"{m['date']} {m['time']}"
        elif m.get("date"):
            dt_part = m["date"]
        id_part = f" #{m['id']}" if m.get("id") else ""
        lines.append(f"- {m['home']} vs {m['away']} {dt_part}{id_part}")
    return "\n".join(lines)


def render_no_matches_error(league_code: str, err: dict) -> str:
    disp = LEAGUE_DISPLAY.get(league_code, league_code)
    base = [f"Нет матчей (лига: {disp})"]
    msg = err.get("message")
    if msg:
        base.append(f"Причина: {msg}")

    md = err.get("matchday")
    if md:
        base.append(f"Матчдей: {md}")
    season_year = err.get("season_year")
    if season_year:
        base.append(f"Season start year: {season_year}")

    attempts = err.get("attempts") or []
    if attempts:
        base.append("Попытки:")
        for a in attempts:
            url =
