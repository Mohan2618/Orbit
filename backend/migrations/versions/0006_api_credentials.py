"""Add individually revocable team API credentials."""

from alembic import op
import sqlalchemy as sa

revision = "0006_api_credentials"
down_revision = "0005_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_credentials",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_api_credentials_key_hash"),
    )
    op.create_index("ix_api_credentials_key_hash", "api_credentials", ["key_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_api_credentials_key_hash", table_name="api_credentials")
    op.drop_table("api_credentials")
