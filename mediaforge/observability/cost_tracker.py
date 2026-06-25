from dataclasses import dataclass
from typing import Any

from mediaforge.config import get_settings


@dataclass
class TokenUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int


class CostTracker:
    MODEL_RATES = {
        "google/gemini-3-pro-image": {"per_image": 0.04},
        "openai/gpt-5.4-image-2": {"per_image": 0.03},
        "google/veo-3.1": {"per_video": 0.35},
        "bytedance/seedance-2.0": {"per_video": 0.25},
    }

    def __init__(self):
        settings = get_settings()
        self.project = settings.langsmith_project
        self.client = None
        if settings.langsmith_api_key:
            try:
                from langsmith import Client
                self.client = Client(
                    api_key=settings.langsmith_api_key,
                    api_url=settings.langsmith_endpoint,
                )
            except Exception:
                pass

    def estimate_cost(self, usage: TokenUsage | dict) -> float:
        if isinstance(usage, TokenUsage):
            rates = self.MODEL_RATES.get(usage.model, {})
            return rates.get("per_image", rates.get("per_video", 0.0))
        model = usage.get("model", "")
        count = usage.get("count", 1)
        rates = self.MODEL_RATES.get(model, {})
        unit_cost = rates.get("per_image", rates.get("per_video", 0.0))
        return unit_cost * count

    async def record(self, tenant_id: str, job_id: str, usages: list[Any]):
        total = sum(self.estimate_cost(u) for u in usages)
        if self.client is None:
            return
        try:
            self.client.create_run(
                name="batch_cost",
                run_type="chain",
                project_name=self.project,
                inputs={"tenant_id": tenant_id, "job_id": job_id},
                outputs={"estimated_cost_usd": total},
            )
        except Exception:
            pass
