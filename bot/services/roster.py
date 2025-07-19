import os
import re
import random
import asyncio
import logging
from datetime import datetime, timedelta, timezone
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

logger = logging.getLogger(__name__)

DISABLE_SOFA = os.environ.get("DISABLE_SOFASCORE") == "1"

# Короткие фиксированные коды (≤12)
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


# ---------- Date Helpers ---------- #

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _to_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Привести любой datetime к tz-aware UTC. Если None – вернуть None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    # нормализуем в UTC
    return dt.astimezone(timezone.utc)


# ---------- Utility ---------- #

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

def _fallback_code(name: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9]+', '_', name.lower())
    slug = re.sub(r'_+', '_', slug).strip('_')
    if not slug:
        slug = "team"
    slug = slug[:12]
    return slug.upper()


# ---------- Ensure Teams ---------- #

async def ensure_teams_exist(team_names: List[str], tournament_code: str):
    """
    Создаёт команды, если отсутствуют. Дополняет code/tournament_id если пусто.
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

        # Уже есть
        existing_res = await session.execute(select(Team).where(Team.name.in_(team_names)))
        existing = existing_res.scalars().all()
        existing_by_name = {t.name: t for t in existing}

        # Все команды — для занятости кодов
        all_team_res = await session.execute(select(Team))
        all_teams = all_team_res.scalars().all()
        occupied = {t.code for t in all_teams if getattr(t, "code", None)}

        def uniq(code: str) -> str:
            code = code.upper()
            if code not in occupied:
                occupied.add(code)
                return code
            base = code
            idx = 2
            while True:
                suffix = f"_{idx}"
                limit = 12 - len(suffix)
                cand = (base[:limit] + suffix).upper()
                if cand not in occupied:
                    occupied.add(cand)
                    return cand
                idx += 1

        created = 0
        repaired = 0

        for name in team_names:
            team = existing_by_name.get(name)
            code_raw = FIXED_TEAM_CODES.get(name) or _fallback_code(name)
            if len(code_raw) > 12:
                code_raw = code_raw[:12]
            if not team:
                team = Team(
                    name=name,
                    code=uniq(code_raw),
                    tournament_id=tournament.id
                )
                session.add(team)
                created += 1
            else:
                changed = False
                if getattr(team, "tournament_id", None) in (None, 0):
                    team.tournament_id = tournament.id
                    changed = True
                if not getattr(team, "code", None):
                    team.code = uniq(code_raw)
                    changed = True
                elif len(team.code) > 12:
                    team.code = uniq(team.code[:12])
                    changed = True
                if changed:
                    repaired += 1

        if created or repaired:
            await session.commit()
            logger.info("Teams ensure created=%s repaired=%s", created, repaired)

        return created


# ---------- Players Upsert ---------- #

async def _upsert_players(team, player_dicts):
    async with SessionLocal() as session:
        stmt = select(Player).where(Player.team_id == team.id)
        res = await session.execute(stmt)
        existing = res.scalars().all()
        existing_map = {_normalize_name(p.full_name): p for p in existing}

        created = 0
        updated = 0
        for pd in player_dicts:
            name = (pd.get("full_name") or "").strip()
            if not name:
                continue
            key = _normalize_name(name)
            pos_main = pd.get("position_main") or "midfielder"
            pos_detail = pd.get("position_detail")
            number = pd.get("shirt_number")

            if key in existing_map:
                p = existing_map[key]
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
                    full_name=name,
                    position_main=pos_main,
                    position_detail=pos_detail,
                    shirt_number=number
                ))
                created += 1
        await session.commit()
    return f"created={created}, updated={updated}, total_now={created + len(existing)}"


# ---------- Sources: Sofascore ---------- #

async def _sync_from_sofascore(team) -> str:
    sofa_id = SOFASCORE_TEAM_IDS.get(team.name)
    if not sofa_id:
        return f"No Sofascore ID for {team.name}"
    raw = await sofa_fetch_players(sofa_id)
    cleaned = []
    for p in raw[:60]:
        fullname = p.get("name") or p.get("shortName") or p.get("slug") or ""
        if not fullname.strip():
            continue
        cleaned.append({
            "full_name": fullname.strip(),
            "shirt_number": p.get("shirtNumber") or p.get("jerseyNumber"),
            "position_main": _map_main_sofa(p.get("position")),
            "position_detail": _detail_sofa(p),
        })
        if len(cleaned) >= 45:
            break
    return await _upsert_players(team, cleaned)


# ---------- Sources: Transfermarkt ---------- #

async def _sync_from_transfermarkt(team) -> str:
    squad = await fetch_team_squad(team.name)
    rep_players = await _upsert_players(team, squad)

    injuries = await fetch_injury_list(team.name)
    created_status = 0

    if injuries:
        async with SessionLocal() as session:
            stmt = select(Player).where(Player.team_id == team.id)
            res = await session.execute(stmt)
            players = res.scalars().all()
            by_name = {_normalize_name(p.full_name): p for p in players}

            cutoff = _now_utc() - timedelta(days=14)

            st_res = await session.execute(
                select(PlayerStatus).where(PlayerStatus.player_id.in_([p.id for p in players]))
            )
            existing_statuses = st_res.scalars().all()

            # Нормализуем время
            existing_signature = {}
            for s in existing_statuses:
                created_at = _to_utc_aware(getattr(s, "created_at", None))
                if created_at and created_at >= cutoff:
                    sig = (s.player_id, (s.raw_status or "").lower())
                    existing_signature[sig] = s

            for it in injuries:
                nm = _normalize_name(it["full_name"])
                player = by_name.get(nm)
                if not player:
                    continue
                reason = (it["reason"] or "").strip()
                if not reason:
                    continue
                sig_key = (player.id, reason.lower())
                if sig_key in existing_signature:
                    continue
                status = PlayerStatus(
                    player_id=player.id,
                    type="injury" if "suspens" not in reason.lower() else "suspension",
                    availability="OUT",
                    reason=reason[:180],
                    raw_status=reason,
                )
                session.add(status)
                created_status += 1

            if created_status:
                await session.commit()

    if created_status:
        rep_players += f"; statuses={created_status}"
    return rep_players


# ---------- Public API ---------- #

async def sync_team_roster(team_name: str):
    async with SessionLocal() as session:
        stmt = select(Team).where(Team.name == team_name)
        res = await session.execute(stmt)
        team = res.scalar_one_or_none()
        if not team:
            return f"Team '{team_name}' not found."

    # Sofascore (если включено)
    if not DISABLE_SOFA and team_name in SOFASCORE_TEAM_IDS:
        try:
            return f"{team_name} (Sofa): " + await _sync_from_sofascore(team)
        except Exception as e:
            logger.warning("Sofascore fail %s: %s", team_name, e)

    # Transfermarkt
    if team_name in TRANSFERMARKT_TEAM_IDS:
        try:
            return f"{team_name} (TM): " + await _sync_from_transfermarkt(team)
        except TMError as e:
            return f"{team_name} TM error: {e}"
        except Exception as e:
            logger.exception("Unexpected TM error for %s", team_name)
            return f"{team_name} unexpected TM error: {e}"

    return f"{team_name}: no data source."


async def sync_multiple_teams(team_names: List[str], delay_between: float = 3.2):
    """
    Последовательно, с паузой (анти-бот). + случайный шум.
    """
    reports = []
    for name in team_names:
        rep = await sync_team_roster(name)
        reports.append(rep)
        await asyncio.sleep(delay_between + random.uniform(0, 1.4))
    return "\n".join(reports)
