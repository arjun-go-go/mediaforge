from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class TenantPlan(StrEnum):
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class TenantQuota(BaseModel):
    plan: TenantPlan
    max_concurrent_jobs: int = Field(default=2)
    max_skus_per_job: int = Field(default=50)
    image_credits_monthly: int = Field(default=100)
    video_credits_monthly: int = Field(default=10)
    allowed_models: list[str] = Field(default_factory=lambda: ["fast"])

    def model_post_init(self, __context):
        defaults = {
            TenantPlan.starter: (2, 50, 100, 10, ["fast", "seedance"]),
            TenantPlan.pro: (5, 500, 1000, 100, ["pro", "fast", "veo", "seedance"]),
            TenantPlan.enterprise: (20, 5000, 10000, 1000, ["pro", "fast", "veo", "seedance"]),
        }
        m_jobs, m_skus, img_credits, vid_credits, models = defaults[self.plan]
        self.max_concurrent_jobs = m_jobs
        self.max_skus_per_job = m_skus
        self.image_credits_monthly = img_credits
        self.video_credits_monthly = vid_credits
        self.allowed_models = models


class Tenant(BaseModel):
    tenant_id: UUID
    name: str
    api_key_hash: str = Field(default="", exclude=True)
    plan: TenantPlan
    quotas: TenantQuota | None = None

    def model_post_init(self, __context):
        if self.quotas is None:
            self.quotas = TenantQuota(plan=self.plan)
