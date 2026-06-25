import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config; mediaforge.config.clear_settings_cache()

import pytest
from unittest.mock import MagicMock, patch
from mediaforge.rag.milvus_store import MilvusVectorStore
from mediaforge.rag.models import RagItem


@pytest.mark.asyncio
async def test_milvus_upsert_and_search():
    with patch("mediaforge.rag.milvus_store.MilvusClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.search.return_value = [[{"entity": {"product_id": "P001", "image_url": "https://example.com/p001.jpg"}, "distance": 0.9}]]

        store = MilvusVectorStore(uri="http://localhost:19530", collection="mediaforge")
        await store.upsert([
            RagItem(
                product_id="P001",
                category="apparel",
                style="elegant",
                color="red",
                material="silk",
                image_url="https://example.com/p001.jpg",
                text_embedding=[0.1] * 1024,
            )
        ])
        results = await store.hybrid_search(None, "elegant silk dress", "apparel", top_k=3)
        assert len(results) == 1
        assert results[0].product_id == "P001"
