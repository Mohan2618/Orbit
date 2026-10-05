from fastapi import APIRouter, Depends, HTTPException

from app.schemas.repository import RepositoryAnalysisRequest, RepositoryIntelligence
from app.services.repository_intelligence import (
    GitHubRateLimited,
    GitHubRepositoryAnalyzer,
    GitHubUnavailable,
    RepositoryNotFound,
)

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


def get_repository_analyzer() -> GitHubRepositoryAnalyzer:
    return GitHubRepositoryAnalyzer()


@router.post("/analyze", response_model=RepositoryIntelligence)
async def analyze_repository(
    request: RepositoryAnalysisRequest,
    analyzer: GitHubRepositoryAnalyzer = Depends(get_repository_analyzer),
) -> RepositoryIntelligence:
    """Inspect public GitHub repository metadata and selected manifests."""
    try:
        return await analyzer.analyze(request.repository_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GitHubRateLimited as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GitHubUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
