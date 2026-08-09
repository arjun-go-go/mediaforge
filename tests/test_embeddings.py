from mediaforge.config import get_settings
from mediaforge.rag.embeddings import DashScopeEmbeddingClient


def test_model_names_configured():
    client = DashScopeEmbeddingClient(api_key="test")
    settings = get_settings()
    assert client.image_model == settings.dashscope_image_model
    assert client.text_model == settings.dashscope_text_model
    assert client.rerank_model == settings.dashscope_rerank_model
