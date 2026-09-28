from copy import deepcopy
from datetime import date

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models import Assignment, LineupSnapshot, Member, Mission, Position, SyncState, Unit
from app.schemas import MissionPayload, UnitPayload
from app.services.adcm_client import AdcmClient, AdcmError
from app.services.lineup_import import MissionIgnored, assignment_state, import_mission, payload_hash
from app.services.maintenance import (
    reconcile_manual_member_assignments,
    remove_ignored_missions,
    remove_superseded_snapshots,
)
from app.services.statistics import (
    lineup_tree,
    member_detail,
    member_statistics,
    overall_statistics,
    overview_for,
)


UNIT_PAYLOAD = {
    "id": 13378,
    "name": "Alpha Company",
    "shortName": "A CO",
    "positions": [
        {"id": 1, "name": "CO", "defaultMemberId": 10, "assignedMemberParticipation": {"id": 100, "memberId": 10, "memberName": "Regular Member", "decision": "yes"}},
        {"id": 2, "name": "XO", "defaultMemberId": 20, "assignedMemberParticipation": {"id": 101, "memberId": 21, "memberName": "Replacement Member", "decision": "maybe"}},
        {"id": 3, "name": "1SG", "defaultMemberId": 30, "assignedMemberParticipation": None},
        {"id": 4, "name": "Guest", "defaultMemberId": None, "assignedMemberParticipation": {"id": 102, "memberId": None, "memberName": "Manual Guest", "decision": "custom-value"}},
    ],
    "children": [{"id": 13379, "name": "1st Platoon", "positions": [], "children": [{"id": 13380, "name": "1st Squad", "positions": [], "children": []}]}],
}

MISSION_PAYLOAD = {
    "id": 285,
    "missionId": 762,
    "missionName": "Synthetic Mission",
    "missionDate": "2026-09-25T18:00:00Z",
    "lineUpUnitRoot": {"id": 13378, "name": "Alpha Company", "positions": []},
}


class FakeClient:
    async def get_mission(self, mission_id: int):
        assert mission_id == 762
        return MissionPayload.model_validate(MISSION_PAYLOAD), [MISSION_PAYLOAD]

    async def get_unit(self, unit_id: int):
        assert unit_id == 13378
        return UnitPayload.model_validate(UNIT_PAYLOAD), UNIT_PAYLOAD


class FakeClantreffenClient(FakeClient):
    async def get_mission(self, mission_id: int):
        payload = {**MISSION_PAYLOAD, "missionName": "Clantreffen"}
        return MissionPayload.model_validate(payload), [payload]


class FakeEmptyClient(FakeClient):
    async def get_unit(self, unit_id: int):
        payload = {"id": 13378, "name": "Empty", "positions": [], "children": []}
        return UnitPayload.model_validate(payload), payload


class FakeChangedClient(FakeClient):
    async def get_unit(self, unit_id: int):
        payload = deepcopy(UNIT_PAYLOAD)
        payload["positions"][0]["assignedMemberParticipation"]["decision"] = "maybe"
        return UnitPayload.model_validate(payload), payload


class FakeManualDefaultClient(FakeClient):
    async def get_unit(self, unit_id: int):
        payload = deepcopy(UNIT_PAYLOAD)
        participation = payload["positions"][0]["assignedMemberParticipation"]
        participation["memberId"] = None
        participation["decision"] = "Unknown"
        replacement = payload["positions"][1]["assignedMemberParticipation"]
        replacement["memberId"] = None
        replacement["decision"] = "Unknown"
        return UnitPayload.model_validate(payload), payload


class FakeSecondMissionClient(FakeClient):
    async def get_mission(self, mission_id: int):
        assert mission_id == 763
        payload = {
            **MISSION_PAYLOAD,
            "missionId": 763,
            "missionName": "Second Synthetic Mission",
        }
        return MissionPayload.model_validate(payload), [payload]

    async def get_unit(self, unit_id: int):
        payload = deepcopy(UNIT_PAYLOAD)
        payload["positions"] = payload["positions"][:1]
        payload["positions"][0]["name"] = "PL"
        payload["children"] = []
        return UnitPayload.model_validate(payload), payload


class FakeZeusClient(FakeClient):
    async def get_mission(self, mission_id: int):
        payload = deepcopy(MISSION_PAYLOAD)
        payload["zeusMembers"] = [
            {
                "id": 9001,
                "memberParticipation": {
                    "id": 9101,
                    "memberId": 99,
                    "memberName": "Zeus Member",
                    "decision": "Unknown",
                },
            }
        ]
        return MissionPayload.model_validate(payload), [payload]


def test_assignment_states_cover_vacancy_regular_replacement_and_guest():
    unit = UnitPayload.model_validate(UNIT_PAYLOAD)
    assert assignment_state(10, unit.positions[0].assignedMemberParticipation) == "regular"
    assert assignment_state(20, unit.positions[1].assignedMemberParticipation) == "replacement"
    assert assignment_state(30, None) == "vacant"
    assert assignment_state(None, unit.positions[3].assignedMemberParticipation) == "guest"


def test_schema_accepts_unknown_decisions_and_missing_optional_fields():
    unit = UnitPayload.model_validate(UNIT_PAYLOAD)
    assert unit.positions[3].assignedMemberParticipation.decision == "custom-value"
    assert unit.children[0].callSign is None
    with pytest.raises(ValidationError):
        UnitPayload.model_validate({"name": "Missing stable ID"})


def test_payload_hash_is_deterministic():
    assert payload_hash({"b": 2, "a": 1})[0] == payload_hash({"a": 1, "b": 2})[0]


@pytest.mark.asyncio
async def test_zeus_members_count_as_participants_but_not_staffing_positions(session):
    snapshot, _ = await import_mission(session, 762, FakeZeusClient())

    overview = overview_for(session, snapshot)
    assert overview["participants"] == 4
    assert overview["positions"] == 4
    assert overview["filled"] == 3
    tree = lineup_tree(session, snapshot)
    zeus_unit = next(child for child in tree[0]["children"] if child["name"] == "Zeuse")
    assert zeus_unit["positions"][0]["name"] == "Zeus"
    assert zeus_unit["positions"][0]["counts_for_staffing"] is False

    overall = overall_statistics(session)
    zeus_statistic = next(item for item in overall["unit_statistics"] if item["name"] == "Zeuse")
    assert zeus_statistic["metric_type"] == "attendance"
    assert zeus_statistic["average_participants"] == 1.0
    assert zeus_statistic["average_staffing_rate"] is None

    detail = member_detail(session, 99)
    assert detail is not None
    assert detail["missions_with_assignment"] == 1
    assert detail["roles"] == ["Zeus"]


@pytest.mark.asyncio
async def test_manual_default_member_is_reconciled_as_present(session):
    await import_mission(session, 762, FakeClient())
    snapshot, created = await import_mission(session, 762, FakeManualDefaultClient())
    assert created is True
    assignment = session.scalar(
        select(Assignment)
        .join(Position, Assignment.position_id == Position.id)
        .where(
            Assignment.snapshot_id == snapshot.id,
            Position.adcm_position_id == 1,
        )
    )
    assert assignment is not None
    assert assignment.adcm_member_id == 10
    assert assignment.assignment_state == "regular"
    assert assignment.decision == "Unknown"
    replacement = session.scalar(
        select(Assignment)
        .join(Position, Assignment.position_id == Position.id)
        .where(
            Assignment.snapshot_id == snapshot.id,
            Position.adcm_position_id == 2,
        )
    )
    assert replacement is not None
    assert replacement.adcm_member_id == 21
    assert replacement.assignment_state == "replacement"
    assert replacement.decision == "Unknown"

    assignment.member_record_id = None
    assignment.adcm_member_id = None
    assignment.assignment_state = "guest"
    session.commit()
    assert reconcile_manual_member_assignments(session) == 1
    session.refresh(assignment)
    assert assignment.member_record_id == session.scalar(
        select(Member.id).where(Member.adcm_member_id == 10)
    )
    assert assignment.adcm_member_id == 10
    assert assignment.assignment_state == "regular"


@pytest.mark.asyncio
async def test_recursive_import_snapshot_deduplication_and_statistics(session, monkeypatch):
    monkeypatch.setattr("app.services.lineup_import.AdcmClient", FakeClient)
    snapshot, created = await import_mission(session, 762)
    duplicate, duplicate_created = await import_mission(session, 762)

    assert created is True
    assert duplicate_created is False
    assert duplicate.id == snapshot.id
    assert session.scalar(select(func.count()).select_from(LineupSnapshot)) == 1
    assert session.scalar(select(func.count()).select_from(Unit)) == 3
    assert session.scalar(select(func.count()).select_from(Position)) == 4
    assert session.scalar(select(func.count()).select_from(Assignment)) == 4

    overview = overview_for(session, snapshot)
    assert overview["positions"] == 4
    assert overview["participants"] == 3
    assert overview["vacant"] == 1
    assert overview["regular"] == 1
    assert overview["replacement"] == 1
    assert overview["guest"] == 1
    assert overview["decision_counts"] == {"custom-value": 1, "maybe": 1, "yes": 1}
    tree = lineup_tree(session, snapshot)
    assert tree[0]["children"][0]["children"][0]["name"] == "1st Squad"

    overall = overall_statistics(session)
    assert overall["mission_count"] == 1
    assert overall["average_staffing_rate"] == 75.0
    assert overall["missions_at_least_80_percent"] == 0
    assert overall["average_replacement_rate"] == 25.0
    assert overall["assignment_mix"] == {
        "regular": 1,
        "replacement": 1,
        "other": 1,
        "vacant": 1,
    }
    assert overall["yearly"][0]["period"] == "2026"
    assert overall["yearly"][0]["missions"] == 1
    assert overall["monthly"][0]["period"] == "2026-09"

    people = member_statistics(session, "regular")
    assert len(people) == 1
    assert people[0]["missions_with_assignment"] == 1
    assert people[0]["regular_assignments"] == 1
    assert people[0]["assignment_share"] == 100.0
    assert people[0]["current_role"] == "CO"

    detail = member_detail(session, 10)
    assert detail is not None
    assert detail["history"][0]["role"] == "CO"
    assert detail["available_years"] == [2026]
    assert detail["yearly"][0]["period"] == "2026"
    assert detail["monthly"][0]["period"] == "2026-09"

    filtered = member_detail(session, 10, date(2027, 1, 1), date(2027, 12, 31))
    assert filtered is not None
    assert filtered["missions_with_assignment"] == 0
    assert filtered["observed_missions"] == 0
    assert filtered["attendance_rate"] == 0

    replacement, replacement_created = await import_mission(
        session, 762, FakeChangedClient()
    )
    assert replacement_created is True
    assert session.scalar(select(func.count()).select_from(LineupSnapshot)) == 1
    assert session.scalar(select(func.count()).select_from(Assignment)) == 4
    updated = overview_for(session, replacement)
    assert updated["decision_counts"] == {"custom-value": 1, "maybe": 2}

    await import_mission(session, 763, FakeSecondMissionClient())
    combined = overall_statistics(session)
    assert combined["mission_count"] == 2
    assert combined["missions_at_least_80_percent"] == 1
    assert combined["average_replacement_rate"] == 12.5
    assert combined["yearly"][0]["average_staffing_rate"] == 87.5

    role_detail = member_detail(session, 10, role="PL")
    assert role_detail is not None
    assert role_detail["roles"] == ["CO", "PL"]
    assert role_detail["selected_role"] == "PL"
    assert role_detail["missions_with_assignment"] == 1
    assert role_detail["missions_in_active_period"] == 2
    assert role_detail["attendance_rate"] == 50.0
    assert role_detail["history"][0]["role"] == "PL"


@pytest.mark.asyncio
@pytest.mark.parametrize("client", [FakeClantreffenClient(), FakeEmptyClient()])
async def test_ignored_missions_are_not_imported(session, client):
    with pytest.raises(MissionIgnored):
        await import_mission(session, 762, client)
    assert session.scalar(select(func.count()).select_from(Mission)) == 0


def test_clantreffen_cleanup_removes_existing_entry(session):
    session.add(
        Mission(
            adcm_mission_id=100,
            name="Community Clantreffen",
            mission_date=None,
            source_url="https://example.invalid",
        )
    )
    session.commit()
    session.add(
        SyncState(
            key="mission_scan",
            imported_count=2,
            initial_scan_complete=1,
        )
    )
    session.commit()
    assert remove_ignored_missions(session) == 1
    assert session.scalar(select(func.count()).select_from(Mission)) == 0
    assert session.get(SyncState, "mission_scan").imported_count == 0


def test_superseded_snapshot_cleanup_keeps_only_latest(session):
    mission = Mission(
        adcm_mission_id=101,
        name="Synthetic Mission",
        mission_date=None,
        source_url="https://example.invalid",
    )
    session.add(mission)
    session.flush()
    first = LineupSnapshot(
        mission_id=mission.id,
        root_unit_id=1,
        source_hash="first",
        raw_payload="{}",
    )
    second = LineupSnapshot(
        mission_id=mission.id,
        root_unit_id=1,
        source_hash="second",
        raw_payload="{}",
    )
    session.add_all([first, second])
    session.commit()

    assert remove_superseded_snapshots(session) == 1
    remaining = session.scalar(select(LineupSnapshot))
    assert remaining is not None
    assert remaining.source_hash == "second"


@pytest.mark.asyncio
async def test_malformed_upstream_response_is_rejected(monkeypatch):
    async def invalid_response(*_args, **_kwargs):
        return {"unexpected": True}

    monkeypatch.setattr(AdcmClient, "_get_json", invalid_response)
    with pytest.raises(AdcmError, match="unerwartetes Schema"):
        await AdcmClient().get_unit(13378)


@pytest.mark.asyncio
async def test_timeout_is_reported_as_adcm_error(monkeypatch):
    class TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("synthetic timeout")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: TimeoutClient())
    with pytest.raises(AdcmError, match="ADCM-Abruf fehlgeschlagen"):
        await AdcmClient().get_unit(13378)
