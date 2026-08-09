"""Store per-SKU generation context and quality trace.

Revision ID: 8a06gencontext
Revises: 8a05addjobitems
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8a06gencontext"
down_revision: str | Sequence[str] | None = "8a05addjobitems"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_items",
        sa.Column(
            "generation_context",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("job_items", "generation_context")
