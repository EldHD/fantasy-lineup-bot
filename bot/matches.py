from typing import List, Tuple, Optional, Dict

from bot.config import (
    DEFAULT_MATCH_LIMIT,
    LEAGUE_DISPLAY,
    USE_TRANSFERMARKT,
)
from bot.external.transfermarkt_fixtures import fetch_transfermarkt_fixtures

MatchDict = Dict[str, str | int | None]


async def load_matches_for_league(
    league_code: str,
    *,
    limit: int | None = None
) -> Tuple[List[MatchDict], Optional[dict]]:
    """
    Теперь источник – только Transfermarkt (USE_TRANSFERMARKT=True).
    Возвращает (matches, error_dict)
    matches: [{id, home, away, timestamp, date_str, time_str}, ...]
    """
    limit = limit or DEFAULT_MATCH_LIMIT
    if USE_TRANSFERMARKT:
        fixtures, err = await fetch_transfermarkt_fixtures(league_code, limit)
        if err:
            return [], err
        # Нормализуем поля под единый формат
        norm: List[MatchDict] = []
        for f in fixtures:
            norm.append({
                "id": f.get("id"),
                "home": f.get("home"),
                "away": f.get("away"),
                "ts": f.get("timestamp"),
                "date": f.get("date_str"),
                "time": f.get("time_str"),
            })
        return norm, None
    return [], {"message": "No enabled sources"}


def render_matches_text(league_code: str, matches: List[MatchDict]) -> str:
    disp = LEAGUE_DISPLAY.get(league_code, league_code)
    if not matches:
        return f"Нет матчей (лига: {disp})"
    lines = [f"Матчи ({disp}):"]
    for m in matches:
        dt_part = ""
        if m.get("date") and m.get("time"):
            dt_part = f"{m['date']} {m['time']}"
        elif m.get("date"):
            dt_part = str(m["date"])
        elif m.get("time"):
            dt_part = str(m["time"])
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
    attempts = err.get("attempts") or []
    if attempts:
        base.append("Попытки (matchday -> статус):")
        for a in attempts[:6]:
            md = a.get("matchday")
            st = a.get("status")
            found = a.get("found")
            err_txt = a.get("error")
            if err_txt:
                base.append(f" - MD {md}: status={st} error={err_txt}")
            else:
                base.append(f" - MD {md}: status={st} parsed={found}")
    base.append("Источник: Transfermarkt")
    base.append("Советы: Попробуйте позже / уменьшить частоту / другой IP.")
    return "\n".join(base)
