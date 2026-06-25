import pytest

from mediaforge.rag.models import RagItem
from mediaforge.rag.vector_store import ChromaVectorStore


@pytest.mark.asyncio
async def test_chroma_upsert_and_search(tmp_path):
    store = ChromaVectorStore(persist_dir=str(tmp_path / "chroma"))
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
    results = await store.hybrid_search(
        image_path=None,
        text="elegant silk dress",
        category="apparel",
        top_k=3,
    )
    assert len(results) == 1
    assert results[0].product_id == "P001"
