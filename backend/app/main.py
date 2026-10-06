import hmac
import hashlib
import os
from datetime import datetime, timedelta, timezone

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.health import router as health_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.repositories import router as repositories_router
from app.api.routes.schedules import router as schedules_router
from app.api.routes.test_runs import router as test_runs_router
from app.api.routes.test_generation import router as test_generation_router
from app.api.routes.ml_evaluations import router as ml_evaluations_router
from app.api.routes.api_credentials import router as api_credentials_router
from app.core.config import PROJECT_NAME, PROJECT_VERSION, SERVICE_NAME
from app.core.database import SessionLocal
from app.models.api_credential import ApiCredential
from app.schemas.status import ServiceStatus

app = FastAPI(
    title=f"{PROJECT_NAME} API",
    version=PROJECT_VERSION,
    description="The API foundation for Orbit, an autonomous software QA platform.",
)

app.include_router(health_router)
app.include_router(integrations_router)
app.include_router(dashboard_router)
app.include_router(repositories_router)
app.include_router(schedules_router)
app.include_router(test_runs_router)
app.include_router(test_generation_router)
app.include_router(ml_evaluations_router)
app.include_router(api_credentials_router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")


@app.middleware("http")
async def optional_api_key(request: Request, call_next):
    """Authenticate the master key or a revocable team key when protection is enabled."""
    api_key = os.getenv("ORBIT_API_KEY")
    path = request.url.path
    webhook_path = path == "/api/v1/integrations/github/webhook"
    auth_required = bool(api_key) or os.getenv("ORBIT_AUTH_REQUIRED", "false").lower() == "true"
    if auth_required and path.startswith("/api/v1/") and not webhook_path:
        supplied = request.headers.get("authorization", "")
        token = supplied[7:] if supplied.startswith("Bearer ") else ""
        if api_key and token and hmac.compare_digest(token, api_key):
            return await call_next(request)
        if token:
            try:
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                with SessionLocal() as session:
                    credential = session.scalar(
                        select(ApiCredential).where(
                            ApiCredential.key_hash == token_hash,
                            ApiCredential.revoked_at.is_(None),
                        )
                    )
                    if credential is not None:
                        now = datetime.now(timezone.utc)
                        if credential.last_used_at is None or credential.last_used_at < now - timedelta(minutes=5):
                            credential.last_used_at = now
                            session.commit()
                        return await call_next(request)
            except SQLAlchemyError:
                return JSONResponse(status_code=503, content={"detail": "The API credential store is unavailable."})
        if not token:
            return JSONResponse(status_code=401, content={"detail": "A valid Orbit bearer API key is required."})
        return JSONResponse(status_code=401, content={"detail": "A valid Orbit bearer API key is required."})
    return await call_next(request)


@app.get("/", response_model=ServiceStatus, tags=["service"])
def service_info() -> ServiceStatus:
    """Identify the running Orbit service."""
    return ServiceStatus()
