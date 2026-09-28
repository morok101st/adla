from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.database import init_db
from app.config import settings
from app.services.automatic_import import automatic_import_loop


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("adla")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("database initialized")
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
