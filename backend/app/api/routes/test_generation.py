from pathlib import Path, PurePosixPath
import hashlib
import tempfile
from datetime import datetime, timezone

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.generated_test import GeneratedTest
from app.models.test_run import TestRun
from app.schemas.generated_test import GenerateTestRequest, GeneratedTestResponse
from app.services.repository_archive import download_repository
from app.services.repository_intelligence import parse_github_repository_url
from app.services.test_generation import TestGenerationError, generate_tests

router = APIRouter(prefix="/api/v1/generated-tests", tags=["test-generation"])


@router.post("", response_model=GeneratedTestResponse, status_code=status.HTTP_201_CREATED)
async def create_generated_test(
    request: GenerateTestRequest, session: Session = Depends(get_db)
) -> GeneratedTest:
    """Generate a candidate pytest module after an explicit source-sharing opt-in."""
    if not request.share_source_with_model:
        raise HTTPException(status_code=400, detail="Set share_source_with_model=true to opt in to external source processing.")
    try:
        repository = parse_github_repository_url(request.repository_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    relative = PurePosixPath(request.source_path)
    if "\\" in request.source_path or ":" in request.source_path or relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.suffix.lower() != ".py":
        raise HTTPException(status_code=422, detail="source_path must name a relative Python file within the repository.")
    with tempfile.TemporaryDirectory(prefix="orbit-generation-") as temporary:
        source = Path(temporary) / "source"
        try:
            await download_repository(request.repository_url, source)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="The public repository source could not be fetched.") from exc
        selected = source.joinpath(*relative.parts)
        try:
            resolved = selected.resolve(strict=True)
            if not resolved.is_relative_to(source.resolve()) or not resolved.is_file():
                raise ValueError
            source_code = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="The selected source file is missing or is not UTF-8 Python text.") from exc
        try:
            code, model, findings = await generate_tests(source_code, relative.as_posix())
        except TestGenerationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    candidate = GeneratedTest(
        repository_url=f"https://github.com/{repository.owner}/{repository.name}",
        source_path=relative.as_posix(),
        model=model,
        source_digest=hashlib.sha256(source_code.encode("utf-8")).hexdigest(),
        source_shared_with_model=True,
        test_code=code,
        review_findings=findings,
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


@router.get("/{candidate_id}", response_model=GeneratedTestResponse)
def get_generated_test(candidate_id: str, session: Session = Depends(get_db)) -> GeneratedTest:
    candidate = session.get(GeneratedTest, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Generated test not found.")
    return candidate


@router.post("/{candidate_id}/approve", response_model=GeneratedTestResponse)
def approve_generated_test(candidate_id: str, session: Session = Depends(get_db)) -> GeneratedTest:
    candidate = session.get(GeneratedTest, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Generated test not found.")
    candidate.approved = True
    candidate.approved_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(candidate)
    return candidate


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generated_test(candidate_id: str, session: Session = Depends(get_db)) -> Response:
    candidate = session.get(GeneratedTest, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Generated test not found.")
    referenced = session.scalar(
        select(TestRun.id).where(TestRun.generated_test_id == candidate_id).limit(1)
    )
    if referenced:
        raise HTTPException(status_code=409, detail="This generated test is attached to a run and cannot be deleted.")
    session.delete(candidate)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
