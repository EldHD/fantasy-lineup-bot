from typing import List, Optional
from sqlalchemy import select
from bot.db.database import SessionLocal
from bot.db.models import Team, Player
from bot.external.sofascore import fetch_team_players, SOFASCORE_TEAM_IDS

POS_MAP_MAIN = {
    "G": "goalkeeper",
    "GK": "goalkeeper",
    "D": "defender",
    "DF": "defender",
    "M": "midfielder",
    "MF": "midfielder",
    "F": "forward",
    "FW": "forward",
    "ATT": "forward",
}


def extract_detail(p: dict) -> Optional[str]:
    info = p.get("positionInfo") or {}
    desc = (info.get("description") or "").title()
    if not desc:
        return None
    mapping = {
        "Centre-Back": "CB",
        "Left-Back": "LB",
        "Right-Back": "RB",
        "Defensive Midfield": "DM",
        "Central Midfield": "CM",
        "Attacking Midfield": "AM",
        "Left Winger": "LW",
        "Right Winger": "RW",
        "Centre-Forward": "CF",
        "Goalkeeper": "GK",
        "Second Striker": "SS",
    }
    return mapping.get(desc, desc[:12])


def map_main(pos_raw: str) -> str:
    return POS_MAP_MAIN.get((pos_raw or "").upper(), "midfielder")


async def sync_team_roster(team_name: str):
    async with SessionLocal() as session:
        stmt = select(Team).where(Team.name == team_name)
        res = await session.execute(stmt)
        team = res.scalar_one_or_none()
        if not team:
            return f"Team '{team_name}' not found in DB."

        sofa_id = SOFASCORE_TEAM_IDS.get(team.name)
        if not sofa_id:
            return f"No Sofascore ID mapped for '{team.name}'"

        players_raw = await fetch_team_players(sofa_id)
        created = 0
        updated = 0

        ex_stmt = select(Player).where(Player.team_id == team.id)
        ex_res = await session.execute(ex_stmt)
        existing = ex_res.scalars().all()
        by_name = {p.full_name.lower(): p for p in existing}

        for pr in players_raw:
            full_name = pr.get("name") or pr.get("shortName") or pr.get("slug") or ""
            if not full_name:
                continue
            key = full_name.lower()
            pos_raw = pr.get("position") or pr.get("player", {}).get("position")
            position_main = map_main(pos_raw)
            position_detail = extract_detail(pr)
            number = pr.get("shirtNumber") or pr.get("jerseyNumber") or None
            sf_id = pr.get("id")

            if key in by_name:
                p = by_name[key]
                changed = False
                if p.position_main != position_main:
                    p.position_main = position_main; changed = True
                if position_detail and p.position_detail != position_detail:
                    p.position_detail = position_detail; changed = True
                if number and p.shirt_number != number:
                    p.shirt_number = number; changed = True
                if sf_id and p.sf_id != sf_id:
                    p.sf_id = sf_id; changed = True
                if changed:
                    updated += 1
            else:
                new_p = Player(
                    team_id=team.id,
                    full_name=full_name,
                    shirt_number=number,
                    position_main=position_main,
                    position_detail=position_detail,
                    sf_id=sf_id,
                )
                session.add(new_p)
                created += 1

        await session.commit()
        return f"Roster sync for {team.name}: created={created}, updated={updated}, total_now={created+len(existing)}"


async def sync_multiple_teams(team_names: List[str]):
    reports = []
    for name in team_names:
        rep = await sync_team_roster(name)
        reports.append(rep)
    return "\n".join(reports)
