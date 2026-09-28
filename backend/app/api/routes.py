from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LineupSnapshot, Mission, SyncState
from app.services.adcm_client import AdcmError
from app.services.automatic_import import STATE_KEY, scan_is_running
from app.services.lineup_import import MissionIgnored, import_mission
from app.services.statistics import (
    latest_snapshot,
    lineup_tree,
    member_detail,
    member_statistics,
    overall_statistics,
    overview_for,
)


router = APIRouter(prefix="/api")


@router.get("/health")
def health(session: Session = Depends(get_db)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/missions")
def missions(session: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = session.execute(
        select(Mission, func.max(LineupSnapshot.retrieved_at))
        .outerjoin(LineupSnapshot)
        .group_by(Mission.id)
        .order_by(Mission.mission_date.desc(), Mission.id.desc())
    ).all()
    return [
        {
            "id": mission.adcm_mission_id,
            "name": mission.name,
            "mission_date": mission.mission_date,
            "imported_at": mission.imported_at,
            "last_snapshot_at": last_snapshot_at,
        }
        for mission, last_snapshot_at in rows
    ]


@router.post("/missions/{mission_id}/sync")
async def sync_mission(mission_id: int, session: Session = Depends(get_db)) -> dict[str, object]:
    if mission_id <= 0:
        raise HTTPException(status_code=422, detail="Die Mission-ID muss positiv sein")
    try:
        snapshot, created = await import_mission(session, mission_id)
    except MissionIgnored as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AdcmError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return {
        "mission_id": mission_id,
        "snapshot_id": snapshot.id,
        "created": created,
        "retrieved_at": snapshot.retrieved_at,
    }


def _snapshot_or_404(session: Session, mission_id: int | None) -> LineupSnapshot:
    snapshot = latest_snapshot(session, mission_id)
    if snapshot is None:
        message = f"Für Mission {mission_id} existiert kein Datenstand" if mission_id else "Es existiert noch kein Datenstand"
        raise HTTPException(status_code=404, detail=message)
    return snapshot


@router.get("/lineup")
def lineup(
    mission_id: int | None = Query(default=None), session: Session = Depends(get_db)
) -> dict[str, object]:
    snapshot = _snapshot_or_404(session, mission_id)
    mission = session.get(Mission, snapshot.mission_id)
    return {
        "mission": {
            "id": mission.adcm_mission_id,
            "name": mission.name,
            "mission_date": mission.mission_date,
        },
        "snapshot": {"id": snapshot.id, "retrieved_at": snapshot.retrieved_at},
        "units": lineup_tree(session, snapshot),
    }


@router.get("/statistics/overview")
def statistics_overview(
    mission_id: int | None = Query(default=None), session: Session = Depends(get_db)
) -> dict[str, object]:
    snapshot = _snapshot_or_404(session, mission_id)
    mission = session.get(Mission, snapshot.mission_id)
    return {
        "mission": {
            "id": mission.adcm_mission_id,
            "name": mission.name,
            "mission_date": mission.mission_date,
        },
        **overview_for(session, snapshot),
    }


@router.get("/statistics/members")
def statistics_members(
    search: str | None = Query(default=None, max_length=100),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return member_statistics(session, search)


@router.get("/statistics/members/{member_id}")
def statistics_member(
    member_id: int,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    role: str | None = Query(default=None, max_length=255),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="Das Von-Datum darf nicht nach dem Bis-Datum liegen")
    result = member_detail(session, member_id, date_from, date_to, role)
    if result is None:
        raise HTTPException(status_code=404, detail="Mitglied wurde nicht gefunden")
    return result


@router.get("/statistics/overall")
def statistics_overall(session: Session = Depends(get_db)) -> dict[str, object]:
    return overall_statistics(session)


@router.get("/sync/status")
def sync_status(session: Session = Depends(get_db)) -> dict[str, object]:
    state = session.get(SyncState, STATE_KEY)
    if state is None:
        return {
            "status": "starting" if scan_is_running() else "idle",
            "next_mission_id": 0,
            "last_found_id": None,
            "scanned_count": 0,
            "imported_count": 0,
            "initial_scan_complete": False,
            "last_error": None,
            "updated_at": None,
            "last_completed_at": None,
        }
    return {
        "status": "running" if scan_is_running() else state.status,
        "next_mission_id": state.next_mission_id,
        "last_found_id": state.last_found_id,
        "scanned_count": state.scanned_count,
        "imported_count": state.imported_count,
        "initial_scan_complete": bool(state.initial_scan_complete),
        "last_error": state.last_error,
        "updated_at": state.updated_at,
        "last_completed_at": state.last_completed_at,
    }
