"""TenantResolver — async DB-backed identity lookup.

Two resolution paths, in priority order:

1. JWT access token (already verified upstream) → lookup user + tenant by id.
2. X-Api-Key header with a user-created key → DB lookup against
   `api_keys` table by sha256(key) (implemented in P2).

Every method returns `(User, Tenant)` so callers get both principals.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from mediaforge.db.engine import get_engine
from mediaforge.db.tenant_store import TenantStore
from mediaforge.db.user_store import UserStore
from mediaforge.models.tenant import Tenant
from mediaforge.models.user import User

if TYPE_CHECKING:
    pass


class TenantResolver:
    """Async-aware resolver. All public methods are async."""

    def __init__(self) -> None:
        self._engine = get_engine()
        self._tenant_store = TenantStore(self._engine)
        self._user_store = UserStore(self._engine)

    async def resolve_by_jwt(self, user_id: str, tenant_id: str) -> tuple[User, Tenant]:
        user = await self._user_store.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        if user.status != "active":
            raise ValueError("User is suspended")
        tenant = await self._tenant_store.get_by_id(tenant_id)
        if tenant is None:
            raise ValueError("Tenant not found")
        if user.tenant_id != tenant.tenant_id:
            raise ValueError("User/tenant mismatch")
        return user, tenant

    async def resolve_by_api_key(self, api_key: str) -> tuple[User, Tenant]:
        import hashlib
        from datetime import datetime, timezone
        # DB lookup via sha256(key)
        from mediaforge.db.api_key_store import ApiKeyStore
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        store = ApiKeyStore(self._engine)
        row = await store.get_by_hash(key_hash)
        if row is None:
            raise ValueError("Invalid API key")
        if row.get("revoked_at") is not None:
            raise ValueError("API key has been revoked")
        if row.get("expires_at") is not None and row["expires_at"] < datetime.now(timezone.utc):
            raise ValueError("API key has expired")

        tenant = await self._tenant_store.get_by_id(row["tenant_id"])
        if tenant is None:
            raise ValueError("Tenant not found")

        # Resolve the creating user if available, otherwise create a synthetic one
        user: User | None = None
        if row.get("created_by"):
            user = await self._user_store.get_by_id(row["created_by"])
        if user is None:
            user = User(
                user_id=uuid.UUID(int=0),
                tenant_id=tenant.tenant_id,
                email="apikey@mediaforge.local",
                display_name=row.get("name", "API Key"),
                status="active",
            )

        # Fire-and-forget last_used_at update
        try:
            await store.touch_last_used(row["key_id"])
        except Exception:
            pass

        return user, tenant

    def check_quota(self, tenant: Tenant, sku_count: int) -> None:
        q = tenant.quotas
        if sku_count > q.max_skus_per_job:
            raise ValueError(f"Exceeds max_skus_per_job: {q.max_skus_per_job}")

    def check_model_allowed(self, tenant: Tenant, model_alias: str) -> None:
        if model_alias not in tenant.quotas.allowed_models:
            raise ValueError(f"Model {model_alias} not allowed for plan {tenant.plan.value}")
