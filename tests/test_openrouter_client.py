import pytest

from mediaforge.workers.openrouter_client import IMAGE_MODELS, VIDEO_MODELS, OpenRouterClient


@pytest.mark.asyncio
async def test_model_maps_contain_only_specified_models():
    assert IMAGE_MODELS["pro"] == "google/gemini-3-pro-image"
    assert IMAGE_MODELS["fast"] == "openai/gpt-5.4-image-2"
    assert VIDEO_MODELS["veo"] == "google/veo-3.1"
    assert VIDEO_MODELS["seedance"] == "bytedance/seedance-2.0"


def test_aspect_ratio_parsing():
    client = OpenRouterClient(api_key="test")
    payload = client._image_payload(prompt="p", model="pro", size="2K", aspect_ratio="1:1")
    assert payload["model"] == "google/gemini-3-pro-image"
