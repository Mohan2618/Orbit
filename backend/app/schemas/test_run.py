from datetime import datetime
from pydantic import BaseModel, Field


class TestRunRequest(BaseModel):
    repository_url: str = Field(
        ...,
        max_length=2048,
        description="A public Python GitHub repository to run its existing pytest suite, Ruff checks, and coverage collection.",
        example="https://github.com/owner/repository",
    )
    generated_test_id: str | None = Field(
        default=None, description="Optional ID of a reviewed and approved generated test candidate for this repository."
    )


class TestRunResponse(BaseModel):
    id: str
    repository_url: str
    generated_test_id: str | None = None
    status: str
    result: dict | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        orm_mode = True
        from_attributes = True
