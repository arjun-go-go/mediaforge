import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config; mediaforge.config.clear_settings_cache()

import pytest
from pydantic import ValidationError

from mediaforge.orchestrator.agent_tools import SubmitGenerationInput


@pytest.mark.asyncio
async def test_submit_generation_input_contract():
    data = SubmitGenerationInput(
        sku_id="SKU001",
        product_image_url="https://example.com/product.png",
        product_name="Dress",
        category="fashion",
        target_platforms=["SHEIN"],
        output_types=["main_image"],
    )
    assert data.target_platforms == ["shein"]

    with pytest.raises(ValidationError):
        SubmitGenerationInput(
            sku_id="SKU001",
            product_image_url="https://example.com/product.png",
            product_name="Dress",
            category="fashion",
            target_platforms=["amazon"],
            output_types=["pdd_white_background"],
        )
