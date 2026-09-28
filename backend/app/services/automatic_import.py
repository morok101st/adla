from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging

from app.config import settings
from app.database import SessionLocal
from app.models import SyncState
from app.services.adcm_client import AdcmClient, AdcmError, MissionNotFound
from app.services.lineup_import import MissionIgnored, import_mission


logger = logging.getLogger("adla.auto_import")
STATE_KEY = "mission_scan"
_scan_lock = asyncio.Lock()


def get_or_create_state(session) -> SyncState:
    state = session.get(SyncState, STATE_KEY)
    if state is None:
        state = SyncState(key=STATE_KEY, next_mission_id=0, status="idle")
        session.add(state)
        session.commit()
    return state


def scan_is_running() -> bool:
    return _scan_lock.locked()


async def run_mission_scan() -> bool:
    if _scan_lock.locked():
        return False

    async with _scan_lock:
        with SessionLocal() as session:
            state = get_or_create_state(session)
            if state.initial_scan_complete:
                logger.info("initial mission scan already completed; automatic import skipped")
                return False
            state.status = "running"
            state.last_error = None
            state.updated_at = datetime.now(timezone.utc)
            session.commit()

            try:
                async with AdcmClient() as client:
                    state = get_or_create_state(session)
                    start_id = max(0, state.next_mission_id)
                    ceiling = settings.auto_import_initial_max_id

                    logger.info("mission scan started start=%s ceiling=%s", start_id, ceiling)
                    for mission_id in range(start_id, ceiling + 1):
                        try:
                            _, created = await import_mission(session, mission_id, client)
                            found = True
                        except (MissionNotFound, MissionIgnored):
                            created = False
                            found = False

                        state = get_or_create_state(session)
                        state.next_mission_id = mission_id + 1
                        state.scanned_count = max(state.scanned_count + 1, mission_id + 1)
                        state.updated_at = datetime.now(timezone.utc)
                        if created:
                            state.imported_count += 1
                        if found:
                            state.last_found_id = max(state.last_found_id or mission_id, mission_id)
                            if created:
                                logger.info("mission discovered mission_id=%s", mission_id)
                        if mission_id % 20 == 0 or created:
                            session.commit()
                        if settings.auto_import_request_delay_ms > 0:
                            await asyncio.sleep(settings.auto_import_request_delay_ms / 1000)

                    state = get_or_create_state(session)
                    state.initial_scan_complete = 1
                    state.status = "idle"
                    state.last_completed_at = datetime.now(timezone.utc)
                    state.updated_at = state.last_completed_at
                    session.commit()
                    logger.info(
                        "mission scan completed scanned=%s imported=%s last_found=%s",
                        state.scanned_count,
                        state.imported_count,
                        state.last_found_id,
                    )
                    return True
            except asyncio.CancelledError:
                state = get_or_create_state(session)
                state.status = "idle"
                state.updated_at = datetime.now(timezone.utc)
                session.commit()
                raise
            except AdcmError as exc:
                session.rollback()
                state = get_or_create_state(session)
                state.status = "error"
                state.last_error = str(exc)[:500]
                state.updated_at = datetime.now(timezone.utc)
                session.commit()
                logger.warning("mission scan stopped error=%s", type(exc).__name__)
                return False
            except Exception as exc:
                session.rollback()
                state = get_or_create_state(session)
                state.status = "error"
                state.last_error = f"Interner Importfehler: {type(exc).__name__}"
                state.updated_at = datetime.now(timezone.utc)
                session.commit()
                logger.exception("mission scan failed")
                return False


async def automatic_import_loop() -> None:
    await run_mission_scan()
