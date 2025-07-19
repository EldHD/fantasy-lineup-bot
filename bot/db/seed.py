import datetime as dt
from sqlalchemy import select
from .database import engine, SessionLocal
from .models import Base, Tournament, Team, Match, Player, Prediction, PlayerStatus


async def auto_seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        exists = await session.execute(select(Tournament).limit(1))
        if exists.first():
            return

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

        def mk_players(team_id, tuples):
            res = []
            for num, name, pmain, pdetail in tuples:
                res.append(Player(
                    team_id=team_id,
                    full_name=name,
                    shirt_number=num,
                    position_main=pmain,
                    position_detail=pdetail
                ))
            return res

        ZENIT = [
            (41, "Mikhail Kerzhakov", "goalkeeper", "GK"),
            (5, "Wendel", "midfielder", "CM"),
            (11, "Claudinho", "midfielder", "AM"),
            (10, "Malcom", "forward", "RW"),
            (9, "Ivan Sergeev", "forward", "CF"),
        ]
        CSKA = [
            (35, "Igor Akinfeev", "goalkeeper", "GK"),
            (6, "Moises", "defender", "RB"),
            (19, "Jorge Carrascal", "midfielder", "AM"),
            (10, "Fedor Chalov", "forward", "CF"),
            (9, "Anton Zabolotny", "forward", "CF"),
        ]
        ARS = [
            (1, "Aaron Ramsdale", "goalkeeper", "GK"),
            (6, "Gabriel", "defender", "CB"),
            (5, "Thomas Partey", "midfielder", "DM"),
            (8, "Martin Odegaard", "midfielder", "AM"),
            (9, "Gabriel Jesus", "forward", "CF"),
        ]
        CHE = [
            (1, "Djordje Petrovic", "goalkeeper", "GK"),
            (6, "Thiago Silva", "defender", "CB"),
            (8, "Enzo Fernandez", "midfielder", "CM"),
            (23, "Conor Gallagher", "midfielder", "CM"),
            (15, "Nicolas Jackson", "forward", "CF"),
        ]

        players = []
        players += mk_players(zen.id, ZENIT)
        players += mk_players(csk.id, CSKA)
        players += mk_players(ars.id, ARS)
        players += mk_players(che.id, CHE)
        session.add_all(players)
        await session.flush()

        # Предикты
        predictions = []
        for p in players:
            match_id = m1.id if p.team_id in (zen.id, csk.id) else m2.id
            base_prob = 90
            variance = (p.id % 5) * 3
            probability = max(65, min(95, base_prob - variance))
            predictions.append(Prediction(
                match_id=match_id,
                player_id=p.id,
                will_start=True,
                probability=probability,
                explanation="Baseline prediction (demo)"
            ))
        session.add_all(predictions)
        await session.flush()

        # Статусы: по одному примеру
        # Допустим Malcom лёгкая травма (doubt), Zabolotny травмирован (OUT), Gabriel Jesus OUT, Enzo doubtful
        name_to_player = {p.full_name: p for p in players}

        statuses = [
            PlayerStatus(
                player_id=name_to_player["Malcom"].id,
                type="injury",
                availability="DOUBT",
                reason="Minor knock, ожидается тест перед матчем",
                source_url="https://example.com/malcom"
            ),
            PlayerStatus(
                player_id=name_to_player["Anton Zabolotny"].id,
                type="injury",
                availability="OUT",
                reason="Muscle injury, пропустит матч",
                source_url="https://example.com/zabolotny"
            ),
            PlayerStatus(
                player_id=name_to_player["Gabriel Jesus"].id,
                type="injury",
                availability="OUT",
                reason="Knee issue, восстановление",
                source_url="https://example.com/jesus"
            ),
            PlayerStatus(
                player_id=name_to_player["Enzo Fernandez"].id,
                type="illness",
                availability="DOUBT",
                reason="Illness, 50/50",
                source_url="https://example.com/enzo"
            ),
        ]
        session.add_all(statuses)

        await session.commit()
        print("Seed: players, predictions, statuses inserted.")
