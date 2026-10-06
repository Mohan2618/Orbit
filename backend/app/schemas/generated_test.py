from datetime import datetime

from pydantic import BaseModel, Field


class GenerateTestRequest(BaseModel):
    repository_url: str = Field(..., max_length=2048)
    source_path: str = Field(..., max_length=1024)
    share_source_with_model: bool = Field(
        ..., description="Must be true to explicitly authorize sending this source file to the configured model provider."
    )


class GeneratedTestResponse(BaseModel):
    id: str
    repository_url: str
    source_path: str
    model: str
    source_digest: str
    source_shared_with_model: bool
    test_code: str
    review_findings: list
    approved: bool
    approved_at: datetime | None = None
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
