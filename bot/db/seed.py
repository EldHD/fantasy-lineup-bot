import datetime as dt
from sqlalchemy import select
from .database import engine, SessionLocal
from .models import Base, Tournament, Team, Match

async def _create_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def _seed_minimal(session):
    exists = await session.execute(select(Tournament.id).limit(1))
    if exists.first():
        return False
    now = dt.datetime.now(dt.timezone.utc)

    epl = Tournament(code="epl", name="Premier League")
    rpl = Tournament(code="rpl", name="Russian Premier League")
    session.add_all([epl, rpl])
    await session.flush()

    ars = Team(tournament_id=epl.id, code="ARS", name="Arsenal")
    che = Team(tournament_id=epl.id, code="CHE", name="Chelsea")
    zen = Team(tournament_id=rpl.id, code="ZEN", name="Zenit")
    csk = Team(tournament_id=rpl.id, code="CSK", name="CSKA Moscow")
    session.add_all([ars, che, zen, csk])
    await session.flush()

    m1 = Match(
        tournament_id=epl.id,
        round="Matchweek 1",
        utc_kickoff=now + dt.timedelta(hours=6),
        home_team_id=ars.id,
        away_team_id=che.id
    )
    m2 = Match(
        tournament_id=rpl.id,
        round="Matchday 1",
        utc_kickoff=now + dt.timedelta(hours=8),
        home_team_id=zen.id,
        away_team_id=csk.id
    )
    session.add_all([m1, m2])
    await session.flush()
    return True

async def auto_seed():
    await _create_schema()
    async with SessionLocal() as session:
        created = await _seed_minimal(session)
        if created:
            await session.commit()
            print("Minimal seed applied.")
        else:
            print("Seed skipped (already have tournaments).")
