import pytest

from mediaforge.config import get_settings
from mediaforge.workers.openrouter_client import (
    OpenRouterClient,
    get_image_models,
    get_video_models,
)


@pytest.mark.asyncio
async def test_model_maps_contain_only_specified_models():
    settings = get_settings()
    assert get_image_models()["pro"] == settings.image_model_pro
    assert get_image_models()["fast"] == settings.image_model_fast
    assert get_video_models()["veo"] == settings.video_model_veo
    assert get_video_models()["seedance"] == settings.video_model_seedance


@pytest.mark.asyncio
async def test_aspect_ratio_parsing():
    client = OpenRouterClient(api_key="test")
    payload = await client._image_payload(
        prompt="p", model="pro", size="2K", aspect_ratio="1:1"
    )
    assert payload["model"] == get_settings().image_model_pro
    assert payload["aspect_ratio"] == "1:1"
    assert payload["resolution"] == "2K"
    assert "modalities" not in payload
    assert "messages" not in payload


def test_extract_dedicated_image_api_response():
    assert OpenRouterClient._extract_image_bytes(
        {"data": [{"b64_json": "aW1hZ2U="}]}
    ) == b"image"
