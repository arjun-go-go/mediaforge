import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config; mediaforge.config.clear_settings_cache()

import pytest
from mediaforge.orchestrator.rag_tool import RAGSearchTool


@pytest.mark.asyncio
async def test_rag_tool_schema():
    tool = RAGSearchTool(vector_store=None)
    assert tool.name == "rag_search"
    assert "query_text" in tool.args_schema.model_fields
