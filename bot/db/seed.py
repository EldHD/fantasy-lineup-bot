import datetime as dt
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from .database import engine, SessionLocal
from .models import (
    Base, Tournament, Team, Match,
    Player, Prediction, PlayerStatus
)

# --- Наборы игроков ---
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
    """Создать турниры, команды, матчи если вообще пусто."""
    exists = await session.execute(select(Tournament.id).limit(1))
    if exists.first():
        return False

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
    """
    Добавить игроков / предикты / статусы если ещё нет игроков.
    Избегаем обращения к ленивым связям: работаем через уже загруженные данные.
    """
    count_players = await session.scalar(select(func.count(Player.id)))
    if count_players and count_players > 0:
        return False

    # Подтянем команды (будем использовать их id)
    teams = (await session.execute(select(Team))).scalars().all()
    teams_by_code = {t.code: t for t in teams}

    def mk_players(team_obj, data):
        items = []
        for num, name, pmain, pdetail in data:
            items.append(Player(
                team_id=team_obj.id,
                full_name=name,
                shirt_number=num,
                position_main=pmain,
                position_detail=pdetail
            ))
        return items

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

    # Загрузим матчи с предзагрузкой home/away (чтобы не трогать связи позже)
    matches = (
        await session.execute(
            select(Match).options(
                selectinload(Match.home_team),
                selectinload(Match.away_team)
            )
        )
    ).scalars().all()

    # Определим "матч RPL" и "матч EPL" без обращения к m.tournament:
    # (берём по присутствию соответствующих команд)
    rpl_match = None
    epl_match = None
    rpl_team_codes = {"ZEN", "CSK"}
    epl_team_codes = {"ARS", "CHE"}

    for m in matches:
        home_code = next((t.code for t in teams if t.id == m.home_team_id), None)
        away_code = next((t.code for t in teams if t.id == m.away_team_id), None)
        codes = {home_code, away_code}
        if not rpl_match and codes & rpl_team_codes == codes:
            rpl_match = m
        if not epl_match and codes & epl_team_codes == codes:
            epl_match = m

    # Простейшие предикты
    predictions = []
    for p in players:
        code = next((c for c, t in teams_by_code.items() if t.id == p.team_id), None)
        if code in ("ZEN", "CSK") and rpl_match:
            target_match_id = rpl_match.id
        elif code in ("ARS", "CHE") and epl_match:
            target_match_id = epl_match.id
        else:
            # fallback: если что-то не нашли
            target_match_id = matches[0].id

        base_prob = 90
        variance = (p.id % 5) * 3
        probability = max(65, min(95, base_prob - variance))
        predictions.append(Prediction(
            match_id=target_match_id,
            player_id=p.id,
            will_start=True,
            probability=probability,
            explanation="Baseline prediction (demo)"
        ))

    session.add_all(predictions)
    await session.flush()

    # Статусы (пример)
    name_to_player = {pl.full_name: pl for pl in players}
    statuses_data = [
        ("Malcom", "DOUBT", "Minor knock"),
        ("Anton Zabolotny", "OUT", "Muscle injury"),
        ("Gabriel Jesus", "OUT", "Knee issue"),
        ("Enzo Fernandez", "DOUBT", "Illness"),
    ]
    statuses = []
    for nm, avail, reason in statuses_data:
        pl = name_to_player.get(nm)
        if pl:
            statuses.append(PlayerStatus(
                player_id=pl.id,
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
            print(f"Seed: base_added={base_added} players_added={players_added}")
        else:
            # ничего не добавляли
            pass


# Принудительный ресет игроков / предиктов / статусов
async def force_players_reset():
    async with SessionLocal() as session:
        await session.execute(delete(PlayerStatus))
        await session.execute(delete(Prediction))
        await session.execute(delete(Player))
        await session.commit()
        print("Force reset: cleared players/predictions/statuses.")

        # Повторно добавим
        players_added = await _players_seed_if_empty(session)
        if players_added:
            await session.commit()
            print("Force reset: re-seeded players/predictions/statuses.")
        else:
            print("Force reset: nothing re-seeded (unexpected).")
