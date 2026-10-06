import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.health import HealthOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Health check",
    responses={503: {"model": HealthOut, "description": "Database unavailable"}},
)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except OperationalError:
        logger.error("Health check: database unavailable")
        return JSONResponse(status_code=503, content={"status": "error", "database": "unavailable"})
    return HealthOut(status="ok", database="ok")
