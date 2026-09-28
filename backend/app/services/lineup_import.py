from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Assignment, LineupSnapshot, Member, Mission, Position, Unit
from app.schemas import MissionPayload, ParticipationPayload, UnitPayload
from app.services.adcm_client import AdcmClient


def payload_hash(payload: object) -> tuple[str, str]:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), raw


def assignment_state(default_member_id: int | None, participant: ParticipationPayload | None) -> str:
    if participant is None:
        return "vacant"
    if participant.memberId is None:
        return "guest"
    if default_member_id is None:
        return "assigned"
    if participant.memberId == default_member_id:
        return "regular"
    return "replacement"


def _member_for(session: Session, participant: ParticipationPayload | None) -> Member | None:
    if participant is None or participant.memberId is None:
        return None
    member = session.scalar(select(Member).where(Member.adcm_member_id == participant.memberId))
    now = datetime.now(timezone.utc)
    if member is None:
        member = Member(
            adcm_member_id=participant.memberId,
            forum_id=participant.memberForumId,
            name=(participant.memberName or "Unbekannt").strip() or "Unbekannt",
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(member)
        session.flush()
    else:
        member.name = (participant.memberName or member.name).strip() or member.name
        member.forum_id = participant.memberForumId or member.forum_id
        member.last_seen_at = now
    return member


def _store_unit(
    session: Session,
    snapshot: LineupSnapshot,
    payload: UnitPayload,
    parent_id: int | None = None,
    depth: int = 0,
) -> None:
    unit = Unit(
        snapshot_id=snapshot.id,
        adcm_unit_id=payload.id,
        parent_id=parent_id,
        name=payload.name.strip() or "Unbenannte Einheit",
        short_name=(payload.shortName or "").strip() or None,
        call_sign=(payload.callSign or "").strip() or None,
        depth=depth,
    )
    session.add(unit)
    session.flush()

    for item in payload.positions:
        position = Position(
            snapshot_id=snapshot.id,
            unit_id=unit.id,
            adcm_position_id=item.id,
            name=item.name.strip() or "Unbenannte Position",
            call_sign=(item.callSign or "").strip() or None,
            default_member_id=item.defaultMemberId,
        )
        session.add(position)
        session.flush()
        participant = item.assignedMemberParticipation
        member = _member_for(session, participant)
        session.add(
            Assignment(
                snapshot_id=snapshot.id,
                position_id=position.id,
                member_record_id=member.id if member else None,
                adcm_participation_id=participant.id if participant else None,
                adcm_member_id=participant.memberId if participant else None,
                member_name=(participant.memberName or "").strip() or None if participant else None,
                member_forum_id=participant.memberForumId if participant else None,
                decision=(participant.decision or "").strip() or None if participant else None,
                assignment_state=assignment_state(item.defaultMemberId, participant),
            )
        )

    for child in payload.children:
        _store_unit(session, snapshot, child, unit.id, depth + 1)


async def import_mission(
    session: Session, mission_id: int, client: AdcmClient | None = None
) -> tuple[LineupSnapshot, bool]:
    client = client or AdcmClient()
    mission_payload, mission_raw = await client.get_mission(mission_id)
    root_id = mission_payload.lineUpUnitRoot.id or settings.adcm_root_unit_id
    unit_payload, unit_raw = await client.get_unit(root_id)
    combined = {"mission": mission_raw, "unit": unit_raw}
    source_hash, raw_json = payload_hash(combined)

    mission = session.scalar(select(Mission).where(Mission.adcm_mission_id == mission_id))
    if mission is None:
        mission = Mission(
            adcm_mission_id=mission_id,
            name=mission_payload.missionName.strip() or f"Mission {mission_id}",
            mission_date=mission_payload.missionDate,
            source_url=f"{settings.adcm_base_url}/open-lineup?missionId={mission_id}",
        )
        session.add(mission)
        session.flush()
    else:
        mission.name = mission_payload.missionName.strip() or mission.name
        mission.mission_date = mission_payload.missionDate

    existing = session.scalar(
        select(LineupSnapshot).where(
            LineupSnapshot.mission_id == mission.id,
            LineupSnapshot.source_hash == source_hash,
        )
    )
    if existing is not None:
        session.commit()
        return existing, False

    snapshot = LineupSnapshot(
        mission_id=mission.id,
        root_unit_id=root_id,
        source_hash=source_hash,
        raw_payload=raw_json,
    )
    session.add(snapshot)
    session.flush()
    _store_unit(session, snapshot, unit_payload)
    mission.imported_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(snapshot)
    return snapshot, True
