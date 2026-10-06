import os

from fastapi import APIRouter, Depends, HTTPException
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.status import HealthStatus, ReadinessStatus

router = APIRouter()


@router.get("/health", response_model=HealthStatus, tags=["service"])
def health_check() -> HealthStatus:
    """Report whether the Orbit API process is responding."""
    return HealthStatus()


@router.get("/ready", response_model=ReadinessStatus, tags=["service"])
def readiness_check(session: Session = Depends(get_db)) -> ReadinessStatus:
    """Report whether the API can reach PostgreSQL and its Redis queue."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is not ready.") from exc

    queue = Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        queue.ping()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Queue is not ready.") from exc
    finally:
        queue.close()
    return ReadinessStatus()
