from typing import List
from sqlalchemy import select, update
from bot.db.database import SessionLocal
from bot.db.models import Team, Player, PlayerStatus, Tournament
from bot.external.sofascore import (
    fetch_team_players as sofa_fetch_players,
    SOFASCORE_TEAM_IDS,
    SofascoreError,
)
from bot.external.transfermarkt import (
    fetch_team_squad,
    fetch_injury_list,
    TMError,
    TRANSFERMARKT_TEAM_IDS,
)
import os
import logging

logger = logging.getLogger(__name__)

DISABLE_SOFA = os.environ.get("DISABLE_SOFASCORE") == "1"


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _map_main_sofa(pos_raw):
    if not pos_raw:
        return "midfielder"
    pos_raw = pos_raw.upper()
    if pos_raw in ("G", "GK"):
        return "goalkeeper"
    if pos_raw in ("D", "DF"):
        return "defender"
    if pos_raw in ("M", "MF"):
        return "midfielder"
    if pos_raw in ("F", "FW", "ATT"):
        return "forward"
    return "midfielder"


def _detail_sofa(p: dict):
    info = p.get("positionInfo") or {}
    desc = (info.get("description") or "").title()
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
    return mapping.get(desc, desc[:12]) if desc else None


async def ensure_teams_exist(team_names: List[str], tournament_code: str):
    """
    Создаёт команды с привязкой к турниру.
    Если турнир отсутствует – создаёт.
    Если команда есть, но без tournament_id – ставит.
    Возвращает количество *новых* созданных команд.
    """
    async with SessionLocal() as session:
        # Турнир
        t_res = await session.execute(select(Tournament).where(Tournament.code == tournament_code))
        tournament = t_res.scalar_one_or_none()
        if not tournament:
            tournament = Tournament(code=tournament_code, name=tournament_code.upper())
            session.add(tournament)
            await session.flush()
            logger.info("Created tournament %s (id=%s)", tournament_code, tournament.id)

        # Существующие команды
        existing_res = await session.execute(select(Team).where(Team.name.in_(team_names)))
        existing = existing_res.scalars().all()
        existing_by_name = {t.name: t for t in existing}

        created = 0
        repaired = 0
        for name in team_names:
            team = existing_by_name.get(name)
            if team:
                # если уже есть, но нет привязки к турниру – дополним
                if getattr(team, "tournament_id", None) in (None, 0):
                    team.tournament_id = tournament.id
                    repaired += 1
            else:
                session.add(Team(name=name, tournament_id=tournament.id))
                created += 1

        if created or repaired:
            await session.commit()
        return created


async def _upsert_players(team, player_dicts):
    async with SessionLocal() as session:
        stmt = select(Player).where(Player.team_id == team.id)
        res = await session.execute(stmt)
        existing = res.scalars().all()
        existing_by_name = {_normalize_name(p.full_name): p for p in existing}

        created = 0
        updated = 0
        for pd in player_dicts:
            full_name = pd.get("full_name", "").strip()
            if not full_name:
                continue
            key = _normalize_name(full_name)
            pos_main = pd.get("position_main") or "midfielder"
            pos_detail = pd.get("position_detail")
            number = pd.get("shirt_number")

            if key in existing_by_name:
                p = existing_by_name[key]
                changed = False
                if p.position_main != pos_main:
                    p.position_main = pos_main; changed = True
                if pos_detail and p.

Eldar Khayretdinov, [19.07.2025 19:17]
position_detail != pos_detail:
                    p.position_detail = pos_detail; changed = True
                if number and p.shirt_number != number:
                    p.shirt_number = number; changed = True
                if changed:
                    updated += 1
            else:
                session.add(Player(
                    team_id=team.id,
                    full_name=full_name,
                    position_main=pos_main,
                    position_detail=pos_detail,
                    shirt_number=number
                ))
                created += 1
        await session.commit()
    return f"created={created}, updated={updated}, total_now={created+len(existing)}"


async def _sync_from_sofascore(team) -> str:
    sofa_id = SOFASCORE_TEAM_IDS.get(team.name)
    if not sofa_id:
        return f"No Sofascore ID for {team.name}"
    players_raw = await sofa_fetch_players(sofa_id)
    return await _upsert_players(team, [
        {
            "full_name": p.get("name") or p.get("shortName") or p.get("slug") or "",
            "shirt_number": p.get("shirtNumber") or p.get("jerseyNumber"),
            "position_main": _map_main_sofa(p.get("position")),
            "position_detail": _detail_sofa(p),
        } for p in players_raw
    ])


async def _sync_from_transfermarkt(team) -> str:
    squad = await fetch_team_squad(team.name)
    report_players = await _upsert_players(team, squad)
    injuries = await fetch_injury_list(team.name)
    if injuries:
        async with SessionLocal() as session:
            stmt = select(Player).where(Player.team_id == team.id)
            res = await session.execute(stmt)
            players = res.scalars().all()
            by_name = {_normalize_name(p.full_name): p for p in players}

            created_status = 0
            for it in injuries:
                nm = _normalize_name(it["full_name"])
                player = by_name.get(nm)
                if not player:
                    continue
                status = PlayerStatus(
                    player_id=player.id,
                    type="injury" if "Suspension" not in it["reason"] else "suspension",
                    availability="OUT",
                    reason=it["reason"][:180] if it["reason"] else None,
                    raw_status=it["reason"],
                )
                session.add(status)
                created_status += 1
            await session.commit()
        report_players += f"; statuses={created_status}"
    return report_players


async def sync_team_roster(team_name: str):
    async with SessionLocal() as session:
        stmt = select(Team).where(Team.name == team_name)
        res = await session.execute(stmt)
        team = res.scalar_one_or_none()
        if not team:
            return f"Team '{team_name}' not found."

    # Sofascore (если не отключен)
    if not DISABLE_SOFA and team_name in SOFASCORE_TEAM_IDS:
        try:
            return f"{team_name} (Sofa): " + await _sync_from_sofascore(team)
        except Exception as e:
            logger.warning("Sofascore sync fail %s: %s", team_name, e)

    # Transfermarkt
    if team_name in TRANSFERMARKT_TEAM_IDS:
        try:
            return f"{team_name} (TM): " + await _sync_from_transfermarkt(team)
        except TMError as e:
            return f"{team_name} TM error: {e}"
        except Exception as e:
            return f"{team_name} unexpected TM error: {e}"
    return f"{team_name}: no data source."


async def sync_multiple_teams(team_names: List[str]):
    reports = []
    for name in team_names:
        rep = await sync_team_roster(name)
        reports.append(rep)
    return "\n".join(reports)
