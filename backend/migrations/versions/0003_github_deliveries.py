"""Record GitHub webhook delivery IDs for idempotency."""

from alembic import op
import sqlalchemy as sa

revision = "0003_github_deliveries"
down_revision = "0002_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_deliveries",
        sa.Column("delivery_id", sa.String(length=100), nullable=False),
        sa.Column("repository_url", sa.String(length=2048), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("delivery_id"),
    )


def downgrade() -> None:
    op.drop_table("github_deliveries")
