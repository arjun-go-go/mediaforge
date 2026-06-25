from fastapi import APIRouter

from mediaforge.workers.openrouter_client import get_image_models, get_video_models

router = APIRouter(prefix="/api/v1/models")


@router.get("")
async def list_models():
    """Return available image and video model aliases with display labels."""
    image_models = [
        {"alias": alias, "model_id": model_id, "label": model_id}
        for alias, model_id in get_image_models().items()
    ]
    video_models = [
        {"alias": alias, "model_id": model_id, "label": model_id}
        for alias, model_id in get_video_models().items()
    ]
    return {"image_models": image_models, "video_models": video_models}
