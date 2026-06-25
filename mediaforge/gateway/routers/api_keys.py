"""API Key management — Create / List / Revoke.

All endpoints require an authenticated user (JWT cookie or Bearer).
Keys are scoped to the authenticated user's tenant.
"""

import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException

from mediaforge.db.api_key_store import ApiKeyStore, generate_api_key
from mediaforge.db.audit_store import audit
from mediaforge.db.engine import get_engine
from mediaforge.gateway.dependencies import get_current_principal
from mediaforge.models.api_key import (
    ApiKeyCreateRequest,
    ApiKeyCreatedResponse,
    ApiKeyInfo,
)

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


def _to_info(row: dict) -> ApiKeyInfo:
    return ApiKeyInfo(
        key_id=row["key_id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        key_prefix=row["key_prefix"],
        last_used_at=row.get("last_used_at"),
        expires_at=row.get("expires_at"),
        revoked_at=row.get("revoked_at"),
        created_at=row.get("created_at"),
    )


@router.post("", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    principal=Depends(get_current_principal),
):
    """Create a new API key for the authenticated tenant.

    The full key is returned **once** in `plaintext_key`. It is never stored
    in plaintext and cannot be retrieved again.
    """
    user, tenant = principal

    if body.expires_at is not None and body.expires_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="expires_at must be timezone-aware")

    plaintext, prefix, key_hash = generate_api_key()
    store = ApiKeyStore(get_engine())
    row = await store.create(
        tenant_id=tenant.tenant_id,
        created_by=user.user_id,
        name=body.name,
        key_prefix=prefix,
        key_hash=key_hash,
        expires_at=body.expires_at,
    )
    await audit(
        "api_key_create",
        tenant_id=tenant.tenant_id,
        user_id=user.user_id,
        metadata={"key_id": str(row["key_id"]), "name": body.name},
    )
    return ApiKeyCreatedResponse(
        **_to_info(row).model_dump(),
        plaintext_key=plaintext,
    )


@router.get("", response_model=list[ApiKeyInfo])
async def list_api_keys(principal=Depends(get_current_principal)):
    """List all API keys for the authenticated tenant."""
    _, tenant = principal
    store = ApiKeyStore(get_engine())
    rows = await store.list_for_tenant(tenant.tenant_id)
    return [_to_info(r) for r in rows]


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    principal=Depends(get_current_principal),
):
    """Revoke an API key. Only keys belonging to the authenticated tenant can be revoked."""
    user, tenant = principal
    store = ApiKeyStore(get_engine())
    revoked = await store.revoke(key_id, tenant.tenant_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found or already revoked")
    await audit(
        "api_key_revoke",
        tenant_id=tenant.tenant_id,
        user_id=user.user_id,
        metadata={"key_id": str(key_id)},
    )
