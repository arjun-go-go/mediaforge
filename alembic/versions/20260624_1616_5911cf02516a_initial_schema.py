"""Create the MediaForge application schema.

Revision ID: 5911cf02516a
Revises:
Create Date: 2026-06-24 16:16:50.905491

The project originally bootstrapped most tables with ``metadata.create_all``.
Consequently the first Alembic revision only created ``audit_logs`` and failed
against a genuinely empty database.  This migration is deliberately
idempotent at the table/index level so it works for both fresh installations
and databases created by the former bootstrap path.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5911cf02516a"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names(schema="public"))


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns)


def upgrade() -> None:
    """Create missing application tables and adopt legacy installations."""
    tables = _existing_tables()

    # PostgreSQL ENUMs are schema objects, so create them independently and
    # tolerate a type left behind by an older/partial bootstrap.
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE jobstatus AS ENUM
                ('pending', 'running', 'done', 'failed', 'partial_fail');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE assetstatus AS ENUM
                ('pending', 'success', 'failed', 'retrying');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )
    job_status = postgresql.ENUM(
        "pending",
        "running",
        "done",
        "failed",
        "partial_fail",
        name="jobstatus",
        create_type=False,
    )
    asset_status = postgresql.ENUM(
        "pending",
        "success",
        "failed",
        "retrying",
        name="assetstatus",
        create_type=False,
    )

    if "tenants" not in tables:
        op.create_table(
            "tenants",
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("api_key_hash", sa.String(length=255), nullable=False),
            sa.Column("plan", sa.String(length=20), nullable=False),
            sa.Column("quotas", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("tenant_id"),
        )
        tables.add("tenants")

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("password_hash", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=100), nullable=True),
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
            sa.PrimaryKeyConstraint("user_id"),
            sa.UniqueConstraint("email"),
        )
        tables.add("users")
    _create_index_if_missing("idx_users_email", "users", ["email"])
    _create_index_if_missing("idx_users_tenant", "users", ["tenant_id"])

    if "refresh_tokens" not in tables:
        op.create_table(
            "refresh_tokens",
            sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("jti", sa.String(length=64), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("user_agent", sa.String(length=256), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
            sa.PrimaryKeyConstraint("token_id"),
            sa.UniqueConstraint("token_hash"),
        )
        tables.add("refresh_tokens")
    _create_index_if_missing("idx_refresh_tokens_user", "refresh_tokens", ["user_id"])
    _create_index_if_missing("idx_refresh_tokens_jti", "refresh_tokens", ["jti"])

    if "api_keys" not in tables:
        op.create_table(
            "api_keys",
            sa.Column("key_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("key_prefix", sa.String(length=12), nullable=False),
            sa.Column("key_hash", sa.String(length=64), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.user_id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
            sa.PrimaryKeyConstraint("key_id"),
            sa.UniqueConstraint("key_hash"),
        )
        tables.add("api_keys")
    _create_index_if_missing("idx_api_keys_prefix", "api_keys", ["key_prefix"])
    _create_index_if_missing("idx_api_keys_tenant", "api_keys", ["tenant_id"])

    if "jobs" not in tables:
        op.create_table(
            "jobs",
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("status", job_status, nullable=False),
            sa.Column("total_skus", sa.Integer(), nullable=False),
            sa.Column("done_skus", sa.Integer(), nullable=False),
            sa.Column("input_data", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
            sa.PrimaryKeyConstraint("job_id"),
        )
        tables.add("jobs")
    _create_index_if_missing("idx_jobs_tenant", "jobs", ["tenant_id", "created_at"])

    if "assets" not in tables:
        op.create_table(
            "assets",
            sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("sku_id", sa.String(length=255), nullable=False),
            sa.Column("output_type", sa.String(length=30), nullable=False),
            sa.Column("platform", sa.String(length=50), nullable=True),
            sa.Column("model_used", sa.String(length=100), nullable=False),
            sa.Column("file_path", sa.Text(), nullable=True),
            sa.Column("status", asset_status, nullable=False),
            sa.Column("error_msg", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
            sa.PrimaryKeyConstraint("asset_id"),
        )
        tables.add("assets")
    _create_index_if_missing("idx_assets_job", "assets", ["job_id"])
    _create_index_if_missing("idx_assets_tenant", "assets", ["tenant_id", "created_at"])

    if "memories" not in tables:
        op.create_table(
            "memories",
            sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("key", sa.String(length=255), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("memory_id"),
        )
        tables.add("memories")
    _create_index_if_missing("idx_memories_tenant_key", "memories", ["tenant_id", "key"])

    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("success", sa.Integer(), nullable=False),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(length=256), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
            sa.PrimaryKeyConstraint("log_id"),
        )
        tables.add("audit_logs")
    _create_index_if_missing("idx_audit_tenant_ts", "audit_logs", ["tenant_id", "created_at"])
    _create_index_if_missing("idx_audit_user_ts", "audit_logs", ["user_id", "created_at"])

    # LangGraph owns its checkpoint schema.  Preserve the legacy compatibility
    # alteration, but only when that table already exists.
    op.execute(
        """
        DO $$ BEGIN
            IF to_regclass('public.checkpoints') IS NOT NULL THEN
                ALTER TABLE checkpoints
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    """Remove the application schema; LangGraph checkpoint tables are separate."""
    for table in (
        "audit_logs",
        "memories",
        "assets",
        "jobs",
        "api_keys",
        "refresh_tokens",
        "users",
        "tenants",
    ):
        op.drop_table(table)
    postgresql.ENUM(name="assetstatus").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="jobstatus").drop(op.get_bind(), checkfirst=True)
