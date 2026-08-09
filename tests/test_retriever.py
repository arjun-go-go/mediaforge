import pytest

from mediaforge.rag.models import RagResult
from mediaforge.rag.retriever import ReferenceRetriever


class StubRetriever:
    async def retrieve(self, **kwargs):
        if kwargs.get("category") == "apparel":
            return [
                RagResult(
                    product_id="P001",
                    score=0.9,
                    image_url="https://minio.example/mediaforge/P001.jpg",
                    metadata={"category": "apparel"},
                )
            ]
        return []


@pytest.mark.asyncio
async def test_retriever_finds_references():
    retriever = ReferenceRetriever(StubRetriever())
    refs = await retriever.retrieve(
        image_path=None,
        text="elegant silk dress",
        category="apparel",
        top_k=3,
    )
    assert len(refs) == 1
    assert refs[0].product_id == "P001"
