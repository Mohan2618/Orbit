"""Persist reviewed model-generated tests."""

from alembic import op
import sqlalchemy as sa

revision = "0004_generated_tests"
down_revision = "0003_github_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_tests",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("repository_url", sa.String(length=2048), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("source_shared_with_model", sa.Boolean(), nullable=False),
        sa.Column("test_code", sa.Text(), nullable=False),
        sa.Column("review_findings", sa.JSON(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("test_runs") as batch_op:
        batch_op.add_column(sa.Column("generated_test_id", sa.Uuid(as_uuid=False), nullable=True))
        batch_op.create_foreign_key(
            "fk_test_runs_generated_test_id_generated_tests",
            "generated_tests",
            ["generated_test_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("test_runs") as batch_op:
        batch_op.drop_constraint("fk_test_runs_generated_test_id_generated_tests", type_="foreignkey")
        batch_op.drop_column("generated_test_id")
    op.drop_table("generated_tests")
