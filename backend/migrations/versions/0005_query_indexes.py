"""Add indexes used by dashboard and retention queries."""

from alembic import op

revision = "0005_query_indexes"
down_revision = "0004_generated_tests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_test_runs_created_at", "test_runs", ["created_at"], unique=False)
    op.create_index("ix_generated_tests_created_at", "generated_tests", ["created_at"], unique=False)
    op.create_index("ix_github_deliveries_received_at", "github_deliveries", ["received_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_github_deliveries_received_at", table_name="github_deliveries")
    op.drop_index("ix_generated_tests_created_at", table_name="generated_tests")
    op.drop_index("ix_test_runs_created_at", table_name="test_runs")
