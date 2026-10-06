import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

AI_BUSY_MESSAGE = "The AI service is busy, please try again."


class AIServiceError(Exception):
    """A Gemini call failed. `kind` is one of: quota, auth, model_not_found, timeout,
    empty, dimension, unavailable."""

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


class NotFoundError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def _ai_error(request: Request, exc: AIServiceError) -> JSONResponse:
    logger.warning("AI service error kind=%s detail=%s", exc.kind, exc.detail)
    return JSONResponse(status_code=503, content={"detail": AI_BUSY_MESSAGE})


async def _db_error(request: Request, exc: OperationalError) -> JSONResponse:
    logger.error("Database unavailable: %s", exc.orig)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.message})


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AIServiceError, _ai_error)
    app.add_exception_handler(OperationalError, _db_error)
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(Exception, _unexpected)
