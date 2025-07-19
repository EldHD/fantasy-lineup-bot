import logging
from typing import List, Optional, Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.database import async_session
from bot.db import models

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ
# ---------------------------------------------------------------------------

def _utc_now():
    return datetime.now(timezone.utc)

# Сколько дней считаем «актуальными» статусами (OUT / injury)
ACTIVE_STATUS_DAYS = 21


# ---------------------------------------------------------------------------
# MATCHES
# ---------------------------------------------------------------------------

async def fetch_matches_by_league(league_code: str) -> List[models.Match]:
    """Возвращает список матчей по коду турнира (упорядочено по kickoff_utc)."""
    async with async_session() as session:
        stmt = (
            select(models.Match)
            .join(models.Tournament, models.Match.tournament_id == models.Tournament.id)
            .where(models.Tournament.code == league_code)
            .order_by(models.Match.kickoff_utc.asc().nulls_last())
            .limit(50)
        )
        res = await session.execute(stmt)
        matches = res.scalars().all()
        # Дополняем computed имена команд (если не заданы в модели через relationship)
        for m in matches:
            if not hasattr(m, "home_team_name"):
                # Подгружаем имена команд
                # Если отношения настроены, можно просто m.home_team.name
                pass
        return matches


async def fetch_match_with_teams(match_id: int) -> Optional[models.Match]:
    """Возвращает один матч. Предполагается, что в модели есть relationship."""
    async with async_session() as session:
        stmt = select(models.Match).where(models.Match.id == match_id)
        res = await session.execute(stmt)
        match = res.scalar_one_or_none()
        if match:
            # Можно подгрузить команды (если lazy='selectin' настроено — не нужно)
            pass
        return match


# ---------------------------------------------------------------------------
# PREDICTIONS
# ---------------------------------------------------------------------------

async def fetch_predictions_for_team_match(match_id: int, team_id: int) -> List:
    """
    Возвращает список предиктов (LineupPrediction join Player + статус),
    формирует объекты с атрибутами:
      name, shirt_number, position, position_detail, predicted_prob,
      status, reason_text, is_starting
    """
    async with async_session() as session:
        # JOIN predictions + players
        stmt = (
            select(
                models.LineupPrediction,
                models.Player,
            )
            .join(models.Player, models.LineupPrediction.player_id == models.Player.id)
            .where(
                models.LineupPrediction.match_id == match_id,
                models.LineupPrediction.team_id == team_id
            )
        )
        res = await session.execute(stmt)
        rows = res.all()
        if not rows:
            return []

        # Сбор player_ids
        player_ids = [r.Player.id for r in rows]

        # Статусы игроков (последние)
        cutoff = _utc_now() - timedelta(days=ACTIVE_STATUS_DAYS)
        st_stmt = (
            select(models.PlayerStatus)
            .where(models.PlayerStatus.player_id.in_(player_ids))
        )
        st_res = await session.execute(st_stmt)
        statuses = st_res.scalars().all()
        # Берём самый "свежий" для каждого игрока
        status_map = {}
        for s in statuses:
            created_at = getattr(s, "created_at", None)
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at and created_at < cutoff:
                continue
            prev = status_map.get(s.player_id)
            if not prev or (created_at and getattr(prev, "created_at", None) and created_at > prev.created_at):
                status_map[s.player_id] = s

        enriched = []
        for lp, pl in rows:
            obj = type("PredObj", (), {})()
            obj.player_id = pl.id
            obj.name = pl.full_name
            obj.shirt_number = pl.shirt_number
            obj.position = pl.position_main or ""
            obj.position_detail = pl.position_detail or ""
            obj.predicted_prob = lp.probability
            obj.is_starting = lp.will_start
            obj.status = None
            obj.reason_text = lp.explanation or ""
            st = status_map.get(pl.id)
            if st:
                # если игрок "OUT"
                if st.availability and st.availability.upper() == "OUT":
                    obj.status = "OUT"
                    if st.reason:
                        obj.reason_text = st.reason
            enriched.append(obj)

        return enriched


async def upsert_prediction_stub(
    session: AsyncSession,
    match_id: int,
    team_id: int,
    player_id: int,
    prob: float,
    will_start: bool = False,
    explanation: str = None,
):
    """
    Вставляет или обновляет запись LineupPrediction (по уникальному ключу match_id+team_id+player_id).
    """
    table = models.LineupPrediction.__table__
    stmt = insert(table).values(
        match_id=match_id,
        team_id=team_id,
        player_id=player_id,
        probability=prob,
        will_start=will_start,
        explanation=explanation,
    )
    update_cols = dict(
        probability=prob,
        will_start=will_start,
        explanation=explanation,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["match_id", "team_id", "player_id"],
        set_=update_cols
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# ШАБЛОН: Генерация предиктов для ближайших матчей
# (упрощённо – просто создаём случайные вероятности, если отсутствуют)
# ---------------------------------------------------------------------------

async def generate_predictions_for_upcoming_matches(days_ahead: int = 5) -> int:
    """
    Находит матчи в ближайшие days_ahead дней без предиктов и создаёт stub.
    Возвращает количество матчей, для которых добавлены предикты.
    """
    async with async_session() as session:
        now = _utc_now()
        future = now + timedelta(days=days_ahead)

        # Находим матчи
        m_stmt = (
            select(models.Match)
            .where(
                models.Match.kickoff_utc >= now,
                models.Match.kickoff_utc <= future
            )
            .limit(50)
        )
        m_res = await session.execute(m_stmt)
        matches = m_res.scalars().all()

        # Для каждого матча берём игроков home/away
        updated = 0
        for m in matches:
            # Проверим есть ли уже предикты
            exist_stmt = select(func.count(models.LineupPrediction.id)).where(
                models.LineupPrediction.match_id == m.id
            )
            ex_res = await session.execute(exist_stmt)
            if ex_res.scalar() > 0:
                continue  # уже есть

            # Загружаем игроков двух команд
            p_stmt = select(models.Player).where(models.Player.team_id.in_([m.home_team_id, m.away_team_id]))
            p_res = await session.execute(p_stmt)
            players = p_res.scalars().all()

            if not players:
                continue

            import random
            for p in players:
                # простая модель вероятности
                prob = round(random.uniform(0.45, 0.92), 3)
                will_start = prob > 0.75
                await upsert_prediction_stub(
                    session=session,
                    match_id=m.id,
                    team_id=p.team_id,
                    player_id=p.id,
                    prob=prob,
                    will_start=will_start,
                    explanation="Baseline auto"
                )
            updated += 1

        if updated:
            await session.commit()
        return updated
