from pydantic import BaseModel, Field


class MLEvaluationRequest(BaseModel):
    repository_url: str = Field(..., max_length=2048)
    source_path: str = Field(..., max_length=1024)
    label_column: str = Field(..., min_length=1, max_length=200)
    prediction_column: str = Field(..., min_length=1, max_length=200)
    task_type: str = Field(..., pattern="^(classification|regression)$")
