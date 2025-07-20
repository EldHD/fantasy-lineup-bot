import logging, asyncio, datetime as dt
from sqlalchemy import select
from bot.db.database import async_session
from bot.db.models import Tournament, Team, Match
from bot.external.transfermarkt import fetch_matchday

log = logging.getLogger(__name__)

async def load_and_store_next_md(league_code: str) -> list[Match]:
    """Скачивает ближайший тур и кладёт в БД (idempotent)."""
    fixtures = await fetch_matchday(league_code, 1)   # пока всегда 1-й тур
    if not fixtures:
        log.warning("Нет матчей")
        return []

    async with async_session() as s:
        # 1. турнир
        tmt = await s.scalar(select(Tournament).where(Tournament.code == league_code))
        if not tmt:
            tmt = Tournament(code=league_code, name="Premier League")
            s.add(tmt)
            await s.flush()

        # 2. команды
        code_by_name = {}
        for f in fixtures:
            for name in (f["home"], f["away"]):
                if name in code_by_name:
                    continue
                code = name.lower().replace(" ", "_")
                team = await s.scalar(select(Team)
                                      .where(Team.tournament_id==tmt.id, Team.name==name))
                if not team:
                    team = Team(tournament_id=tmt.id, code=code, name=name)
                    s.add(team)
                    await s.flush()
                code_by_name[name] = team.id

        # 3. матчи
        for f in fixtures:
            exists = await s.scalar(
                select(Match).where(
                    Match.tournament_id==tmt.id,
                    Match.home_team_id==code_by_name[f["home"]],
                    Match.away_team_id==code_by_name[f["away"]],
                    Match.utc_kickoff==f["utc_kickoff"],
                )
            )
            if not exists:
                s.add(Match(
                    tournament_id = tmt.id,
                    matchday      = f["matchday"],
                    utc_kickoff   = f["utc_kickoff"],
                    home_team_id  = code_by_name[f["home"]],
                    away_team_id  = code_by_name[f["away"]],
                ))
        await s.commit()

        upcoming = await s.scalars(
            select(Match)
            .where(Match.tournament_id==tmt.id,
                   Match.utc_kickoff > dt.datetime.now(dt.timezone.utc))
            .order_by(Match.utc_kickoff)
            .limit(15)
        )
        return list(upcoming)
