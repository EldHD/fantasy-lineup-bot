# bot/tools/fill_fixtures.py
import asyncio, datetime as dt
from sqlalchemy import select
from bot.db.database import async_session
from bot.db.models   import Tournament, Team, Match
from bot.external.transfermarkt_fixtures import fetch_first_matchday_premier_league


LEAGUE_CODE = "epl"
SEASON      = 2025


async def main():
    fixtures = await fetch_first_matchday_premier_league(SEASON)
    if not fixtures:
        print("⛔  Transfermarkt вернул 0 матчей")
        return

    async with async_session() as s:
        # ── турнир ───────────────────────────
        t = await s.scalar(select(Tournament).where(Tournament.code == LEAGUE_CODE))
        if not t:
            t = Tournament(code=LEAGUE_CODE, name="Premier League")
            s.add(t)
            await s.flush()

        # ── команды ──────────────────────────
        cache: dict[str, int] = {}
        async def get_team(code: str, name: str) -> int:
            if code in cache:
                return cache[code]
            team = await s.scalar(
                select(Team)
                .where((Team.code == code) & (Team.tournament_id == t.id))
            )
            if not team:
                team = Team(code=code, name=name, tournament_id=t.id)
                s.add(team)
                await s.flush()
            cache[code] = team.id
            return team.id

        # ── сами матчи ───────────────────────
        for f in fixtures:
            hm_id = await get_team(f["home_code"], f["home_name"])
            aw_id = await get_team(f["away_code"], f["away_name"])

            exists = await s.scalar(
                select(Match).where(
                    (Match.tournament_id == t.id) &
                    (Match.utc_kickoff   == f["utc"]) &
                    (Match.home_team_id  == hm_id) &
                    (Match.away_team_id  == aw_id)
                )
            )
            if exists:
                continue

            s.add(Match(
                tournament_id = t.id,
                round         = f["round"],
                matchday      = f["matchday"],
                status        = "scheduled",
                utc_kickoff   = f["utc"],
                home_team_id  = hm_id,
                away_team_id  = aw_id,
            ))

        await s.commit()
    print(f"✅  Залили {len(fixtures)} матчей")


if __name__ == "__main__":
    asyncio.run(main())
