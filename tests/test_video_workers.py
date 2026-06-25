from unittest.mock import AsyncMock, MagicMock

import pytest

from mediaforge.models.job import SkuInput
from mediaforge.workers.video.veo import VeoWorker


@pytest.mark.asyncio
async def test_veo_worker_generates_video(tmp_path):
    mock_client = AsyncMock()
    mock_client.generate_video.return_value = "https://cdn.example.com/video.mp4"
    mock_client.model_name = MagicMock(return_value="google/veo-3.1")

    worker = VeoWorker(
        client=mock_client,
        storage_dir=str(tmp_path),
        model="veo",
    )
    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Silk Dress",
        category="apparel",
        target_platforms=["tiktok"],
        output_types=["video"],
        market="US",
    )
    result = await worker.run(sku, tenant_id="t-1", job_id="j-1")
    assert len(result.success) == 1
    assert result.success[0].output_type == "video"
    assert "lock exposure" in mock_client.generate_video.call_args.kwargs["prompt"]
