import pytest
from pydantic import ValidationError

from mediaforge.models.job import SkuInput


def test_public_batch_payload_rejects_video_output():
    with pytest.raises(ValidationError, match="Invalid output_type: video"):
        SkuInput(
            sku_id="SKU-001",
            product_image_url="https://example.com/img.jpg",
            product_name="Silk Dress",
            category="apparel",
            target_platforms=["amazon"],
            output_types=["video"],
            market="US",
        )
