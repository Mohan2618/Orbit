"""Add recurring QA run schedules."""

from alembic import op
import sqlalchemy as sa

revision = "0002_schedules"
down_revision = "0001_test_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_schedules",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("repository_url", sa.String(length=2048), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("interval_minutes >= 15 AND interval_minutes <= 43200", name="ck_schedule_interval"),
    )
    op.create_index("ix_run_schedules_next_run_at", "run_schedules", ["next_run_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_run_schedules_next_run_at", table_name="run_schedules")
    op.drop_table("run_schedules")
