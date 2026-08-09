from types import SimpleNamespace

from mediaforge.rag import factory
from mediaforge.rag.milvus_store import MilvusVectorStore


def test_factory_uses_milvus_as_the_only_backend(monkeypatch):
    settings = SimpleNamespace(
        milvus_uri="http://milvus:19530",
        milvus_token="",
        milvus_db_name="default",
        milvus_collection="mediaforge",
        dashscope_text_dim=1024,
        dashscope_image_dim=2560,
    )
    monkeypatch.setattr(factory, "get_settings", lambda: settings)
    monkeypatch.setattr(factory, "_store", None)

    store = factory.get_vector_store()

    assert isinstance(store, MilvusVectorStore)
    assert store.uri == "http://milvus:19530"
    assert store.text_dim == 1024
    assert store.image_dim == 2560
