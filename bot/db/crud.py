import datetime as dt
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .database import SessionLocal
from .models import (
    Tournament,
    Match,
    Player,
    Prediction,
    PlayerStatus,
)


async def fetch_matches_by_league(code: str, limit: int = 10):
    """
    Возвращает предстоящие матчи лиги по её коду.
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
                Match.utc_kickoff >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
            )
            .order_by(Match.utc_kickoff.asc())
            .limit(limit)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.tournament),
            )
        )
        res = await session.execute(stmt)
        return res.scalars().all()


async def fetch_match_with_teams(match_id: int):
    """
    Возвращает матч с подгруженными командами и турниром.
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
        return res.scalar_one_or_none()


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

    Возвращаем строго *данные*, а не ORM-объекты, чтобы избежать MissingGreenlet
    (ленивая загрузка вне сессии).
    """
    async with SessionLocal() as session:
        # Предикты матча (с предзагрузкой Player)
        stmt = (
            select(Prediction)
            .where(Prediction.match_id == match_id)
            .options(
                selectinload(Prediction.player)
            )
        )
        res = await session.execute(stmt)
        all_preds = res.scalars().all()

        # Фильтр по команде
        team_preds = [pr for pr in all_preds if pr.player.team_id == team_id]
        if not team_preds:
            return []

        # Статусы (берем последний по player_id — упрощённо)
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
            if st.player_id not in status_map:  # первый — самый свежий
                status_map[st.player_id] = st

        # Сортировка
        order = {"goalkeeper": 0, "defender": 1, "midfielder": 2, "forward": 3}
        team_preds.sort(
            key=lambda pr: (order.get(pr.player.position_main, 99), -pr.probability)
        )

        # Преобразование в DTO
        dto_list = []
        for pr in team_preds:
            p = pr.player
            st = status_map.get(p.id)
            dto_list.append({
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

        return dto_list
