"""initial_schema

Revision ID: 5911cf02516a
Revises:
Create Date: 2026-06-24 16:16:50.905491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5911cf02516a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Stamp the existing schema as managed by Alembic.

    The tables (tenants, users, jobs, assets, refresh_tokens, api_keys,
    memories, checkpoints) already exist from the previous create_all()
    bootstrap. This revision adds the new audit_logs table and the
    idx_checkpoints_thread index without touching the LangGraph-managed
    checkpoints columns.
    """
    # New table: audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('log_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('success', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=256), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ),
        sa.PrimaryKeyConstraint('log_id'),
    )
    op.create_index('idx_audit_tenant_ts', 'audit_logs', ['tenant_id', 'created_at'])
    op.create_index('idx_audit_user_ts', 'audit_logs', ['user_id', 'created_at'])

    # Add created_at to checkpoints if missing (safe: ADD COLUMN IF NOT EXISTS)
    op.execute("""
        ALTER TABLE checkpoints
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.drop_index('idx_audit_user_ts', table_name='audit_logs')
    op.drop_index('idx_audit_tenant_ts', table_name='audit_logs')
    op.drop_table('audit_logs')
