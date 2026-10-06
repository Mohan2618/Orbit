from datetime import datetime

from pydantic import BaseModel, Field


class ApiCredentialRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ApiCredentialResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    class Config:
        orm_mode = True
        from_attributes = True


class ApiCredentialCreated(ApiCredentialResponse):
    token: str
