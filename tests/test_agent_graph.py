import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config

mediaforge.config.clear_settings_cache()

from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from mediaforge.orchestrator.agent_graph import build_supervisor_graph


@pytest.mark.asyncio
async def test_supervisor_graph_compiles():
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_router = MagicMock()
    mock_router.invoke = MagicMock(return_value=MagicMock(next="FINISH"))
    mock_llm.with_structured_output = MagicMock(return_value=mock_router)

    saver = InMemorySaver()

    with patch(
        "mediaforge.orchestrator.agent_graph.AsyncPostgresSaver.from_conn_string",
        return_value=saver,
    ):
        graph = await build_supervisor_graph(llm=mock_llm)

    assert graph is not None
