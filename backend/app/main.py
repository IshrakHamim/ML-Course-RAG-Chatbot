import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.api import auth, chat, documents, health
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.services.documents import count_stale_chunks

logger = logging.getLogger(__name__)
API_PREFIX = "/api/v1"


def _warn_about_stale_chunks() -> None:
    from app.core.db import SessionLocal

    try:
        with SessionLocal() as db:
            stale = count_stale_chunks(db)
    except OperationalError:
        logger.warning("Database not reachable at startup; is `docker compose up -d db` running?")
        return
    if stale:
        logger.warning(
            "%d chunks were embedded with a different model; run `python -m app.cli reindex`",
            stale,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warn_about_stale_chunks()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="QueryBuddy API",
        version="0.1.0",
        description="Answers questions only from the uploaded knowledge base.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Handle it here, inside the CORS middleware, so the browser can read the 500.
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s %s %.0fms", request.method, request.url.path, response.status_code, elapsed_ms
        )
        return response

    # Added last so it is the outermost middleware and every response gets CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_exception_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    return app


app = create_app()
