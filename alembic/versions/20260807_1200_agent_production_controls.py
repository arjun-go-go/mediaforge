"""Add durable idempotency metadata for generation jobs.

Revision ID: 8a07agentcontrols
Revises: 8a06gencontext
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8a07agentcontrols"
down_revision: str | Sequence[str] | None = "8a06gencontext"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "jobs", sa.Column("source", sa.String(length=20), nullable=False, server_default="batch")
    )
    op.add_column("jobs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_foreign_key("fk_jobs_created_by_users", "jobs", "users", ["created_by"], ["user_id"])
    op.create_index(
        "uq_jobs_tenant_idempotency",
        "jobs",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_tenant_idempotency", table_name="jobs")
    op.drop_constraint("fk_jobs_created_by_users", "jobs", type_="foreignkey")
    op.drop_column("jobs", "idempotency_key")
    op.drop_column("jobs", "source")
    op.drop_column("jobs", "created_by")
