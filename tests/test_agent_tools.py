import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config; mediaforge.config.clear_settings_cache()

import pytest
from mediaforge.orchestrator.agent_tools import GenerateImageTool


@pytest.mark.asyncio
async def test_generate_image_tool_schema():
    tool = GenerateImageTool()
    assert tool.name == "generate_image"
    assert "prompt" in tool.args_schema.model_fields
