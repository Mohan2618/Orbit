from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GitHubDelivery(Base):
    __tablename__ = "github_deliveries"

    delivery_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
