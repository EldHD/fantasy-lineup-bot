from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.config import (
    LEAGUE_DISPLAY, TOURNAMENT_CODE_MAP, FIXTURES_TTL,
    FETCH_LIMIT_PER_LEAGUE
)
from bot.external.transfermarkt_fixtures import fetch_current_matchday_upcoming
from bot.db.database import async_session
from bot.db.models import Tournament, Team, Match


def _norm(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum())


async def _get_tournament(session, league_code: str) -> Optional[Tournament]:
    code = TOURNAMENT_CODE_MAP.get(league_code, league_code)
    res = await session.execute(select(Tournament).where(Tournament.code == code))
    return res.scalar_one_or_none()


async def _load_cached(session, tournament_id: int):
    now = datetime.now(timezone.utc)
    res = await session.execute(
        select(Match)
        .where(Match.tournament_id == tournament_id)
        .where(Match.utc_kickoff > now)
        .order_by(Match.utc_kickoff)
    )
    matches = res.scalars().all()
    if not matches:
        return None, [], False

    # сгруппировать по туру
    buckets = {}
    for m in matches:
        md = None
        if m.round and m.round.startswith("MD "):
            try:
                md = int(m.round.split()[1])
            except ValueError:
                pass
        if md is None:
            continue
        buckets.setdefault(md, []).append(m)

    if not buckets:
        return None, [], False

    md_min = min(buckets.keys())
    current = buckets[md_min]

    fresh = False
    if hasattr(Match, "updated_at"):
        upd_times = [getattr(m, "updated_at", None) for m in current]
        if all(upd_times):
            oldest = min(upd_times)
            if (datetime.now(timezone.utc) - oldest) < FIXTURES_TTL:
                fresh = True

    return md_min, current, fresh


async def _ensure_teams(session, tournament: Tournament, fixtures: List[Dict]) -> Dict[str, int]:
    res = await session.execute(
        select(Team).where(Team.tournament_id == tournament.id)
    )
    existing = res.scalars().all()
    existing_map = {_norm(t.name): t for t in existing}
    created = False
    for fx in fixtures:
        for side in ("home", "away"):
            nm = fx[side]
            k = _norm(nm)
            if k not in existing_map:
                team = Team(
                    tournament_id=tournament.id,
                    code=k[:12],
                    name=nm
                )
                session.add(team)
                existing_map[k] = team
                created = True
    if created:
        await session.flush()
    return {k: v.id for k, v in existing_map.items()}


async def _upsert(session, tournament: Tournament, md: int, fixtures: List[Dict]):
    team_ids = await _ensure_teams(session, tournament, fixtures)
    now = datetime.utcnow()
    rows = []
    for fx in fixtures:
        home_id = team_ids[_norm(fx["home"])]
        away_id = team_ids[_norm(fx["away"])]
        rows.append({
            "id": fx["id"],
            "tournament_id": tournament.id,
            "round": f"MD {md}",
            "utc_kickoff": fx.get("datetime"),
            "home_team_id": home_id,
            "away_team_id": away_id,
            "status": "planned",
            "updated_at": now,
        })
    stmt = pg_insert(Match).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Match.id],
        set_={
            "tournament_id": stmt.excluded.tournament_id,
            "round": stmt.excluded.round,
            "utc_kickoff": stmt.excluded.utc_kickoff,
            "home_team_id": stmt.excluded.home_team_id,
            "away_team_id": stmt.excluded.away_team_id,
            "status": stmt.excluded.status,
            "updated_at": stmt.excluded.updated_at,
        }
    )
    await session.execute(stmt)


async def load_matches_for_league(league_code: str, limit: int = FETCH_LIMIT_PER_LEAGUE) -> Tuple[List[Dict], Dict]:
    async with async_session() as session:
        tournament = await _get_tournament(session, league_code)
        if not tournament:
            return [], {"error": f"Tournament not found for league {league_code}"}

        md_cached, cached, fresh = await _load_cached(session, tournament.id)
        if cached and fresh:
            data = [{
                "id": m.id,
                "home": m.home_team.name if m.home_team else "?",
                "away": m.away_team.name if m.away_team else "?",
                "datetime": m.utc_kickoff,
                "matchday": md_cached
            } for m in cached[:limit]]
            return data, {
                "cached": True,
                "matchday": md_cached,
                "count": len(data),
                "league": league_code
            }

        # Парсим
        fixtures, meta = await fetch_current_matchday_upcoming(league_code)
        if not fixtures:
            return [], {"error": "No fixtures parsed", "meta": meta}

        md = meta.get("matchday", 0)
        await _upsert(session, tournament, md, fixtures)
        await session.commit()

        # перечитать для консистентности
        md2, matches2, _ = await _load_cached(session, tournament.id)
        data = [{
            "id": m.id,
            "home": m.home_team.name if m.home_team else "?",
            "away": m.away_team.name if m.away_team else "?",
            "datetime": m.utc_kickoff,
            "matchday": md2
        } for m in matches2[:limit]]

        return data, {
            "cached": False,
            "matchday": md2,
            "count": len(data),
            "league": league_code,
            "parsed_meta": meta
        }


def render_matches_text(league_code: str, matches: List[Dict], meta: Dict) -> str:
    if not matches:
        if meta.get("error"):
            return f"Нет матчей (лига: {league_code})\nПричина: {meta['error']}"
        return f"Нет матчей (лига: {league_code})"

    league_name = LEAGUE_DISPLAY.get(league_code, league_code)
    md = matches[0].get("matchday")
    header = f"Тур {md} ({league_name}):" if md else f"{league_name}:"
    lines = []
    for fx in matches:
        dt_obj = fx.get("datetime")
        dt_str = dt_obj.strftime("%d/%m/%Y %H:%M") if dt_obj else "TBD"
        lines.append(f"- {fx['home']} vs {fx['away']} {dt_str} #{fx['id']}")
    return header + "\n" + "\n".join(lines)
