from typing import Optional, Tuple, List, Dict
from bot.external.sofascore import fetch_upcoming_events
from bot.config import DEFAULT_MATCH_LIMIT, LEAGUE_DISPLAY, SOFASCORE_BASE

# Тип для матча в Telegram-рендере
MatchDict = Dict[str, str | int | None]


async def load_matches_for_league(
    league_code: str,
    *,
    limit: int | None = None
) -> Tuple[List[MatchDict], Optional[dict]]:
    """
    Унифицированная функция (заменяет предыдущие варианты).
    Возвращает (список матчей, err_dict или None).
    """
    limit = limit or DEFAULT_MATCH_LIMIT
    events, err = await fetch_upcoming_events(league_code, limit=limit)
    if err:
        return [], err

    matches: List[MatchDict] = []
    for ev in events:
        matches.append({
            "id": ev["id"],
            "home": ev["homeTeam"],
            "away": ev["awayTeam"],
            "ts": ev["startTimestamp"],
            "status": ev["status"],
        })
    return matches, None


def render_matches_text(league_code: str, matches: List[MatchDict]) -> str:
    disp = LEAGUE_DISPLAY.get(league_code, league_code)
    if not matches:
        return f"Нет матчей (лига: {disp})"
    lines = [f"Матчи ({disp}):"]
    for m in matches:
        lines.append(
            f"- {m['home']} vs {m['away']} (ts={m['ts']})"
        )
    return "\n".join(lines)


def render_no_matches_error(league_code: str, err: dict) -> str:
    disp = LEAGUE_DISPLAY.get(league_code, league_code)
    base = [f"Нет матчей (лига: {disp})"]
    # Основное сообщение
    msg = err.get("message")
    if msg:
        base.append(f"Причина: {msg}")
    season_id = err.get("season_id")
    if season_id:
        base.append(f"Season ID: {season_id}")
    t_id = err.get("tournament_id")
    if t_id:
        base.append(f"Tournament ID: {t_id}")
    if err.get("season_resolve_error"):
        base.append(f"Season resolve err: {err['season_resolve_error']}")
    attempts = err.get("attempts") or []
    if attempts:
        base.append("Попытки:")
        # Покажем только первую и (если есть) вторую
        for a in attempts[:2]:
            ep = a.get("endpoint")
            st = a.get("status")
            e = a.get("error")
            base.append(f" - {ep} | status={st} | {e}")
    base.append(f"Источник: {SOFASCORE_BASE}")
    return "\n".join(base)
