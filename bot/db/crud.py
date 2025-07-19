import datetime as dt
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .database import SessionLocal
from .models import Tournament, Match, Player, Prediction, Team


async def fetch_matches_by_league(code: str, limit: int = 10):
    async with SessionLocal() as session:
        t_stmt = select(Tournament).where(Tournament.code == code)
        t_res = await session.execute(t_stmt)
        tournament = t_res.scalar_one_or_none()
        if not tournament:
            return []

        stmt = (
            select(Match)
            .where(
                Match.tournament_id == tournament.id,
                Match.utc_kickoff >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
            )
            .order_by(Match.utc_kickoff.asc())
            .limit(limit)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.tournament),
            )
        )
        res = await session.execute(stmt)
        return res.scalars().all()


async def fetch_match_with_teams(match_id: int):
    async with SessionLocal() as session:
        stmt = (
            select(Match)
            .where(Match.id == match_id)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.tournament),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def fetch_team_lineup_predictions(match_id: int, team_id: int):
    """
    Возвращает список (prediction, player) для конкретного матча и команды.
    """
    async with SessionLocal() as session:
        # Вытащим все предикты по матчу
        stmt = (
            select(Prediction)
            .where(Prediction.match_id == match_id)
            .options(
                selectinload(Prediction.player).selectinload(Player.team)
            )
        )
        res = await session.execute(stmt)
        all_preds = res.scalars().all()

        # Отфильтруем по команде
        team_preds = [pr for pr in all_preds if pr.player.team_id == team_id]

        # Можно сортировать, например, по позиции и вероятности
        order = {"goalkeeper": 0, "defender": 1, "midfielder": 2, "forward": 3}
        team_preds.sort(key=lambda pr: (order.get(pr.player.position_main, 99), -pr.probability))
        return team_preds
