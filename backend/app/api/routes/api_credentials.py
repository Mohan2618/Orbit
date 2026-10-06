from datetime import datetime, timezone
import hashlib
import hmac
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_credential import ApiCredential
from app.schemas.api_credential import ApiCredentialCreated, ApiCredentialRequest, ApiCredentialResponse

router = APIRouter(prefix="/api/v1/admin/api-keys", tags=["team-credentials"])
MAX_ACTIVE_CREDENTIALS = 100


def require_admin_key(authorization: str | None = Header(default=None)) -> None:
    import os

    master_key = os.getenv("ORBIT_API_KEY", "")
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not master_key or not supplied or not hmac.compare_digest(supplied, master_key):
        raise HTTPException(status_code=403, detail="The Orbit administrator key is required for credential management.")


@router.post("", response_model=ApiCredentialCreated, status_code=status.HTTP_201_CREATED)
def create_api_credential(
    request: ApiCredentialRequest,
    _: None = Depends(require_admin_key),
    session: Session = Depends(get_db),
) -> dict:
    active_count = session.scalar(
        select(func.count()).select_from(ApiCredential).where(ApiCredential.revoked_at.is_(None))
    ) or 0
    if active_count >= MAX_ACTIVE_CREDENTIALS:
        raise HTTPException(status_code=429, detail="The active team credential limit has been reached.")
    token = "orbt_" + secrets.token_urlsafe(32)
    credential = ApiCredential(
        name=request.name.strip(),
        key_prefix=token[:12],
        key_hash=hashlib.sha256(token.encode()).hexdigest(),
    )
    session.add(credential)
    session.commit()
    session.refresh(credential)
    return {**ApiCredentialResponse.from_orm(credential).dict(), "token": token}


@router.get("", response_model=list[ApiCredentialResponse])
def list_api_credentials(
    _: None = Depends(require_admin_key), session: Session = Depends(get_db)
) -> list[ApiCredential]:
    return list(session.scalars(select(ApiCredential).order_by(ApiCredential.created_at.desc()).limit(200)))


@router.post("/{credential_id}/revoke", response_model=ApiCredentialResponse)
def revoke_api_credential(
    credential_id: str,
    _: None = Depends(require_admin_key),
    session: Session = Depends(get_db),
) -> ApiCredential:
    credential = session.get(ApiCredential, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="Team API key not found.")
    if credential.revoked_at is None:
        credential.revoked_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(credential)
    return credential
