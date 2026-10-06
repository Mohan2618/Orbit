from pathlib import Path, PurePosixPath
import tempfile

from fastapi import APIRouter, HTTPException

from app.schemas.ml_evaluation import MLEvaluationRequest
from app.services.ml_evaluation import EvaluationInputError, evaluate_file
from app.services.repository_archive import download_repository
from app.services.repository_intelligence import parse_github_repository_url

router = APIRouter(prefix="/api/v1/ml-evaluations", tags=["ml-evaluation"])


@router.post("")
async def evaluate_predictions(request: MLEvaluationRequest) -> dict:
    """Compute classification or regression metrics from explicit columns in a bounded public artifact."""
    try:
        repository = parse_github_repository_url(request.repository_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    relative = PurePosixPath(request.source_path)
    if "\\" in request.source_path or ":" in request.source_path or relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.suffix.lower() not in {".csv", ".jsonl"}:
        raise HTTPException(status_code=422, detail="source_path must identify a relative .csv or .jsonl file in the repository.")
    with tempfile.TemporaryDirectory(prefix="orbit-evaluation-") as temporary:
        source = Path(temporary) / "source"
        try:
            await download_repository(request.repository_url, source)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="The public repository artifact could not be fetched.") from exc
        artifact = source.joinpath(*relative.parts)
        try:
            resolved = artifact.resolve(strict=True)
            if not resolved.is_relative_to(source.resolve()) or not resolved.is_file():
                raise ValueError
            report = evaluate_file(resolved, request.label_column, request.prediction_column, request.task_type)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc) or "The selected prediction artifact is invalid.") from exc
    return {
        "repository_url": f"https://github.com/{repository.owner}/{repository.name}",
        "source_path": relative.as_posix(),
        "label_column": request.label_column,
        "prediction_column": request.prediction_column,
        **report,
    }
