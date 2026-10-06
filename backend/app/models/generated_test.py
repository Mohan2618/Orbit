from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GeneratedTest(Base):
    __tablename__ = "generated_tests"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_shared_with_model: Mapped[bool] = mapped_column(Boolean, nullable=False)
    test_code: Mapped[str] = mapped_column(Text, nullable=False)
    review_findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
