from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Assignment, LineupSnapshot, Mission, Position, SyncState, Unit


STATE_KEY = "mission_scan"


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
        if snapshot_ids:
            session.execute(delete(Assignment).where(Assignment.snapshot_id.in_(snapshot_ids)))
            session.execute(delete(Position).where(Position.snapshot_id.in_(snapshot_ids)))
            session.execute(delete(Unit).where(Unit.snapshot_id.in_(snapshot_ids)))
            session.execute(delete(LineupSnapshot).where(LineupSnapshot.id.in_(snapshot_ids)))
        session.execute(delete(Mission).where(Mission.id == mission_id))
    state = session.get(SyncState, STATE_KEY)
    if state is not None and state.initial_scan_complete:
        state.imported_count = session.scalar(select(func.count()).select_from(Mission)) or 0

    if mission_ids or state is not None:
        session.commit()
    return len(mission_ids)
