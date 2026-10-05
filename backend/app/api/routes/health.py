from fastapi import APIRouter

from app.schemas.status import HealthStatus

router = APIRouter()


@router.get("/health", response_model=HealthStatus, tags=["service"])
def health_check() -> HealthStatus:
    """Report whether the Orbit API process is responding."""
    return HealthStatus()
