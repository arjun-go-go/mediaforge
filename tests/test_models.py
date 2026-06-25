import pytest

from mediaforge.models.job import BatchSubmitPayload, SkuInput
from mediaforge.models.tenant import TenantPlan, TenantQuota


def test_sku_input_minimal():
    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Dress",
        category="apparel",
        target_platforms=["amazon"],
        output_types=["main_image"],
        market="US",
    )
    assert sku.sku_id == "SKU-001"
    assert sku.style_hint is None


def test_batch_payload_validation():
    payload = BatchSubmitPayload(
        skus=[
            SkuInput(
                sku_id="SKU-001",
                product_image_url="https://example.com/img.jpg",
                product_name="Dress",
                category="apparel",
                target_platforms=["amazon"],
                output_types=["main_image"],
                market="US",
            )
        ],
        image_model="pro",
        video_model="veo",
    )
    assert payload.total_skus == 1


def test_invalid_output_type_rejected():
    with pytest.raises(ValueError):
        SkuInput(
            sku_id="SKU-001",
            product_image_url="https://example.com/img.jpg",
            product_name="Dress",
            category="apparel",
            target_platforms=["amazon"],
            output_types=["invalid_type"],
            market="US",
        )


def test_tenant_quota_defaults():
    quota = TenantQuota(plan=TenantPlan.starter)
    assert quota.max_concurrent_jobs == 2
    assert quota.max_skus_per_job == 50
