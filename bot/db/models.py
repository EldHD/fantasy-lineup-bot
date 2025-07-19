import datetime as dt
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


# ------------------- Core domain -------------------

class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))

    teams: Mapped[list["Team"]] = relationship(back_populates="tournament")
    matches: Mapped[list["Match"]] = relationship(back_populates="tournament")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)

    # Внешние идентификаторы
    tm_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)        # Transfermarkt
    sf_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)        # Sofascore
    api_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)       # (API-Football / football-data)

    tournament: Mapped["Tournament"] = relationship(back_populates="teams")
    players: Mapped[list["Player"]] = relationship(back_populates="team", cascade="all,delete-orphan")
    home_matches: Mapped[list["Match"]] = relationship(
        back_populates="home_team",
        foreign_keys="[Match.home_team_id]"
    )
    away_matches: Mapped[list["Match"]] = relationship(
        back_populates="away_team",
        foreign_keys="[Match.away_team_id]"
    )

    __table_args__ = (
        UniqueConstraint("tournament_id", "code", name="uq_team_tournament_code"),
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    round: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    utc_kickoff: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))

    tournament: Mapped["Tournament"] = relationship(back_populates="matches")
    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match", cascade="all,delete-orphan")

    __table_args__ = (
        Index("ix_match_tournament_kickoff", "tournament_id", "utc_kickoff"),
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))

    full_name: Mapped[str] = mapped_column(String(140), index=True)
    shirt_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    position_main: Mapped[str] = mapped_column(String(30))             # goalkeeper/defender/midfielder/forward
    position_detail: Mapped[Optional[str]] = mapped_column(String(30)) # CB, DM, RW, etc.

    # Внешние ID
    tm_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    sf_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    api_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc)
    )

    team: Mapped["Team"] = relationship(back_populates="players")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="player", cascade="all,delete-orphan")
    statuses: Mapped[list["PlayerStatus"]] = relationship(back_populates="player", cascade="all,delete-orphan")

    __table_args__ = (
        Index("ix_player_team_name", "team_id", "full_name"),
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))

    will_start: Mapped[bool] = mapped_column(Boolean, default=True)
    probability: Mapped[int] = mapped_column(Integer)  # 0–100
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc)
    )

    match: Mapped["Match"] = relationship(back_populates="predictions")
    player: Mapped["Player"] = relationship(back_populates="predictions")

    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_prediction_match_player"),
    )


# ------------------- Sources & Status -------------------

class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), index=True)
    title: Mapped[Optional[str]] = mapped_column(String(300))
    provider: Mapped[Optional[str]] = mapped_column(String(60))
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc)
    )

    # Связанные статусы
    statuses: Mapped[list["PlayerStatus"]] = relationship(back_populates="source")


class PlayerStatus(Base):
    __tablename__ = "player_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))

    type: Mapped[str] = mapped_column(String(30))  # injury, suspension, covid, rest, etc.
    availability: Mapped[Optional[str]] = mapped_column(String(10))   # OUT / DOUBT / OK
    reason: Mapped[Optional[str]] = mapped_column(String(200))
    raw_status: Mapped[Optional[str]] = mapped_column(Text)
    expected_return: Mapped[Optional[dt.date]] = mapped_column(nullable=True)
    confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0–100 (позже)

    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc)
    )

    player: Mapped["Player"] = relationship(back_populates="statuses")
    source: Mapped[Optional["Source"]] = relationship(back_populates="statuses")

    __table_args__ = (
        Index("ix_status_player_recent", "player_id", "created_at"),
    )
