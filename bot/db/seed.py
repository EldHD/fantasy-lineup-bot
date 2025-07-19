import datetime as dt
from sqlalchemy import select
from .database import engine, SessionLocal
from .models import Base, Tournament, Team, Match, Player, Prediction


async def auto_seed():
    # Создание таблиц
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        existing = await session.execute(select(Tournament).limit(1))
        if existing.first():
            return  # Уже сидировано ранее

        now = dt.datetime.now(dt.timezone.utc)

        # Лиги
        rpl = Tournament(code="rpl", name="Russian Premier League")
        epl = Tournament(code="epl", name="Premier League")
        session.add_all([rpl, epl])
        await session.flush()

        # Команды
        zen = Team(tournament_id=rpl.id, code="ZEN", name="Zenit")
        csk = Team(tournament_id=rpl.id, code="CSK", name="CSKA Moscow")
        ars = Team(tournament_id=epl.id, code="ARS", name="Arsenal")
        che = Team(tournament_id=epl.id, code="CHE", name="Chelsea")
        session.add_all([zen, csk, ars, che])
        await session.flush()

        # Матчи
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

        # Игроки (по 4 на команду для примера)
        players = [
            Player(team_id=zen.id, full_name="Zenit Goalkeeper", shirt_number=1, position_main="goalkeeper", position_detail="GK"),
            Player(team_id=zen.id, full_name="Zenit Centre Back", shirt_number=4, position_main="defender", position_detail="CB"),
            Player(team_id=zen.id, full_name="Zenit Midfielder", shirt_number=8, position_main="midfielder", position_detail="CM"),
            Player(team_id=zen.id, full_name="Zenit Striker", shirt_number=9, position_main="forward", position_detail="CF"),

            Player(team_id=csk.id, full_name="CSKA Goalkeeper", shirt_number=1, position_main="goalkeeper", position_detail="GK"),
            Player(team_id=csk.id, full_name="CSKA Defender", shirt_number=3, position_main="defender", position_detail="CB"),
            Player(team_id=csk.id, full_name="CSKA Winger", shirt_number=11, position_main="forward", position_detail="LW"),
            Player(team_id=csk.id, full_name="CSKA Striker", shirt_number=10, position_main="forward", position_detail="CF"),

            Player(team_id=ars.id, full_name="Arsenal Goalkeeper", shirt_number=1, position_main="goalkeeper", position_detail="GK"),
            Player(team_id=ars.id, full_name="Arsenal Defender", shirt_number=5, position_main="defender", position_detail="CB"),
            Player(team_id=ars.id, full_name="Arsenal Midfielder", shirt_number=10, position_main="midfielder", position_detail="AM"),
            Player(team_id=ars.id, full_name="Arsenal Forward", shirt_number=9, position_main="forward", position_detail="CF"),

            Player(team_id=che.id, full_name="Chelsea Goalkeeper", shirt_number=1, position_main="goalkeeper", position_detail="GK"),
            Player(team_id=che.id, full_name="Chelsea Defender", shirt_number=6, position_main="defender", position_detail="CB"),
            Player(team_id=che.id, full_name="Chelsea Midfielder", shirt_number=8, position_main="midfielder", position_detail="CM"),
            Player(team_id=che.id, full_name="Chelsea Forward", shirt_number=11, position_main="forward", position_detail="LW"),
        ]
        session.add_all(players)
        await session.flush()

        # Простейшие предикты (допустим все стартуют, с разной вероятностью)
        predictions = []
        for p in players:
            # Привяжем к соответствующему матчу (по турниру, упрощённо)
            if p.team_id in (zen.id, csk.id):
                match_id = m1.id
            else:
                match_id = m2.id
            predictions.append(
                Prediction(
                    match_id=match_id,
                    player_id=p.id,
                    will_start=True,
                    probability=80 + (p.id % 10),  # просто варьируем
                    explanation="Базовый предикт (демо)"
                )
            )
        session.add_all(predictions)

        await session.commit()
        print("Seed: initial data with players & predictions inserted.")
