import json

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Assignment, LineupSnapshot, Member, Mission, Position, SyncState, Unit
from app.schemas import MissionPayload
from app.services.lineup_import import store_zeus_members


STATE_KEY = "mission_scan"


def backfill_zeus_assignments(session: Session) -> int:
    created = 0
    rows = session.execute(select(LineupSnapshot, Mission).join(Mission)).all()
    for snapshot, mission in rows:
        try:
            raw = json.loads(snapshot.raw_payload)
            payloads = TypeAdapter(list[MissionPayload]).validate_python(raw.get("mission", []))
        except (json.JSONDecodeError, ValidationError, AttributeError):
            continue
        payload = next((item for item in payloads if item.missionId == mission.adcm_mission_id), None)
        if payload is not None:
            created += store_zeus_members(session, snapshot, payload.zeusMembers)
    if created:
        session.commit()
    return created


def _delete_snapshots(session: Session, snapshot_ids: list[int]) -> None:
    if not snapshot_ids:
        return
    session.execute(delete(Assignment).where(Assignment.snapshot_id.in_(snapshot_ids)))
    session.execute(delete(Position).where(Position.snapshot_id.in_(snapshot_ids)))
    session.execute(delete(Unit).where(Unit.snapshot_id.in_(snapshot_ids)))
    session.execute(delete(LineupSnapshot).where(LineupSnapshot.id.in_(snapshot_ids)))


def remove_superseded_snapshots(session: Session) -> int:
    obsolete_ids: list[int] = []
    mission_ids = list(session.scalars(select(Mission.id)))
    for mission_id in mission_ids:
        snapshot_ids = list(
            session.scalars(
                select(LineupSnapshot.id)
                .where(LineupSnapshot.mission_id == mission_id)
                .order_by(LineupSnapshot.retrieved_at.desc(), LineupSnapshot.id.desc())
            )
        )
        obsolete_ids.extend(snapshot_ids[1:])
    _delete_snapshots(session, obsolete_ids)
    if obsolete_ids:
        session.commit()
    return len(obsolete_ids)


def reconcile_manual_member_assignments(session: Session) -> int:
    members_by_name: dict[str, list[Member]] = {}
    for member in session.scalars(select(Member)):
        members_by_name.setdefault(member.name.strip().casefold(), []).append(member)
    rows = session.execute(
        select(Assignment, Position)
        .join(Position, Assignment.position_id == Position.id)
        .where(
            Assignment.adcm_member_id.is_(None),
            Assignment.member_name.is_not(None),
        )
    ).all()
    reconciled = 0
    for assignment, position in rows:
        candidates = members_by_name.get(assignment.member_name.strip().casefold(), [])
        if len(candidates) != 1:
            continue
        member = candidates[0]
        assignment.member_record_id = member.id
        assignment.adcm_member_id = member.adcm_member_id
        if position.default_member_id == member.adcm_member_id:
            assignment.assignment_state = "regular"
        elif position.default_member_id is None:
            assignment.assignment_state = "assigned"
        else:
            assignment.assignment_state = "replacement"
        reconciled += 1
    if reconciled:
        session.commit()
    return reconciled


def remove_ignored_missions(session: Session) -> int:
    mission_ids: list[int] = []
    missions = list(session.scalars(select(Mission)))
    for mission in missions:
        should_remove = "clantreffen" in mission.name.casefold()
        if not should_remove:
            snapshot_id = session.scalar(
                select(func.max(LineupSnapshot.id)).where(LineupSnapshot.mission_id == mission.id)
            )
            if snapshot_id is not None:
                filled = session.scalar(
                    select(func.count())
                    .select_from(Assignment)
                    .where(
                        Assignment.snapshot_id == snapshot_id,
                        Assignment.assignment_state != "vacant",
                    )
                ) or 0
                should_remove = filled == 0
        if should_remove:
            mission_ids.append(mission.id)

    for mission_id in mission_ids:
        snapshot_ids = list(
            session.scalars(
                select(LineupSnapshot.id).where(LineupSnapshot.mission_id == mission_id)
            )
        )
        _delete_snapshots(session, snapshot_ids)
        session.execute(delete(Mission).where(Mission.id == mission_id))
    state = session.get(SyncState, STATE_KEY)
    if state is not None and state.initial_scan_complete:
        state.imported_count = session.scalar(select(func.count()).select_from(Mission)) or 0

    if mission_ids or state is not None:
        session.commit()
    return len(mission_ids)
