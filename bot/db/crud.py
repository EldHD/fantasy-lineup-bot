import datetime as dt
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .database import SessionLocal
from .models import Tournament, Match

async def fetch_matches_by_league(code: str, limit: int = 10):
    async with SessionLocal() as session:
        t_stmt = select(Tournament).where(Tournament.code == code)
        t_res = await session.execute(t_stmt)
        tournament = t_res.scalar_one_or_none()
        if not tournament:
            return []

        stmt = (
            select(Match)
            .where(Match.tournament_id == tournament.id,
                   Match.utc_kickoff >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2))
            .order_by(Match.utc_kickoff.asc())
            .limit(limit)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.tournament)
            )
        )
        res = await session.execute(stmt)
        return res.scalars().all()
