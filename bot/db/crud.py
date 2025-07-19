import datetime as dt
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .database import SessionLocal
from .models import (
    Tournament,
    Match,
    Prediction,
    PlayerStatus,
    Player,
)


async def fetch_matches_by_league(code: str, limit: int = 10):
    """
    Возвращает список матчей в виде DTO:
    [
      {
        'id': int,
        'round': str,
        'utc_kickoff': datetime,
        'home_team_id': int,
        'home_team_name': str,
        'away_team_id': int,
        'away_team_name': str,
        'tournament_code': str
      }, ...
    ]
    """
    async with SessionLocal() as session:
        t_stmt = select(Tournament).where(Tournament.code == code)
        t_res = await session.execute(t_stmt)
        tournament = t_res.scalar_one_or_none()
        if not tournament:
            return []

        stmt = (
            select(Match)
            .where(
                Match.tournament_id == tournament.id,
                Match.utc_kickoff >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2),
            )
            .order_by(Match.utc_kickoff.asc())
            .limit(limit)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
            )
        )
        res = await session.execute(stmt)
        matches = res.scalars().all()

        dto = []
        for m in matches:
            dto.append({
                "id": m.id,
                "round": m.round,
                "utc_kickoff": m.utc_kickoff,
                "home_team_id": m.home_team_id,
                "home_team_name": m.home_team.name if m.home_team else "TBD",
                "away_team_id": m.away_team_id,
                "away_team_name": m.away_team.name if m.away_team else "TBD",
                "tournament_code": tournament.code,
            })
        return dto


async def fetch_match_with_teams(match_id: int):
    """
    DTO одного матча:
    {
      'id': ...,
      'round': ...,
      'utc_kickoff': ...,
      'tournament_code': ...,
      'home': {'id': int, 'name': str},
      'away': {'id': int, 'name': str}
    }
    """
    async with SessionLocal() as session:
        stmt = (
            select(Match)
            .where(Match.id == match_id)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.tournament),
            )
        )
        res = await session.execute(stmt)
        m = res.scalar_one_or_none()
        if not m:
            return None

        return {
            "id": m.id,
            "round": m.round,
            "utc_kickoff": m.utc_kickoff,
            "tournament_code": m.tournament.code if m.tournament else "",
            "home": {
                "id": m.home_team.id if m.home_team else None,
                "name": m.home_team.name if m.home_team else "TBD",
            },
            "away": {
                "id": m.away_team.id if m.away_team else None,
                "name": m.away_team.name if m.away_team else "TBD",
            },
        }


async def fetch_team_lineup_predictions(match_id: int, team_id: int):
    """
    Возвращает список словарей (DTO) по предиктам состава команды на матч.
    Формат элемента:
    {
      'player_id': int,
      'full_name': str,
      'number': int|None,
      'position_main': str,
      'position_detail': str|None,
      'will_start': bool,
      'probability': int,
      'explanation': str|None,
      'status_availability': 'OUT'|'DOUBT'|'OK'|None,
      'status_type': str|None,
      'status_reason': str|None,
      'status_source': str|None
    }
    """
    async with SessionLocal() as session:
        # Предикты по матчу
        stmt = (
            select(Prediction)
            .where(Prediction.match_id == match_id)
            .options(
                selectinload(Prediction.player)
            )
        )
        res = await session.execute(stmt)
        all_preds = res.scalars().all()

        team_preds = [pr for pr in all_preds if pr.player and pr.player.team_id == team_id]
        if not team_preds:
            return []

        # Статусы по player_id
        player_ids = [pr.player_id for pr in team_preds]
        st_stmt = (
            select(PlayerStatus)
            .where(PlayerStatus.player_id.in_(player_ids))
            .order_by(PlayerStatus.updated_at.desc())
        )
        st_res = await session.execute(st_stmt)
        statuses_list = st_res.scalars().all()

        status_map: dict[int, PlayerStatus] = {}
        for st in statuses_list:
            if st.player_id not in status_map:
                status_map[st.player_id] = st

        order = {"goalkeeper": 0, "defender": 1, "midfielder": 2, "forward": 3}
        team_preds.sort(
            key=lambda pr: (order.get(pr.player.position_main, 99), -pr.probability)
        )

        result = []
        for pr in team_preds:
            p: Player = pr.player
            st = status_map.get(p.id)
            result.append({
                "player_id": p.id,
                "full_name": p.full_name,
                "number": p.shirt_number,
                "position_main": p.position_main,
                "position_detail": p.position_detail,
                "will_start": pr.will_start,
                "probability": pr.probability,
                "explanation": pr.explanation,
                "status_availability": st.availability if st else None,
                "status_type": st.type if st else None,
                "status_reason": st.reason if st else None,
                "status_source": st.source_url if st else None,
            })
        return result
