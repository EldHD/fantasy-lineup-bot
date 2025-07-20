import datetime as dt
from typing import Optional, List
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, UniqueConstraint, Index

class Base(DeclarativeBase):
    pass

class Tournament(Base):
    __tablename__ = "tournaments"
    id:   Mapped[int]  = mapped_column(primary_key=True)
    code: Mapped[str]  = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str]  = mapped_column(String(100))

    teams:   Mapped[List["Team"]]  = relationship(back_populates="tournament")
    matches: Mapped[List["Match"]] = relationship(back_populates="tournament")

class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int]  = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(120))

    tournament: Mapped["Tournament"] = relationship(back_populates="teams")

class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    matchday:   Mapped[int]
    status:     Mapped[str] = mapped_column(String(20), default="scheduled")
    utc_kickoff: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    tournament:  Mapped["Tournament"] = relationship(back_populates="matches")
