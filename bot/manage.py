import asyncio
import sys
from sqlalchemy import select
from bot.db.database import create_all, drop_all, async_session
from bot.db.models import Tournament, Team

EPL_TEAMS = [
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford",
    "Brighton & Hove Albion", "Chelsea", "Crystal Palace", "Everton",
    "Fulham", "Ipswich Town", "Leicester City", "Liverpool",
    "Manchester City", "Manchester United", "Newcastle United",
    "Nottingham Forest", "Southampton", "Tottenham Hotspur",
    "West Ham United", "Wolverhampton Wanderers"
]
EPL_CODE = "epl"
EPL_NAME = "Premier League"


def slug(name: str) -> str:
    return (name.lower()
            .replace("&", "and")
            .replace(" ", "_")
            .replace("-", "_"))[:32]


async def seed_epl():
    async with async_session() as session:
        res = await session.execute(select(Tournament).where(Tournament.code == EPL_CODE))
        t = res.scalars().first()
        if not t:
            t = Tournament(code=EPL_CODE, name=EPL_NAME)
            session.add(t)
            await session.flush()
            print("Created tournament:", EPL_CODE)

        res = await session.execute(select(Team).where(Team.tournament_id == t.id))
        existing_codes = {tm.code for tm in res.scalars().all()}

        created = 0
        for n in EPL_TEAMS:
            c = slug(n)
            if c in existing_codes:
                continue
            session.add(Team(tournament_id=t.id, code=c, name=n))
            created += 1
        await session.commit()
        print(f"EPL seed complete. Added teams: {created}, total target: {len(EPL_TEAMS)}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m bot.manage <command>")
        print("Commands: reset_db, seed_epl, full_init")
        return

    cmd = sys.argv[1]
    if cmd == "reset_db":
        print("Dropping all tables...")
        await drop_all()
        print("Creating tables...")
        await create_all()
        print("Done.")
    elif cmd == "seed_epl":
        await seed_epl()
    elif cmd == "full_init":
        print("Reset + seed EPL...")
        await drop_all()
        await create_all()
        await seed_epl()
    else:
        print("Unknown command:", cmd)


if __name__ == "__main__":
    asyncio.run(main())
