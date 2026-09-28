from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(primary_key=True)
    adcm_mission_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    mission_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    snapshots: Mapped[list[LineupSnapshot]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )


class LineupSnapshot(Base):
    __tablename__ = "lineup_snapshots"
    __table_args__ = (
        UniqueConstraint("mission_id", "source_hash", name="uq_snapshot_mission_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mission_id: Mapped[int] = mapped_column(ForeignKey("missions.id"), index=True)
    root_unit_id: Mapped[int] = mapped_column(Integer)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_payload: Mapped[str] = mapped_column(Text)

    mission: Mapped[Mission] = relationship(back_populates="snapshots")
    units: Mapped[list[Unit]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    positions: Mapped[list[Position]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "adcm_unit_id", name="uq_unit_snapshot_adcm"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("lineup_snapshots.id"), index=True)
    adcm_unit_id: Mapped[int] = mapped_column(Integer, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    short_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    call_sign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)

    snapshot: Mapped[LineupSnapshot] = relationship(back_populates="units")
    positions: Mapped[list[Position]] = relationship(back_populates="unit")


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "adcm_position_id", name="uq_position_snapshot_adcm"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("lineup_snapshots.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    adcm_position_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    call_sign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_member_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    snapshot: Mapped[LineupSnapshot] = relationship(back_populates="positions")
    unit: Mapped[Unit] = relationship(back_populates="positions")
    assignment: Mapped[Assignment] = relationship(
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    adcm_member_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    forum_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("lineup_snapshots.id"), index=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), unique=True)
    member_record_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    adcm_participation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adcm_member_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    member_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    member_forum_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assignment_state: Mapped[str] = mapped_column(String(32), index=True)

    snapshot: Mapped[LineupSnapshot] = relationship(back_populates="assignments")
    position: Mapped[Position] = relationship(back_populates="assignment")


class SyncState(Base):
    __tablename__ = "sync_states"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    next_mission_id: Mapped[int] = mapped_column(Integer, default=0)
    last_found_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scanned_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    initial_scan_complete: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="idle")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
