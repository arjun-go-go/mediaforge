"""Connectivity smoke test for Milvus / Zilliz Cloud vector store."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("JWT_SECRET", "test-script")

import mediaforge.config
mediaforge.config.clear_settings_cache()

from mediaforge.config import get_settings
from mediaforge.rag.factory import get_vector_store


async def main() -> int:
    settings = get_settings()
    print(f"VECTOR_STORE_BACKEND={settings.vector_store_backend}")
    print(f"MILVUS_URI={settings.milvus_uri}")
    print(f"MILVUS_DB_NAME={settings.milvus_db_name}")
    print(f"MILVUS_COLLECTION={settings.milvus_collection}")
    print(f"TEXT_DIM={settings.dashscope_text_dim}")
    print(f"IMAGE_DIM={settings.dashscope_image_dim}")

    try:
        store = get_vector_store()
        health = await store.health()
        print(f"HEALTH={health}")
        print("Milvus connection OK")
        return 0
    except Exception as exc:
        print(f"Milvus connection FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
