import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.api import auth, health
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)
API_PREFIX = "/api/v1"


def _load_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        setup_logging("INFO")
        problems = "; ".join(error["msg"].removeprefix("Value error, ") for error in exc.errors())
        logger.error("Invalid configuration: %s", problems)
        raise SystemExit(1) from None


def create_app() -> FastAPI:
    settings = _load_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="ML Course RAG Chatbot API",
        version="0.1.0",
        description="Answers questions only from the uploaded knowledge base.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s %s %.0fms", request.method, request.url.path, response.status_code, elapsed_ms
        )
        return response

    register_exception_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    return app


app = create_app()
