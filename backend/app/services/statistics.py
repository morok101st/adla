from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assignment, LineupSnapshot, Member, Mission, Position, Unit
from app.services.lineup_import import ZEUS_UNIT_ID


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
    auxiliary_position_ids = set(
        session.scalars(
            select(Position.id)
            .join(Unit, Position.unit_id == Unit.id)
            .where(Position.snapshot_id == snapshot.id, Unit.adcm_unit_id == ZEUS_UNIT_ID)
        )
    )
    staffing_assignments = [
        item for item in assignments if item.position_id not in auxiliary_position_ids
    ]
    states = Counter(item.assignment_state for item in staffing_assignments)
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
        "positions": len(staffing_assignments),
        "filled": len(staffing_assignments) - states["vacant"],
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
    units_by_id = {unit.id: unit for unit in units}
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
                "counts_for_staffing": units_by_id[position.unit_id].adcm_unit_id != ZEUS_UNIT_ID,
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
    auxiliary_position_ids: set[int] = set()
    if snapshot_ids:
        for assignment in session.scalars(
            select(Assignment).where(Assignment.snapshot_id.in_(snapshot_ids)).order_by(Assignment.id)
        ):
            assignments_by_snapshot[assignment.snapshot_id].append(assignment)
        auxiliary_position_ids = set(
            session.scalars(
                select(Position.id)
                .join(Unit, Position.unit_id == Unit.id)
                .where(
                    Position.snapshot_id.in_(snapshot_ids),
                    Unit.adcm_unit_id == ZEUS_UNIT_ID,
                )
            )
        )
    trends: list[dict[str, object]] = []
    totals = Counter()
    for mission, snapshot in snapshot_rows:
        assignments = assignments_by_snapshot[snapshot.id]
        staffing_assignments = [
            item for item in assignments if item.position_id not in auxiliary_position_ids
        ]
        states = Counter(item.assignment_state for item in staffing_assignments)
        participants = {
            ("member", item.adcm_member_id)
            if item.adcm_member_id is not None
            else ("guest", item.adcm_participation_id or item.member_name or item.id)
            for item in assignments
            if item.assignment_state != "vacant"
        }
        overview = {
            "participants": len(participants),
            "positions": len(staffing_assignments),
            "filled": len(staffing_assignments) - states["vacant"],
            "vacant": states["vacant"],
            "regular": states["regular"],
            "replacement": states["replacement"],
            "guest": states["guest"],
            "assigned": states["assigned"],
        }
        for key in (
            "participants",
            "positions",
            "filled",
            "vacant",
            "regular",
            "replacement",
            "guest",
            "assigned",
        ):
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
                "replacement_rate": round(int(overview["replacement"]) / positions * 100, 1)
                if positions
                else 0,
            }
        )
    mission_count = len(trends)

    def period_statistics(format_string: str) -> list[dict[str, object]]:
        buckets: dict[str, list[dict[str, object]]] = {}
        for item in trends:
            mission_date = item["mission_date"]
            if mission_date is None:
                continue
            period = mission_date.strftime(format_string)  # type: ignore[union-attr]
            buckets.setdefault(period, []).append(item)
        return [
            {
                "period": period,
                "missions": len(items),
                "average_participants": round(
                    sum(int(item["participants"]) for item in items) / len(items), 1
                ),
                "average_staffing_rate": round(
                    sum(float(item["staffing_rate"]) for item in items) / len(items), 1
                ),
                "average_vacancies": round(
                    sum(int(item["vacant"]) for item in items) / len(items), 1
                ),
                "average_replacements": round(
                    sum(int(item["replacement"]) for item in items) / len(items), 1
                ),
            }
            for period, items in sorted(buckets.items())
        ]

    units_by_snapshot: dict[int, list[Unit]] = {snapshot_id: [] for snapshot_id in snapshot_ids}
    positions_by_unit: dict[int, list[Position]] = {}
    assignments_by_position: dict[int, Assignment] = {}
    if snapshot_ids:
        for unit in session.scalars(select(Unit).where(Unit.snapshot_id.in_(snapshot_ids))):
            units_by_snapshot[unit.snapshot_id].append(unit)
        for position in session.scalars(
            select(Position).where(Position.snapshot_id.in_(snapshot_ids))
        ):
            positions_by_unit.setdefault(position.unit_id, []).append(position)
        assignments_by_position = {
            assignment.position_id: assignment
            for assignments in assignments_by_snapshot.values()
            for assignment in assignments
        }

    # ADCM creates mission-specific unit IDs. Aggregate the same top-level
    # organizational element across missions by its normalized display name.
    unit_buckets: dict[str, dict[str, object]] = {}
    for mission, snapshot in snapshot_rows:
        units = units_by_snapshot[snapshot.id]
        children: dict[int | None, list[Unit]] = {}
        for unit in units:
            children.setdefault(unit.parent_id, []).append(unit)

        def subtree_unit_ids(root: Unit) -> list[int]:
            result = [root.id]
            for child in children.get(root.id, []):
                result.extend(subtree_unit_ids(child))
            return result

        for unit in (
            item for item in units if item.depth == 1 and item.adcm_unit_id != ZEUS_UNIT_ID
        ):
            unit_ids = subtree_unit_ids(unit)
            assignments = [
                assignments_by_position[position.id]
                for unit_id in unit_ids
                for position in positions_by_unit.get(unit_id, [])
                if position.id in assignments_by_position
            ]
            if not assignments:
                continue
            states = Counter(item.assignment_state for item in assignments)
            positions = len(assignments)
            filled = positions - states["vacant"]
            unit_name = " ".join(unit.name.split()).replace(" (CAV Scouts)", "")
            unit_key = unit_name.casefold()
            bucket = unit_buckets.setdefault(
                unit_key,
                {
                    "unit_id": unit.adcm_unit_id,
                    "name": unit_name,
                    "missions": 0,
                    "staffing_rates": [],
                    "positions": [],
                    "vacancies": [],
                    "replacements": [],
                    "yearly": {},
                },
            )
            bucket["unit_id"] = unit.adcm_unit_id
            bucket["name"] = unit_name
            bucket["missions"] += 1  # type: ignore[operator]
            staffing_rate = filled / positions * 100
            bucket["staffing_rates"].append(staffing_rate)  # type: ignore[union-attr]
            bucket["positions"].append(positions)  # type: ignore[union-attr]
            bucket["vacancies"].append(states["vacant"])  # type: ignore[union-attr]
            bucket["replacements"].append(states["replacement"])  # type: ignore[union-attr]
            if mission.mission_date is not None:
                year = mission.mission_date.strftime("%Y")
                bucket["yearly"].setdefault(year, []).append(staffing_rate)  # type: ignore[union-attr]

    unit_statistics = []
    for bucket in unit_buckets.values():
        missions = int(bucket["missions"])
        unit_statistics.append(
            {
                "unit_id": bucket["unit_id"],
                "name": bucket["name"],
                "metric_type": "staffing",
                "missions": missions,
                "average_staffing_rate": round(sum(bucket["staffing_rates"]) / missions, 1),  # type: ignore[arg-type]
                "average_participants": None,
                "average_positions": round(sum(bucket["positions"]) / missions, 1),  # type: ignore[arg-type]
                "average_vacancies": round(sum(bucket["vacancies"]) / missions, 1),  # type: ignore[arg-type]
                "average_replacements": round(sum(bucket["replacements"]) / missions, 1),  # type: ignore[arg-type]
                "yearly": [
                    {
                        "period": year,
                        "missions": len(rates),
                        "average_staffing_rate": round(sum(rates) / len(rates), 1),
                        "average_participants": None,
                    }
                    for year, rates in sorted(bucket["yearly"].items())  # type: ignore[union-attr]
                ],
            }
        )

    zeus_counts_by_year: dict[str, list[int]] = {}
    zeus_counts: list[int] = []
    for mission, snapshot in snapshot_rows:
        participants = {
            ("member", item.adcm_member_id)
            if item.adcm_member_id is not None
            else ("guest", item.adcm_participation_id or item.member_name or item.id)
            for item in assignments_by_snapshot[snapshot.id]
            if item.position_id in auxiliary_position_ids and item.assignment_state != "vacant"
        }
        count = len(participants)
        zeus_counts.append(count)
        if mission.mission_date is not None:
            zeus_counts_by_year.setdefault(mission.mission_date.strftime("%Y"), []).append(count)
    if any(zeus_counts):
        unit_statistics.append(
            {
                "unit_id": ZEUS_UNIT_ID,
                "name": "Zeuse",
                "metric_type": "attendance",
                "missions": mission_count,
                "average_staffing_rate": None,
                "average_participants": round(sum(zeus_counts) / mission_count, 1),
                "average_positions": None,
                "average_vacancies": None,
                "average_replacements": None,
                "yearly": [
                    {
                        "period": year,
                        "missions": len(counts),
                        "average_staffing_rate": None,
                        "average_participants": round(sum(counts) / len(counts), 1),
                    }
                    for year, counts in sorted(zeus_counts_by_year.items())
                ],
            }
        )
    unit_statistics.sort(key=lambda item: str(item["name"]).casefold())

    return {
        "mission_count": mission_count,
        "average_participants": round(totals["participants"] / mission_count, 1) if mission_count else 0,
        "average_staffing_rate": round(
            sum(float(item["staffing_rate"]) for item in trends) / mission_count, 1
        )
        if mission_count
        else 0,
        "total_filled_observations": totals["filled"],
        "missions_at_least_80_percent": sum(
            1 for item in trends if float(item["staffing_rate"]) >= 80
        ),
        "average_replacement_rate": round(
            sum(float(item["replacement_rate"]) for item in trends) / mission_count, 1
        )
        if mission_count
        else 0,
        "assignment_mix": {
            "regular": totals["regular"],
            "replacement": totals["replacement"],
            "other": totals["guest"] + totals["assigned"],
            "vacant": totals["vacant"],
        },
        "yearly": period_statistics("%Y"),
        "monthly": period_statistics("%Y-%m"),
        "unit_statistics": unit_statistics,
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
    latest_organization_snapshot_id = session.scalar(
        select(LineupSnapshot.id)
        .join(Mission, LineupSnapshot.mission_id == Mission.id)
        .where(LineupSnapshot.id.in_(latest_ids))
        .order_by(Mission.mission_date.desc(), Mission.id.desc())
        .limit(1)
    )
    current_default_roles: dict[int, str] = {}
    if latest_organization_snapshot_id is not None:
        for position in session.scalars(
            select(Position).where(
                Position.snapshot_id == latest_organization_snapshot_id,
                Position.default_member_id.is_not(None),
            )
        ):
            if position.default_member_id is not None:
                current_default_roles[position.default_member_id] = position.name
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
                "current_role": current_default_roles.get(member.adcm_member_id),
                "latest_role": None,
                "latest_role_date": None,
                "decision_counts": Counter(),
                "first_mission_date": None,
                "last_mission_date": None,
                "last_participation": None,
            },
        )
        entry["mission_ids"].add(snapshot.mission_id)  # type: ignore[union-attr]
        entry["roles"].add(position.name)  # type: ignore[union-attr]
        latest_role_date = entry["latest_role_date"]
        if (
            latest_role_date is None
            or (mission.mission_date is not None and mission.mission_date > latest_role_date)
            or (mission.mission_date == latest_role_date and position.name == "Zeus")
        ):
            entry["latest_role"] = position.name
            entry["latest_role_date"] = mission.mission_date
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
        latest_role = entry.pop("latest_role")
        entry.pop("latest_role_date")
        decisions = entry.pop("decision_counts")
        participated = len(mission_ids)
        result.append(
            {
                **entry,
                "current_role": entry["current_role"] or latest_role,
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
    role: str | None = None,
) -> dict[str, object] | None:
    member = session.scalar(select(Member).where(Member.adcm_member_id == member_id))
    if member is None:
        return None
    base_statement = (
        select(Assignment, Position, Mission)
        .join(Position, Assignment.position_id == Position.id)
        .join(LineupSnapshot, Assignment.snapshot_id == LineupSnapshot.id)
        .join(Mission, LineupSnapshot.mission_id == Mission.id)
        .where(
            Assignment.adcm_member_id == member_id,
            Assignment.snapshot_id.in_(latest_snapshot_ids()),
        )
    )
    available_roles = sorted(
        {
            position.name
            for _, position, _ in session.execute(base_statement).all()
        }
    )
    statement = base_statement
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
    selected_role = role.strip() if role and role.strip() else None
    if selected_role is not None:
        rows = [row for row in rows if row[1].name == selected_role]
    all_dates = list(
        session.scalars(select(Mission.mission_date).where(Mission.mission_date.is_not(None)))
    )

    mission_ids: set[int] = set()
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
    missions_in_active_period = 0
    if date_from is not None or date_to is not None:
        missions_in_active_period = len(list(session.scalars(mission_statement)))
    elif first_mission_date is not None and last_mission_date is not None:
        active_period_statement = mission_statement.where(
            Mission.mission_date >= first_mission_date,
            Mission.mission_date <= last_mission_date,
        )
        missions_in_active_period = len(list(session.scalars(active_period_statement)))
    attendance_rate = (
        round(assigned_count / missions_in_active_period * 100, 1)
        if missions_in_active_period
        else 0
    )
    return {
        "member_id": member.adcm_member_id,
        "name": member.name,
        "missions_with_assignment": assigned_count,
        "assignment_share": attendance_rate,
        "observed_missions": missions_in_active_period,
        "attendance_rate": attendance_rate,
        "missions_in_active_period": missions_in_active_period,
        "regular_assignments": states["regular"],
        "replacement_assignments": states["replacement"],
        "roles": available_roles,
        "selected_role": selected_role,
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
