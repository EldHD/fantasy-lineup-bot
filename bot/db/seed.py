import datetime as dt
from sqlalchemy import select, func, delete
from .database import engine, SessionLocal
from .models import (
    Base, Tournament, Team, Match,
    Player, Prediction, PlayerStatus
)


# --- Наборы игроков (реальные примеры) ---
ZENIT = [
    (41, "Mikhail Kerzhakov", "goalkeeper", "GK"),
    (5,  "Wendel", "midfielder", "CM"),
    (11, "Claudinho", "midfielder", "AM"),
    (10, "Malcom", "forward", "RW"),
    (9,  "Ivan Sergeev", "forward", "CF"),
]
CSKA = [
    (35, "Igor Akinfeev", "goalkeeper", "GK"),
    (6,  "Moises", "defender", "RB"),
    (19, "Jorge Carrascal", "midfielder", "AM"),
    (10, "Fedor Chalov", "forward", "CF"),
    (9,  "Anton Zabolotny", "forward", "CF"),
]
ARS = [
    (1,  "Aaron Ramsdale", "goalkeeper", "GK"),
    (6,  "Gabriel", "defender", "CB"),
    (5,  "Thomas Partey", "midfielder", "DM"),
    (8,  "Martin Odegaard", "midfielder", "AM"),
    (9,  "Gabriel Jesus", "forward", "CF"),
]
CHE = [
    (1,  "Djordje Petrovic", "goalkeeper", "GK"),
    (6,  "Thiago Silva", "defender", "CB"),
    (8,  "Enzo Fernandez", "midfielder", "CM"),
    (23, "Conor Gallagher", "midfielder", "CM"),
    (15, "Nicolas Jackson", "forward", "CF"),
]


async def _create_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _base_seed_if_empty(session):
    """Создать турниры, команды, матчи если их ещё нет."""
    exists = await session.execute(select(Tournament.id).limit(1))
    if exists.first():
        return False   # уже есть
    now = dt.datetime.now(dt.timezone.utc)

    rpl = Tournament(code="rpl", name="Russian Premier League")
    epl = Tournament(code="epl", name="Premier League")
    session.add_all([rpl, epl])
    await session.flush()

    zen = Team(tournament_id=rpl.id, code="ZEN", name="Zenit")
    csk = Team(tournament_id=rpl.id, code="CSK", name="CSKA Moscow")
    ars = Team(tournament_id=epl.id, code="ARS", name="Arsenal")
    che = Team(tournament_id=epl.id, code="CHE", name="Chelsea")
    session.add_all([zen, csk, ars, che])
    await session.flush()

    m1 = Match(
        tournament_id=rpl.id,
        round="Matchday 1",
        utc_kickoff=now + dt.timedelta(hours=10),
        home_team_id=zen.id,
        away_team_id=csk.id
    )
    m2 = Match(
        tournament_id=epl.id,
        round="Matchweek 1",
        utc_kickoff=now + dt.timedelta(hours=15),
        home_team_id=ars.id,
        away_team_id=che.id
    )
    session.add_all([m1, m2])
    await session.flush()
    return True


async def _players_seed_if_empty(session):
    """Добавить игроков/предикты/статусы если игроков ещё нет."""
    count_players = await session.scalar(select(func.count(Player.id)))
    if count_players and count_players > 0:
        return False

    # Получаем команды по кодам
    teams_by_code = {}
    teams = (await session.execute(select(Team))).scalars().all()
    for t in teams:
        teams_by_code[t.code] = t

    def mk_players(team, data):
        objs = []
        for num, name, pmain, pdetail in data:
            objs.append(Player(
                team_id=team.id,
                full_name=name,
                shirt_number=num,
                position_main=pmain,
                position_detail=pdetail
            ))
        return objs

    players = []
    if "ZEN" in teams_by_code:
        players += mk_players(teams_by_code["ZEN"], ZENIT)
    if "CSK" in teams_by_code:
        players += mk_players(teams_by_code["CSK"], CSKA)
    if "ARS" in teams_by_code:
        players += mk_players(teams_by_code["ARS"], ARS)
    if "CHE" in teams_by_code:
        players += mk_players(teams_by_code["CHE"], CHE)
    session.add_all(players)
    await session.flush()

    # Матчи
    matches = (await session.execute(select(Match))).scalars().all()
    if len(matches) < 2:
        # На случай если кто-то чистил таблицы частично
        return True

    # Простейшие предикты
    predictions = []
    for p in players:
        # Привяжем по турниру: RPL -> первый матч, EPL -> второй (упрощённо)
        if p.team.code in ("ZEN", "CSK"):
            match = next(m for m in matches if m.tournament.code == "rpl")
        else:
            match = next(m for m in matches if m.tournament.code == "epl")
        base_prob = 90
        variance = (p.id % 5) * 3
        probability = max(65, min(95, base_prob - variance))
        predictions.append(Prediction(
            match_id=match.id,
            player_id=p.id,
            will_start=True,
            probability=probability,
            explanation="Baseline prediction (demo)"
        ))
    session.add_all(predictions)
    await session.flush()

    # Статусы (пример)
    name_to_player = {p.full_name: p for p in players}
    statuses = []
    for nm, avail, reason in [
        ("Malcom", "DOUBT", "Minor knock"),
        ("Anton Zabolotny", "OUT", "Muscle injury"),
        ("Gabriel Jesus", "OUT", "Knee issue"),
        ("Enzo Fernandez", "DOUBT", "Illness"),
    ]:
        if nm in name_to_player:
            statuses.append(PlayerStatus(
                player_id=name_to_player[nm].id,
                type="injury",
                availability=avail,
                reason=reason,
                source_url="https://example.com/source"
            ))
    session.add_all(statuses)
    await session.flush()
    return True


async def auto_seed():
    await _create_schema()
    async with SessionLocal() as session:
        base_added = await _base_seed_if_empty(session)
        players_added = await _players_seed_if_empty(session)
        if base_added or players_added:
            await session.commit()
            print("Seed: base_added=%s players_added=%s" % (base_added, players_added))
        else:
            # ничего не добавляли
            pass


# Опционально принудительный ресид (ОСТОРОЖНО – демо: очищает игроков/предикты/статусы и пересоздаёт)
async def force_players_reset():
    async with SessionLocal() as session:
        # Удаляем связанные записи
        await session.execute(delete(PlayerStatus))
        await session.execute(delete(Prediction))
        await session.execute(delete(Player))
        await session.commit()
        print("Force reset: cleared players/predictions/statuses.")
        # После очистки снова добавим
        await _players_seed_if_empty(session)
        await session.commit()
        print("Force reset: re-seeded players/predictions/statuses.")
