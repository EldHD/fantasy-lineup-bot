from sqlalchemy import select, delete
from bot.db.database import SessionLocal
from bot.db.models import Player, Prediction, Match


def base_probability(position_main: str, idx: int) -> int:
    if position_main == "goalkeeper":
        return 98
    return max(60, 92 - idx * 3)


async def generate_baseline_predictions(match_id: int, team_id: int):
    async with SessionLocal() as session:
        m_res = await session.execute(select(Match).where(Match.id == match_id))
        match = m_res.scalar_one_or_none()
        if not match:
            return f"Match {match_id} not found."

        p_res = await session.execute(select(Player).where(Player.team_id == team_id))
        players = p_res.scalars().all()
        if not players:
            return f"No players for team {team_id}."

        role_order = {"goalkeeper": 0, "defender": 1, "midfielder": 2, "forward": 3}
        players.sort(key=lambda p: (
            role_order.get(p.position_main, 9),
            (p.shirt_number or 999),
            p.full_name.lower()
        ))

        starters = []
        gk = [p for p in players if p.position_main == "goalkeeper"]
        if gk:
            starters.append(gk[0])

        def pick(role, need):
            nonlocal starters
            pool = [p for p in players if p.position_main == role and p not in starters]
            starters.extend(pool[:need])

        pick("defender", 4)
        pick("midfielder", 5)
        pick("forward", 1)

        if len(starters) < 11:
            extras = [p for p in players if p not in starters]
            starters.extend(extras[: 11 - len(starters)])

        starter_ids = {p.id for p in starters}

        del_stmt = delete(Prediction).where(Prediction.match_id == match_id)
        await session.execute(del_stmt)
        await session.flush()

        for idx, p in enumerate(players):
            prob = base_probability(p.position_main, idx)
            will_start = p.id in starter_ids
            session.add(Prediction(
                match_id=match_id,
                player_id=p.id,
                will_start=will_start,
                probability=prob if will_start else max(40, prob - 25),
                explanation="Baseline demo prediction"
            ))

        await session.commit()
        return f"Predictions generated: starters={len(starters)}, total_players={len(players)}"
