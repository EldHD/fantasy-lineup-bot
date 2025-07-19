from typing import List, Optional
from sqlalchemy import select
from bot.db.database import SessionLocal
from bot.db.models import Team, Player, PlayerStatus, Tournament
from bot.external.sofascore import (
    fetch_team_players as sofa_fetch_players,
    SOFASCORE_TEAM_IDS,
)
from bot.external.transfermarkt import (
    fetch_team_squad,
    fetch_injury_list,
    TMError,
    TRANSFERMARKT_TEAM_IDS,
)
import os
import logging
import re

logger = logging.getLogger(__name__)

DISABLE_SOFA = os.environ.get("DISABLE_SOFASCORE") == "1"

# ---- Фиксированные короткие коды (≤12 символов) ----
FIXED_TEAM_CODES = {
    "Arsenal": "ARS",
    "Aston Villa": "AVL",
    "Bournemouth": "BOU",
    "Brentford": "BRE",
    "Brighton & Hove Albion": "BHA",
    "Chelsea": "CHE",
    "Crystal Palace": "CRY",
    "Everton": "EVE",
    "Fulham": "FUL",
    "Ipswich Town": "IPS",
    "Leicester City": "LEI",
    "Liverpool": "LIV",
    "Manchester City": "MCI",
    "Manchester United": "MUN",
    "Newcastle United": "NEW",
    "Nottingham Forest": "NFO",
    "Southampton": "SOU",
    "Tottenham Hotspur": "TOT",
    "West Ham United": "WHU",
    "Wolverhampton Wanderers": "WOL",
    "Zenit": "ZEN",
    "CSKA Moscow": "CSKA",
}

# -------------------------------- Utility -------------------------------- #

def _normalize_name(name: str) -> str:
    return name.strip().lower()

def _map_main_sofa(pos_raw: Optional[str]):
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

def _fallback_code_from_name(name: str) -> str:
    """
    Если вдруг команда вне словаря – создаём безопасный <=12 slug.
    """
    slug = re.sub(r'[^A-Za-z0-9]+', '_', name.lower())
    slug = re.sub(r'_+', '_', slug).strip('_')
    if not slug:
        slug = "team"
    if len(slug) > 12:
        slug = slug[:12]
    return slug.upper()

# ---------------- Ensure Teams ---------------- #

async def ensure_teams_exist(team_names: List[str], tournament_code: str):
    """
    Создаёт недостающие команды, гарантирует короткий уникальный code (≤12),
    чинит отсутствующий tournament_id или code.
    Возвращает количество новых команд.
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

        # Все команды по именам
        existing_res = await session.execute(select(Team).where(Team.name.in_(team_names)))
        existing = existing_res.scalars().all()
        existing_by_name = {t.name: t for t in existing}

        # Уже занятые коды (всей БД)
        all_team_res = await session.execute(select(Team))
        all_teams = all_team_res.scalars().all()
        occupied = {t.code for t in all_teams if getattr(t, "code", None)}

        def unique_code(code: str) -> str:
            base = code
            if base not in occupied:
                occupied.add(base)
                return base
            # Добавляем числовые суффиксы при коллизии
            idx = 2
            while True:
                candidate = (base[: (12 - len(str(idx)) - 1)] + f"_{idx}").upper()
                if candidate not in occupied:
                    occupied.add(candidate)
                    return candidate
                idx += 1

        created = 0
        repaired_code = 0
        repaired_tournament = 0

        for name in team_names:
            team = existing_by_name.get(name)
            if team:
                # Дополняем tournament_id
                if getattr(team, "tournament_id", None) in (None, 0):
                    team.tournament_id = tournament.id
                    repaired_tournament += 1
                # Дополняем / чиним code
                if not getattr(team, "code", None):
                    raw = FIXED_TEAM_CODES.get(name) or _fallback_code_from_name(name)
                    if len(raw) > 12:
                        raw = raw[:12]
                    code = unique_code(raw)
                    team.code = code
                    repaired_code += 1
                else:
                    # Если почему-то длинный >12 (на всякий случай)
                    if len(team.code) > 12:
                        new_code = unique_code(team.code[:12])
                        team.code = new_code
                        repaired_code += 1
            else:
                raw = FIXED_TEAM_CODES.get(name) or _fallback_code_from_name(name)
                if len(raw) > 12:
                    raw = raw[:12]
                code = unique_code(raw)
                new_team = Team(
                    name=name,
                    code=code,
                    tournament_id=tournament.id
                )
                session.add(new_team)
                created += 1

        if created or repaired_code or repaired_tournament:
            await session.commit()
            logger.info(
                "Teams ensure: created=%s repaired_code=%s repaired_tournament=%s",
                created, repaired_code, repaired_tournament
            )

        return created

# ---------------- Upsert Players ---------------- #

async def _upsert_players(team, player_dicts):
    async with SessionLocal() as session:
        stmt = select(Player).where(Player.team_id == team.id)
        res = await session.execute(stmt)
        existing = res.scalars().all()
        existing_by_name = {_normalize_name(p.full_name): p for p in existing}

        created = 0
        updated = 0
        for pd in player_dicts:
            full_name = (pd.get("full_name") or "").strip()
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
                if pos_detail and p.position_detail != pos_detail:
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
    total_now = created + len(existing)
    return f"created={created}, updated={updated}, total_now={total_now}"

# ---------------- Sofascore Source ---------------- #

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

# ---------------- Transfermarkt Source ---------------- #

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

# ---------------- Public Sync API ---------------- #

async def sync_team_roster(team_name: str):
    async with SessionLocal() as session:
        stmt = select(Team).where(Team.name == team_name)
        res = await session.execute(stmt)
        team = res.scalar_one_or_none()
        if not team:
            return f"Team '{team_name}' not found."

    # Sofascore
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
