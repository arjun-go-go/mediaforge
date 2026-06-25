from mediaforge.config import get_settings
from mediaforge.rag.vector_store import ChromaVectorStore, VectorStore

_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.vector_store_backend == "milvus":
        from mediaforge.rag.milvus_store import MilvusVectorStore
        _store = MilvusVectorStore(
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            db_name=settings.milvus_db_name,
            collection=settings.milvus_collection,
            text_dim=settings.dashscope_text_dim,
            image_dim=settings.dashscope_image_dim,
        )
    else:
        _store = ChromaVectorStore(persist_dir=settings.chroma_persist_dir)
    return _store
