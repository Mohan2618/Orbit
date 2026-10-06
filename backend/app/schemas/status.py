from pydantic import BaseModel

from app.core.config import PROJECT_NAME, PROJECT_VERSION, SERVICE_NAME


class ServiceStatus(BaseModel):
    name: str = PROJECT_NAME
    service: str = SERVICE_NAME
    version: str = PROJECT_VERSION


class HealthStatus(ServiceStatus):
    status: str = "healthy"


class ReadinessStatus(ServiceStatus):
    status: str = "ready"
    database: str = "healthy"
    queue: str = "healthy"
