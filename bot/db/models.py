# в начале файла
import datetime as dt
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ...

class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    round: Mapped[str] = mapped_column(String(50))
    utc_kickoff: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)

    # ДОБАВЛЕНО:
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
    )

    tournament: Mapped["Tournament"] = relationship(back_populates="matches")
    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match")
