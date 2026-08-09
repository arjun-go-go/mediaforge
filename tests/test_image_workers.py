import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from mediaforge.models.job import AssetOutput, GenerationContext, SkuInput
from mediaforge.workers.image.main_image import MainImageWorker
from mediaforge.workers.image.pinduoduo_white_background import (
    PinduoduoWhiteBackgroundWorker,
)
from mediaforge.workers.platform_rules import aspect_ratio_for, generation_instruction


@pytest.mark.asyncio
async def test_main_image_worker_generates_per_platform(monkeypatch):
    mock_client = AsyncMock()
    mock_client.generate_image.return_value = b"\x89PNG"
    mock_client.model_name = MagicMock(return_value="google/gemini-3-pro-image")
    mock_storage = MagicMock()
    mock_storage.save_asset = AsyncMock(
        return_value="http://localhost:9000/mediaforge/assets/t-1/j-1/a.png"
    )
    monkeypatch.setattr(
        "mediaforge.workers.image.base.get_storage", lambda: mock_storage
    )

    worker = MainImageWorker(
        client=mock_client,
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
    async def generate_for_platform(**kwargs):
        return AssetOutput(
            sku_id=kwargs["sku"].sku_id,
            output_type="main_image",
            model_used="google/gemini-3-pro-image",
            platform=kwargs["platform"],
            status="success",
            file_path=f"https://example.com/{kwargs['platform']}.png",
        )

    monkeypatch.setattr(worker, "_generate_and_save", generate_for_platform)
    context = GenerationContext(
        product_image_path=sku.product_image_url,
        input_matches=True,
        retrieval_mode="none",
    )
    result = await worker.run(
        sku, tenant_id="t-1", job_id="j-1", generation_context=context
    )
    assert len(result.success) == 2
    assert result.success[0].platform == "amazon"
    assert result.success[1].platform == "shopee"


@pytest.mark.asyncio
async def test_pinduoduo_white_background_worker_generates_one_dedicated_asset(monkeypatch):
    worker = PinduoduoWhiteBackgroundWorker(client=AsyncMock(), model="fast")
    sku = SkuInput(
        sku_id="SKU-PDD",
        product_image_url="https://example.com/product.png",
        product_name="Cotton Shirt",
        category="apparel",
        target_platforms=["pinduoduo", "shein"],
        output_types=["main_image", "pdd_white_background"],
        presentation_mode="model_wear",
        style_hint="outdoor lifestyle scene",
    )
    captured = {}

    async def generate(**kwargs):
        captured.update(kwargs)
        return AssetOutput(
            sku_id=sku.sku_id,
            output_type="pdd_white_background",
            model_used="openai/gpt-image-2",
            platform="pinduoduo",
            status="success",
            file_path="https://example.com/pdd-white.png",
        )

    monkeypatch.setattr(worker, "_generate_and_save", generate)
    context = GenerationContext(
        product_image_path=sku.product_image_url,
        input_matches=True,
        retrieval_mode="none",
        presentation_mode="model_wear",
    )
    result = await worker.run(sku, "tenant", "job", generation_context=context)

    assert len(result.success) == 1
    assert captured["platform"] == "pinduoduo"
    assert captured["aspect_ratio"] == "1:1"
    assert captured["ref_image_path"] is None
    assert "outdoor lifestyle scene" not in captured["prompt"]
    assert worker._resolve_presentation_mode(sku) == "product_only"


def test_pinduoduo_white_background_export_is_480_square_under_3mb():
    source = io.BytesIO()
    Image.new("RGB", (1536, 1536), (255, 255, 255)).save(source, format="PNG")
    worker = PinduoduoWhiteBackgroundWorker(client=MagicMock(), model="fast")

    exported = worker._prepare_storage_image(source.getvalue())
    checks = worker._storage_image_checks(exported)

    assert checks["passed"] is True
    assert checks["width"] == 480
    assert checks["height"] == 480
    assert checks["bytes"] < 3 * 1024 * 1024


def test_shein_and_temu_platform_rules_are_selected():
    assert aspect_ratio_for("shein", "main_image") == "1:1"
    assert aspect_ratio_for("shein", "detail_page") == "3:4"
    assert aspect_ratio_for("temu", "main_image") == "1:1"
    assert aspect_ratio_for("temu", "detail_page") == "1:1"
    assert "SHEIN" in generation_instruction("shein", "main_image")
    assert "Temu" in generation_instruction("temu", "detail_page")
