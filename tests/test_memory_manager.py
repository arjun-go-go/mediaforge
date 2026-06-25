import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config; mediaforge.config.clear_settings_cache()

import pytest
from mediaforge.orchestrator.memory import MemoryManager


@pytest.mark.asyncio
async def test_memory_manager_combines_sources(redis_client):
    mm = MemoryManager(redis=redis_client, tenant_id="t-1", thread_id="th-1")
    await mm.add_short_term("user", "I prefer minimalist white backgrounds")
    context = await mm.build_context("Generate a main image")
    assert "minimalist white backgrounds" in context
