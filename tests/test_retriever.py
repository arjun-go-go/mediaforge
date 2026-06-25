import pytest

from mediaforge.rag.models import RagItem
from mediaforge.rag.retriever import ReferenceRetriever
from mediaforge.rag.vector_store import ChromaVectorStore


@pytest.mark.asyncio
async def test_retriever_finds_references(tmp_path):
    store = ChromaVectorStore(persist_dir=str(tmp_path / "chroma"))
    await store.upsert(
        [
            RagItem(
                product_id="P001",
                category="apparel",
                style="elegant",
                color="red",
                material="silk",
                image_url="https://example.com/p001.jpg",
                text_embedding=[0.1] * 1024,
            )
        ]
    )
    retriever = ReferenceRetriever(vector_store=store)
    refs = await retriever.retrieve(
        image_path=None,
        text="elegant silk dress",
        category="apparel",
        top_k=3,
    )
    assert len(refs) == 1
    assert refs[0].product_id == "P001"
