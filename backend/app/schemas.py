from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UpstreamModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ParticipationPayload(UpstreamModel):
    id: int | None = None
    memberId: int | None = None
    memberName: str | None = None
    memberForumId: int | None = None
    decision: str | None = None


class PositionPayload(UpstreamModel):
    id: int
    name: str = "Unbenannte Position"
    callSign: str | None = None
    defaultMemberId: int | None = None
    assignedMemberParticipation: ParticipationPayload | None = None


class UnitPayload(UpstreamModel):
    id: int
    name: str = "Unbenannte Einheit"
    shortName: str | None = None
    callSign: str | None = None
    positions: list[PositionPayload] = Field(default_factory=list)
    children: list[UnitPayload] = Field(default_factory=list)


class MissionPayload(UpstreamModel):
    id: int | None = None
    missionId: int
    missionName: str = "Unbenannte Mission"
    missionDate: datetime | None = None
    lineUpUnitRoot: UnitPayload
