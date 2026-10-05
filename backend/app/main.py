from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.repositories import router as repositories_router
from app.core.config import PROJECT_NAME, PROJECT_VERSION, SERVICE_NAME
from app.schemas.status import ServiceStatus

app = FastAPI(
    title=f"{PROJECT_NAME} API",
    version=PROJECT_VERSION,
    description="The API foundation for Orbit, an autonomous software QA platform.",
)

app.include_router(health_router)
app.include_router(repositories_router)


@app.get("/", response_model=ServiceStatus, tags=["service"])
def service_info() -> ServiceStatus:
    """Identify the running Orbit service."""
    return ServiceStatus()
