import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.github_delivery import GitHubDelivery
from app.models.test_run import TestRun
from app.services.repository_intelligence import parse_github_repository_url
from app.workers.tasks import run_test_run

router = APIRouter(prefix="/api/v1/integrations/github", tags=["integrations"])


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    session: Session = Depends(get_db),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> dict:
    """Accept signed push events and enqueue one QA run per GitHub delivery."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="GitHub webhook integration is not configured.")
    declared_size = request.headers.get("content-length")
    if declared_size and (not declared_size.isdigit() or int(declared_size) > 1_048_576):
        raise HTTPException(status_code=413, detail="GitHub webhook payload exceeds the 1 MiB limit.")
    body = await request.body()
    if len(body) > 1_048_576:
        raise HTTPException(status_code=413, detail="GitHub webhook payload exceeds the 1 MiB limit.")
    digest = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(digest, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature.")
    if x_github_event != "push":
        return {"accepted": False, "reason": "Only push events are processed."}
    if not x_github_delivery or len(x_github_delivery) > 100:
        raise HTTPException(status_code=400, detail="Missing GitHub delivery identifier.")
    session.execute(
        delete(GitHubDelivery).where(
            GitHubDelivery.received_at < datetime.now(timezone.utc) - timedelta(days=30)
        )
    )
    if session.get(GitHubDelivery, x_github_delivery) is not None:
        return {"accepted": True, "duplicate": True}
    try:
        payload = json.loads(body)
        repository_url = payload["repository"]["html_url"]
        parse_github_repository_url(repository_url)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="The push payload has no supported public GitHub repository URL.") from exc
    delivery = GitHubDelivery(delivery_id=x_github_delivery, repository_url=repository_url)
    run = TestRun(repository_url=repository_url)
    session.add_all([delivery, run])
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        if session.get(GitHubDelivery, x_github_delivery) is not None:
            return {"accepted": True, "duplicate": True}
        raise
    try:
        run_test_run.delay(run.id)
    except Exception as exc:
        session.delete(delivery)
        run.status = "failed"
        run.error_message = "The QA worker queue is unavailable."
        session.commit()
        raise HTTPException(status_code=503, detail=run.error_message) from exc
    return {"accepted": True, "duplicate": False, "run_id": run.id}
