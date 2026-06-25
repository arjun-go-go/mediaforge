"""Tenant-scoped metadata endpoints.

The /me endpoint moved to /api/v1/auth/me (see auth.py). This router
retains only tenant-plan / quota introspection endpoints.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from mediaforge.gateway.dependencies import get_tenant_only
from mediaforge.models.tenant import Tenant, TenantPlan


router = APIRouter(prefix="/api/v1", tags=["tenants"])


class TenantQuotaResponse(BaseModel):
    plan: TenantPlan
    max_concurrent_jobs: int = Field(default=2)
    max_skus_per_job: int = Field(default=50)
    image_credits_monthly: int = Field(default=100)
    video_credits_monthly: int = Field(default=10)
    allowed_models: list[str] = Field(default_factory=lambda: ["fast"])


class TenantInfoResponse(BaseModel):
    tenant_id: str
    name: str
    plan: str
    quotas: TenantQuotaResponse | None


def _build_response(tenant: Tenant) -> TenantInfoResponse:
    return TenantInfoResponse(
        tenant_id=str(tenant.tenant_id),
        name=tenant.name,
        plan=tenant.plan.value,
        quotas=TenantQuotaResponse(
            plan=tenant.plan,
            **tenant.quotas.model_dump(exclude={"plan"}),
        ) if tenant.quotas else None,
    )


@router.get("/me", response_model=TenantInfoResponse)
async def legacy_me(tenant: Tenant = Depends(get_tenant_only)) -> TenantInfoResponse:
    """Legacy endpoint — equivalent to /api/v1/auth/me but returns Tenant-only shape."""
    return _build_response(tenant)


@router.get("/tenants/me", response_model=TenantInfoResponse)
async def tenant_me(tenant: Tenant = Depends(get_tenant_only)) -> TenantInfoResponse:
    return _build_response(tenant)
