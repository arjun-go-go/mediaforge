import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    partial_fail = "partial_fail"


class AssetStatus(StrEnum):
    pending = "pending"
    success = "success"
    failed = "failed"
    retrying = "retrying"


Base = declarative_base()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class TenantTable(Base):
    __tablename__ = "tenants"

    tenant_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    api_key_hash = Column(String(255), nullable=False)
    plan = Column(String(20), nullable=False, default="starter")
    quotas = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class UserTable(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    email = Column(String(320), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    display_name = Column(String(100), nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_tenant", "tenant_id"),
    )


class RefreshTokenTable(Base):
    __tablename__ = "refresh_tokens"

    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    jti = Column(String(64), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    user_agent = Column(String(256), nullable=True)
    ip_address = Column(String(45), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("idx_refresh_tokens_user", "user_id"),
        Index("idx_refresh_tokens_jti", "jti"),
    )


class ApiKeyTable(Base):
    __tablename__ = "api_keys"

    key_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(12), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("idx_api_keys_prefix", "key_prefix"),
        Index("idx_api_keys_tenant", "tenant_id"),
    )


class JobTable(Base):
    __tablename__ = "jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.pending)
    total_skus = Column(Integer, nullable=False)
    done_skus = Column(Integer, nullable=False, default=0)
    input_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    assets = relationship("AssetTable", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_jobs_tenant", "tenant_id", "created_at"),)


class AssetTable(Base):
    __tablename__ = "assets"

    asset_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    sku_id = Column(String(255), nullable=False)
    output_type = Column(String(30), nullable=False)
    platform = Column(String(50), nullable=True)
    model_used = Column(String(100), nullable=False)
    file_path = Column(Text, nullable=True)
    status = Column(Enum(AssetStatus), nullable=False, default=AssetStatus.pending)
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    job = relationship("JobTable", back_populates="assets")

    __table_args__ = (
        Index("idx_assets_job", "job_id"),
        Index("idx_assets_tenant", "tenant_id", "created_at"),
    )


class MemoryTable(Base):
    __tablename__ = "memories"

    memory_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("idx_memories_tenant_key", "tenant_id", "key"),
    )


class AuditLogTable(Base):
    __tablename__ = "audit_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(64), nullable=False)   # e.g. "login", "logout", "api_key_create"
    success = Column(Integer, nullable=False, default=1)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(256), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("idx_audit_tenant_ts", "tenant_id", "created_at"),
        Index("idx_audit_user_ts", "user_id", "created_at"),
    )
