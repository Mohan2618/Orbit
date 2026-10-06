from datetime import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_test_runs_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    generated_test_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("generated_tests.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
