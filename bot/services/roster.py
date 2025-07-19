import asyncio
import logging
import random
from typing import List, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.database import async_session
from bot.db import models
from bot.config import TM_DELAY_BASE, TM_DELAY_JITTER

logger = logging.getLogger(__name__)

# ===== Заглушки парсеров (если реальные уже есть - оставь свои) =================
async def fetch_transfermarkt_roster(team_name: str) -> List[Dict]:
    """
    Заглушка: вернёт пустой список или фиктивные данные.
    В реальном коде тут запрос к Transfermarkt.
    """
    await asyncio.sleep(0.2)
    return []  # вернуть список игроков (dict) если нужно

# ================================================================================
async def ensure_teams_exist(team_names: List[str], tournament_code: str) -> Dict[str, models.Team]:
    """
    Гарантируем наличие записей команд в БД.
    team_names: список отображаемых имён ('Arsenal', 'Chelsea', ...)
    tournament_code: 'epl' и т.п.
    Возвращаем словарь name -> Team
    """
    results: Dict[str, models.Team] = {}
    async with async_session() as session:
        # Получаем турнир
        stmt_t = select(models.Tournament).where(models.Tournament.code == tournament_code)
        tournament = (await session.execute(stmt_t)).scalar_one_or_none()
        if not tournament:
            # Создадим, если отсутствует
            tournament = models.Tournament(code=tournament_code, name=tournament_code.upper())
            session.add(tournament)
            await session.commit()
            await session.refresh(tournament)

        # Существующие команды
        stmt = select(models.Team).where(models.Team.tournament_id == tournament.id)
        existing = {t.name.lower(): t for t in (await session.execute(stmt)).scalars().all()}

        created = 0
        for name in team_names:
            key = name.lower()
            if key in existing:
                results[name] = existing[key]
                continue
            code = key.replace(" ", "_")
            team = models.Team(tournament_id=tournament.id, name=name, code=code)
            session.add(team)
            await session.flush()
            results[name] = team
            created += 1

        if created:
            await session.commit()
            logger.info("ensure_teams_exist: created=%s", created)

    return results


async def sync_roster_for_team(team_name: str, tournament_code: str = "epl") -> str:
    """
    Синхронизирует ростер конкретной команды.
    Возвращает строку-отчёт.
    """
    # 1. ensure team exists
    teams_map = await ensure_teams_exist([team_name], tournament_code)
    team = teams_map[team_name]

    # 2. Получаем игроков с внешнего источника (пока заглушка)
    external_players = await fetch_transfermarkt_roster(team_name)
    if not external_players:
        return f"{team_name}: no external data"

    # Пример структуры external_players:
    # [{"name": "...", "position": "GK", "number": 1}, ...]

    async with async_session() as session:
        stmt = select(models.Player).where(models.Player.team_id == team.id)
        existing_players = {p.name.lower(): p for p in (await session.execute(stmt)).scalars().all()}

        created = 0
        updated = 0
        for ep in external_players:
            key = ep["name"].lower()
            if key in existing_players:
                p = existing_players[key]
                # при необходимости обновить поля
                updated += 1
            else:
                p = models.Player(
                    team_id=team.id,
                    name=ep["name"],
                    position=ep.get("position"),
                    number=ep.get("number")
                )
                session.add(p)
                created += 1

        if created or updated:
            await session.commit()

    return f"{team_name}: created={created}, updated={updated}"


async def sync_multiple_teams(
    team_names: List[str],
    tournament_code: str = "epl",
    delay_between: float = None
) -> List[str]:
    """
    Синхронизирует несколько команд подряд.
    delay_between: базовая задержка между командами (если None — TM_DELAY_BASE)
    """
    if delay_between is None:
        delay_between = TM_DELAY_BASE

    reports: List[str] = []
    for idx, name in enumerate(team_names, start=1):
        try:
            rep = await sync_roster_for_team(name, tournament_code=tournament_code)
            reports.append(rep)
        except Exception as e:
            logger.exception("sync_multiple_teams error for %s", name)
            reports.append(f"{name}: error {e}")
        if idx < len(team_names):
            # случайная добавка
            await asyncio.sleep(delay_between + random.uniform(0, TM_DELAY_JITTER))
    return reports
