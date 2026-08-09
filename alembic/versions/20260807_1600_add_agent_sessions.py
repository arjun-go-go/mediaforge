"""Persist intelligent assistant session directory metadata.

Revision ID: 8a07agentsessions
Revises: 8a07agentcontrols
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8a07agentsessions"
down_revision: str | Sequence[str] | None = "8a07agentcontrols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False, server_default="新对话"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("user_id", "session_id"),
    )
    op.create_index(
        "idx_agent_sessions_tenant_user",
        "agent_sessions",
        ["tenant_id", "user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_sessions_tenant_user", table_name="agent_sessions")
    op.drop_table("agent_sessions")
