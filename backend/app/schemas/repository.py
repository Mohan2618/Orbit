from pydantic import BaseModel, Field


class RepositoryAnalysisRequest(BaseModel):
    repository_url: str = Field(
        ...,
        max_length=2048,
        description="An HTTPS URL for a public repository on github.com.",
        example="https://github.com/tiangolo/fastapi",
    )


class RepositoryIntelligence(BaseModel):
    full_name: str
    repository_url: str
    description: str | None = None
    default_branch: str
    languages: list[str]
    frameworks: list[str]
    dependencies: list[str]
    test_frameworks: list[str]
    entry_points: list[str]
    docker_detected: bool
    manifest_files: list[str]
    analyzed_files: int
    file_tree_truncated: bool
