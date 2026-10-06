"""Create durable QA run records.

Revision ID: 0001_test_runs
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_test_runs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_runs",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("repository_url", sa.String(length=2048), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_test_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_runs_status", "test_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_test_runs_status", table_name="test_runs")
    op.drop_table("test_runs")
