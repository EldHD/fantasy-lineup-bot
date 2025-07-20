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
    if md == "guessed":
        md_part = "Тур (оценка)"
    elif md and md != 10_000:
        md_part = f"Тур {md}"
    else:
        md_part = "Ближайшие матчи"
    lines = [f"{md_part} ({disp}):"]
    for m in matches:
        dt_part = ""
        if m.get("date") and m.get("time"):
            dt_part = f"{m['date']} {m['time']}"
        elif m.get("date"):
            dt_part = m["date"]
        elif m.get("time"):
            dt_part = m["time"]
        id_part = f" #{m['id']}" if m.get("id") else ""
        lines.append(f"- {m['home']} vs {m['away']} {dt_part}{id_part}")
    return "\n".join(lines)


def render_no_matches_error(league_code: str, err: dict) -> str:
    disp = LEAGUE_DISPLAY.get(league_code, league_code)
    base = [f"Нет матчей (лига: {disp})"]
    msg = err.get("message")
    if msg:
        base.append(f"Причина: {msg}")

    season_year = err.get("season_year")
    if season_year:
        base.append(f"Season start year: {season_year}")

    strat = err.get("selection_strategy")
    if strat:
        base.append(f"Selection strategy: {strat}")

    attempts = err.get("attempts") or []
    if attempts:
        base.append("Попытки:")
        for a in attempts:
            url = a.get("url")
            st = a.get("status")
            if "error" in a:
                base.append(f" - {url} | status={st} | error={a['error']}")
            else:
                base.append(
                    f" - {url} | status={st} | candidates={a.get('candidate_rows')} | parsed={a.get('parsed_matches')}"
                )
    errors = err.get("errors")
    if errors:
        base.append("Ошибки (первые):")
        for e in errors:
            base.append(f"   * {e}")

    if err.get("debug"):
        base.append(f"DEBUG: {err['debug']}")

    base.append("Источник: Transfermarkt (gesamtspielplan)")
    base.append("Советы: проверь опубликован ли календарь / TM_SEASON_YEAR / позже / другой IP / TM_CALENDAR_DEBUG=1.")
    return "\n".join(base)
