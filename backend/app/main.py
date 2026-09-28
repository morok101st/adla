from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.database import SessionLocal, init_db
from app.config import settings
from app.services.automatic_import import automatic_import_loop
from app.services.maintenance import (
    backfill_zeus_assignments,
    reconcile_manual_member_assignments,
    remove_ignored_missions,
    remove_superseded_snapshots,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("adla")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("database initialized")
    with SessionLocal() as session:
        removed_snapshots = remove_superseded_snapshots(session)
        if removed_snapshots:
            logger.info("removed superseded mission data count=%s", removed_snapshots)
        removed = remove_ignored_missions(session)
        if removed:
            logger.info("removed ignored missions count=%s", removed)
        reconciled = reconcile_manual_member_assignments(session)
        if reconciled:
            logger.info("reconciled manual default assignments count=%s", reconciled)
        zeus_assignments = backfill_zeus_assignments(session)
        if zeus_assignments:
            logger.info("backfilled Zeus assignments count=%s", zeus_assignments)
    import_task = None
    if settings.auto_import_enabled:
        import_task = asyncio.create_task(automatic_import_loop(), name="adla-auto-import")
        logger.info("automatic mission import enabled")
    try:
        yield
    finally:
        if import_task is not None:
            import_task.cancel()
            try:
                await import_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Airborne Division Lineup Analyzer",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router)
