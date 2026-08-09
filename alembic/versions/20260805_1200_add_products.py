"""Add products as the source of truth for retrieval data.

Revision ID: 8a05addproducts
Revises: 5911cf02516a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8a05addproducts"
down_revision: str | Sequence[str] | None = "5911cf02516a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("document_id", sa.String(length=160), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=True,
        ),
        sa.Column("sku_code", sa.String(length=64), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("style", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("color", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("material", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("season", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sales_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("index_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_products_tenant", "products", ["tenant_id"])
    op.create_index("idx_products_sku", "products", ["sku_code"])
    op.create_index("idx_products_scope", "products", ["visibility", "tenant_id"])
    op.create_index("idx_products_index_status", "products", ["index_status"])


def downgrade() -> None:
    op.drop_table("products")
