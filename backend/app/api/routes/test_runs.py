from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.test_run import TestRun
from app.models.generated_test import GeneratedTest
from app.schemas.test_run import TestRunRequest, TestRunResponse
from app.services.repository_intelligence import parse_github_repository_url
from app.workers.tasks import run_test_run

router = APIRouter(prefix="/api/v1/test-runs", tags=["test-runs"])
MAX_ACTIVE_RUNS = 500


@router.post("", response_model=TestRunResponse, status_code=status.HTTP_202_ACCEPTED)
def create_test_run(
    request: TestRunRequest,
    session: Session = Depends(get_db),
) -> TestRun:
    """Queue a repository's existing pytest suite for sandboxed execution."""
    try:
        parse_github_repository_url(request.repository_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    active_runs = session.scalar(
        select(func.count()).select_from(TestRun).where(TestRun.status.in_(["queued", "running"]))
    ) or 0
    if active_runs >= MAX_ACTIVE_RUNS:
        raise HTTPException(status_code=429, detail="The QA queue is full. Try again after active runs complete.")

    generated_test_id = request.generated_test_id
    if generated_test_id:
        candidate = session.get(GeneratedTest, generated_test_id)
        if candidate is None or not candidate.approved:
            raise HTTPException(status_code=422, detail="Generated test must exist and be approved before a run can use it.")
        expected = parse_github_repository_url(request.repository_url)
        generated_repository = parse_github_repository_url(candidate.repository_url)
        if (expected.owner.casefold(), expected.name.casefold()) != (
            generated_repository.owner.casefold(), generated_repository.name.casefold()
        ):
            raise HTTPException(status_code=422, detail="Generated test belongs to a different repository.")
    test_run = TestRun(repository_url=request.repository_url.strip(), generated_test_id=generated_test_id)
    session.add(test_run)
    session.commit()
    session.refresh(test_run)
    try:
        run_test_run.delay(test_run.id)
    except Exception as exc:
        test_run.status = "failed"
        test_run.error_message = "The QA worker queue is unavailable. Please try again."
        session.commit()
        raise HTTPException(status_code=503, detail=test_run.error_message) from exc
    return test_run


@router.get("", response_model=list[TestRunResponse])
def list_test_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(queued|running|completed|failed)$"),
    session: Session = Depends(get_db),
) -> list[TestRun]:
    query = select(TestRun).order_by(TestRun.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        query = query.where(TestRun.status == status_filter)
    return list(session.scalars(query))


@router.get("/{test_run_id}", response_model=TestRunResponse)
def get_test_run(
    test_run_id: str,
    session: Session = Depends(get_db),
) -> TestRun:
    test_run = session.scalar(select(TestRun).where(TestRun.id == test_run_id))
    if test_run is None:
        raise HTTPException(status_code=404, detail="Test run not found.")
    return test_run
