from datetime import datetime

from pydantic import BaseModel, Field


class ScheduleRequest(BaseModel):
    repository_url: str = Field(..., max_length=2048)
    interval_minutes: int = Field(..., ge=15, le=43_200)


class ScheduleResponse(BaseModel):
    id: str
    repository_url: str
    interval_minutes: int
    enabled: bool
    next_run_at: datetime
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
