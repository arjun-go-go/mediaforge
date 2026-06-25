from mediaforge.rag.embeddings import DashScopeEmbeddingClient


def test_model_names_configured():
    client = DashScopeEmbeddingClient(api_key="test")
    assert client.image_model == "tongyi-embedding-vision-flash-2026-03-06"
    assert client.text_model == "text-embedding-v4"
    assert client.rerank_model == "qwen3-vl-rerank"
