import datetime as dt
import asyncio
from sqlalchemy import select
from .database import engine, SessionLocal
from .models import Base, Tournament, Team, Match

async def auto_seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        # Уже есть турнир? — значит сид делать не нужно
        existing = await session.execute(select(Tournament).limit(1))
        if existing.first():
            return

        now = dt.datetime.now(dt.timezone.utc)

        # Создаём 2 турнира
        rpl = Tournament(code="rpl", name="Russian Premier League")
        epl = Tournament(code="epl", name="Premier League")
        session.add_all([rpl, epl])
        await session.flush()

        # Команды (по 2 для примера)
        zen = Team(tournament_id=rpl.id, code="ZEN", name="Zenit")
        csk = Team(tournament_id=rpl.id, code="CSK", name="CSKA Moscow")
        ars = Team(tournament_id=epl.id, code="ARS", name="Arsenal")
        che = Team(tournament_id=epl.id, code="CHE", name="Chelsea")
        session.add_all([zen, csk, ars, che])
        await session.flush()

        # Два матча
        m1 = Match(
            tournament_id=rpl.id,
            round="Matchday 1",
            utc_kickoff=now + dt.timedelta(hours=10),
            home_team_id=zen.id,
            away_team_id=csk.id
        )
        m2 = Match(
            tournament_id=epl.id,
            round="Matchweek 1",
            utc_kickoff=now + dt.timedelta(hours=15),
            home_team_id=ars.id,
            away_team_id=che.id
        )
        session.add_all([m1, m2])

        await session.commit()
        print("Seed: initial data inserted.")
