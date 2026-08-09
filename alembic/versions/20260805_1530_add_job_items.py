"""Add per-SKU execution state for batch jobs.

Revision ID: 8a05addjobitems
Revises: 8a05addproducts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8a05addjobitems"
down_revision: str | Sequence[str] | None = "8a05addproducts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_items",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.job_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sku_id", sa.String(length=255), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("completed_assets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_assets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_job_items_status", "job_items", ["job_id", "status"])


def downgrade() -> None:
    op.drop_table("job_items")
