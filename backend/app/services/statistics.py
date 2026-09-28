from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assignment, LineupSnapshot, Member, Mission, Position, Unit


_member_cache_snapshot_id: int | None = None
_member_cache: list[dict[str, object]] = []


def latest_snapshot(session: Session, mission_id: int | None = None) -> LineupSnapshot | None:
    statement = select(LineupSnapshot).join(Mission)
    if mission_id is not None:
        statement = statement.where(Mission.adcm_mission_id == mission_id)
    return session.scalar(statement.order_by(LineupSnapshot.retrieved_at.desc(), LineupSnapshot.id.desc()))


def latest_snapshot_ids():
    return select(func.max(LineupSnapshot.id)).group_by(LineupSnapshot.mission_id)


def overview_for(session: Session, snapshot: LineupSnapshot) -> dict[str, object]:
    assignments = list(
        session.scalars(
            select(Assignment).where(Assignment.snapshot_id == snapshot.id).order_by(Assignment.id)
        )
    )
    states = Counter(item.assignment_state for item in assignments)
    decisions = Counter((item.decision or "missing") for item in assignments if item.assignment_state != "vacant")
    participant_keys = {
        ("member", item.adcm_member_id)
        if item.adcm_member_id is not None
        else ("guest", item.adcm_participation_id or item.member_name or item.id)
        for item in assignments
        if item.assignment_state != "vacant"
    }
    return {
        "snapshot_id": snapshot.id,
        "retrieved_at": snapshot.retrieved_at,
        "participants": len(participant_keys),
        "positions": len(assignments),
        "filled": len(assignments) - states["vacant"],
        "vacant": states["vacant"],
        "regular": states["regular"],
        "replacement": states["replacement"],
        "guest": states["guest"],
        "assigned_without_default": states["assigned"],
        "decision_counts": dict(sorted(decisions.items())),
    }


def lineup_tree(session: Session, snapshot: LineupSnapshot) -> list[dict[str, object]]:
    units = list(
        session.scalars(select(Unit).where(Unit.snapshot_id == snapshot.id).order_by(Unit.id))
    )
    positions = list(
        session.scalars(select(Position).where(Position.snapshot_id == snapshot.id).order_by(Position.id))
    )
    assignments = {
        item.position_id: item
        for item in session.scalars(select(Assignment).where(Assignment.snapshot_id == snapshot.id))
    }
    position_map: dict[int, list[dict[str, object]]] = {unit.id: [] for unit in units}
    for position in positions:
        assignment = assignments[position.id]
        position_map[position.unit_id].append(
            {
                "id": position.adcm_position_id,
                "name": position.name,
                "call_sign": position.call_sign,
                "default_member_id": position.default_member_id,
                "participant": {
                    "member_id": assignment.adcm_member_id,
                    "name": assignment.member_name,
                }
                if assignment.assignment_state != "vacant"
                else None,
                "decision": assignment.decision,
                "assignment_state": assignment.assignment_state,
            }
        )

    nodes = {
        unit.id: {
            "id": unit.adcm_unit_id,
            "name": unit.name,
            "short_name": unit.short_name,
            "call_sign": unit.call_sign,
            "depth": unit.depth,
            "positions": position_map[unit.id],
            "children": [],
        }
        for unit in units
    }
    roots: list[dict[str, object]] = []
    for unit in units:
        if unit.parent_id is None:
            roots.append(nodes[unit.id])
        else:
            nodes[unit.parent_id]["children"].append(nodes[unit.id])  # type: ignore[union-attr]
    return roots


def overall_statistics(session: Session) -> dict[str, object]:
    snapshot_rows = session.execute(
        select(Mission, LineupSnapshot)
        .join(LineupSnapshot, LineupSnapshot.mission_id == Mission.id)
        .where(LineupSnapshot.id.in_(latest_snapshot_ids()))
        .order_by(Mission.mission_date, Mission.id)
    ).all()
    snapshot_ids = [snapshot.id for _, snapshot in snapshot_rows]
    assignments_by_snapshot: dict[int, list[Assignment]] = {snapshot_id: [] for snapshot_id in snapshot_ids}
    if snapshot_ids:
        for assignment in session.scalars(
            select(Assignment).where(Assignment.snapshot_id.in_(snapshot_ids)).order_by(Assignment.id)
        ):
            assignments_by_snapshot[assignment.snapshot_id].append(assignment)
    trends: list[dict[str, object]] = []
    totals = Counter()
    for mission, snapshot in snapshot_rows:
        assignments = assignments_by_snapshot[snapshot.id]
        states = Counter(item.assignment_state for item in assignments)
        participants = {
            ("member", item.adcm_member_id)
            if item.adcm_member_id is not None
            else ("guest", item.adcm_participation_id or item.member_name or item.id)
            for item in assignments
            if item.assignment_state != "vacant"
        }
        overview = {
            "participants": len(participants),
            "positions": len(assignments),
            "filled": len(assignments) - states["vacant"],
            "vacant": states["vacant"],
            "regular": states["regular"],
            "replacement": states["replacement"],
            "guest": states["guest"],
        }
        for key in ("participants", "positions", "filled", "vacant", "regular", "replacement", "guest"):
            totals[key] += int(overview[key])
        positions = int(overview["positions"])
        trends.append(
            {
                "mission_id": mission.adcm_mission_id,
                "name": mission.name,
                "mission_date": mission.mission_date,
                "participants": overview["participants"],
                "positions": positions,
                "filled": overview["filled"],
                "vacant": overview["vacant"],
                "regular": overview["regular"],
                "replacement": overview["replacement"],
                "staffing_rate": round(int(overview["filled"]) / positions * 100, 1) if positions else 0,
            }
        )
    mission_count = len(trends)
    return {
        "mission_count": mission_count,
        "snapshot_count": session.scalar(select(func.count()).select_from(LineupSnapshot)) or 0,
        "average_participants": round(totals["participants"] / mission_count, 1) if mission_count else 0,
        "average_staffing_rate": round(
            sum(float(item["staffing_rate"]) for item in trends) / mission_count, 1
        )
        if mission_count
        else 0,
        "total_filled_observations": totals["filled"],
        "total_vacant_observations": totals["vacant"],
        "total_replacement_observations": totals["replacement"],
        "trends": trends,
    }


def member_statistics(session: Session, search: str | None = None) -> list[dict[str, object]]:
    global _member_cache_snapshot_id, _member_cache
    current_snapshot_id = session.scalar(select(func.max(LineupSnapshot.id)))
    if current_snapshot_id == _member_cache_snapshot_id:
        if not search or not search.strip():
            return _member_cache
        needle = search.strip().casefold()
        return [
            item
            for item in _member_cache
            if needle in str(item["name"]).casefold()
            or any(needle in str(role).casefold() for role in item["roles"])
        ]

    latest_ids = latest_snapshot_ids()
    statement = (
        select(Assignment, Position, LineupSnapshot, Member, Mission)
        .join(Position, Assignment.position_id == Position.id)
        .join(LineupSnapshot, Assignment.snapshot_id == LineupSnapshot.id)
        .join(Member, Assignment.member_record_id == Member.id)
        .join(Mission, LineupSnapshot.mission_id == Mission.id)
        .where(Assignment.snapshot_id.in_(latest_ids))
        .order_by(Member.name)
    )
    rows = session.execute(
        statement
    ).all()
    total_missions = session.scalar(select(func.count()).select_from(Mission)) or 0
    members: dict[int, dict[str, object]] = {}
    for assignment, position, snapshot, member, mission in rows:
        entry = members.setdefault(
            member.adcm_member_id,
            {
                "member_id": member.adcm_member_id,
                "name": member.name,
                "mission_ids": set(),
                "regular_assignments": 0,
                "replacement_assignments": 0,
                "roles": set(),
                "decision_counts": Counter(),
                "first_mission_date": None,
                "last_mission_date": None,
                "last_participation": None,
            },
        )
        entry["mission_ids"].add(snapshot.mission_id)  # type: ignore[union-attr]
        entry["roles"].add(position.name)  # type: ignore[union-attr]
        entry["decision_counts"][assignment.decision or "missing"] += 1  # type: ignore[index]
        if assignment.assignment_state == "regular":
            entry["regular_assignments"] += 1  # type: ignore[operator]
        elif assignment.assignment_state == "replacement":
            entry["replacement_assignments"] += 1  # type: ignore[operator]
        last = entry["last_participation"]
        if last is None or snapshot.retrieved_at > last:
            entry["last_participation"] = snapshot.retrieved_at
        if mission.mission_date is not None:
            first_date = entry["first_mission_date"]
            last_date = entry["last_mission_date"]
            if first_date is None or mission.mission_date < first_date:
                entry["first_mission_date"] = mission.mission_date
            if last_date is None or mission.mission_date > last_date:
                entry["last_mission_date"] = mission.mission_date

    result = []
    for entry in members.values():
        mission_ids = entry.pop("mission_ids")
        roles = entry.pop("roles")
        decisions = entry.pop("decision_counts")
        participated = len(mission_ids)
        result.append(
            {
                **entry,
                "missions_with_assignment": participated,
                "assignment_share": round(participated / total_missions * 100, 1) if total_missions else 0,
                "observed_missions": total_missions,
                "roles": sorted(roles),
                "decision_counts": dict(sorted(decisions.items())),
            }
        )
    _member_cache = sorted(result, key=lambda item: str(item["name"]).casefold())
    _member_cache_snapshot_id = current_snapshot_id
    if not search or not search.strip():
        return _member_cache
    needle = search.strip().casefold()
    return [
        item
        for item in _member_cache
        if needle in str(item["name"]).casefold()
        or any(needle in str(role).casefold() for role in item["roles"])
    ]


def member_detail(
    session: Session,
    member_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, object] | None:
    member = session.scalar(select(Member).where(Member.adcm_member_id == member_id))
    if member is None:
        return None
    statement = (
        select(Assignment, Position, Mission)
        .join(Position, Assignment.position_id == Position.id)
        .join(LineupSnapshot, Assignment.snapshot_id == LineupSnapshot.id)
        .join(Mission, LineupSnapshot.mission_id == Mission.id)
        .where(
            Assignment.adcm_member_id == member_id,
            Assignment.snapshot_id.in_(latest_snapshot_ids()),
        )
    )
    mission_statement = select(Mission)
    if date_from is not None:
        start = datetime.combine(date_from, time.min)
        statement = statement.where(Mission.mission_date >= start)
        mission_statement = mission_statement.where(Mission.mission_date >= start)
    if date_to is not None:
        end = datetime.combine(date_to, time.max)
        statement = statement.where(Mission.mission_date <= end)
        mission_statement = mission_statement.where(Mission.mission_date <= end)
    rows = session.execute(statement.order_by(Mission.mission_date.desc(), Mission.id.desc())).all()
    observed_missions = list(session.scalars(mission_statement))
    observed_count = len(observed_missions)
    all_dates = list(
        session.scalars(select(Mission.mission_date).where(Mission.mission_date.is_not(None)))
    )

    mission_ids: set[int] = set()
    roles: set[str] = set()
    decisions: Counter[str] = Counter()
    states: Counter[str] = Counter()
    yearly: dict[str, dict[str, object]] = {}
    monthly: dict[str, dict[str, object]] = {}
    history: list[dict[str, object]] = []
    first_mission_date = None
    last_mission_date = None

    def add_period(target: dict[str, dict[str, object]], period: str, mission_id: int, state: str, decision: str) -> None:
        bucket = target.setdefault(
            period,
            {
                "period": period,
                "mission_ids": set(),
                "regular": 0,
                "replacement": 0,
                "other_assignments": 0,
                "decision_counts": Counter(),
            },
        )
        bucket["mission_ids"].add(mission_id)  # type: ignore[union-attr]
        if state == "regular":
            bucket["regular"] += 1  # type: ignore[operator]
        elif state == "replacement":
            bucket["replacement"] += 1  # type: ignore[operator]
        else:
            bucket["other_assignments"] += 1  # type: ignore[operator]
        bucket["decision_counts"][decision] += 1  # type: ignore[index]

    for assignment, position, mission in rows:
        mission_ids.add(mission.id)
        roles.add(position.name)
        decision = assignment.decision or "missing"
        decisions[decision] += 1
        states[assignment.assignment_state] += 1
        if mission.mission_date is not None:
            if first_mission_date is None or mission.mission_date < first_mission_date:
                first_mission_date = mission.mission_date
            if last_mission_date is None or mission.mission_date > last_mission_date:
                last_mission_date = mission.mission_date
            add_period(yearly, mission.mission_date.strftime("%Y"), mission.id, assignment.assignment_state, decision)
            add_period(monthly, mission.mission_date.strftime("%Y-%m"), mission.id, assignment.assignment_state, decision)
        history.append(
            {
                "mission_id": mission.adcm_mission_id,
                "mission_name": mission.name,
                "mission_date": mission.mission_date,
                "role": position.name,
                "call_sign": position.call_sign,
                "assignment_state": assignment.assignment_state,
                "decision": assignment.decision,
            }
        )

    def finalize_periods(source: dict[str, dict[str, object]]) -> list[dict[str, object]]:
        result = []
        for period in sorted(source, reverse=True):
            bucket = source[period]
            result.append(
                {
                    "period": period,
                    "missions_with_assignment": len(bucket["mission_ids"]),
                    "regular": bucket["regular"],
                    "replacement": bucket["replacement"],
                    "other_assignments": bucket["other_assignments"],
                    "decision_counts": dict(sorted(bucket["decision_counts"].items())),  # type: ignore[union-attr]
                }
            )
        return result

    assigned_count = len(mission_ids)
    return {
        "member_id": member.adcm_member_id,
        "name": member.name,
        "missions_with_assignment": assigned_count,
        "assignment_share": round(assigned_count / observed_count * 100, 1) if observed_count else 0,
        "observed_missions": observed_count,
        "regular_assignments": states["regular"],
        "replacement_assignments": states["replacement"],
        "roles": sorted(roles),
        "decision_counts": dict(sorted(decisions.items())),
        "first_mission_date": first_mission_date,
        "last_mission_date": last_mission_date,
        "last_participation": last_mission_date,
        "available_years": sorted({value.year for value in all_dates}, reverse=True),
        "period": {"date_from": date_from, "date_to": date_to},
        "yearly": finalize_periods(yearly),
        "monthly": finalize_periods(monthly),
        "history": history,
    }
