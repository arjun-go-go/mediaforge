from unittest.mock import AsyncMock, MagicMock

import pytest

from mediaforge.models.job import SkuInput
from mediaforge.workers.image.main_image import MainImageWorker


@pytest.mark.asyncio
async def test_main_image_worker_generates_per_platform(tmp_path):
    mock_client = AsyncMock()
    mock_client.generate_image.return_value = b"\x89PNG"
    mock_client.model_name = MagicMock(return_value="google/gemini-3-pro-image")

    worker = MainImageWorker(
        client=mock_client,
        storage_dir=str(tmp_path),
        model="pro",
    )
    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Silk Dress",
        category="apparel",
        target_platforms=["amazon", "shopee"],
        output_types=["main_image"],
        market="US",
    )
    result = await worker.run(sku, tenant_id="t-1", job_id="j-1")
    assert len(result.success) == 2
    assert result.success[0].platform == "amazon"
    assert result.success[1].platform == "shopee"
