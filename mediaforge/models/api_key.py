from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_at: datetime | None = None


class ApiKeyInfo(BaseModel):
    key_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    key_prefix: str
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime | None


class ApiKeyCreatedResponse(ApiKeyInfo):
    plaintext_key: str = Field(
        ...,
        description="Full API key — shown ONCE. Store it securely; it cannot be retrieved again.",
    )
