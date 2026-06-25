from pathlib import Path

import pytest

from mediaforge.storage import OutputStorage


@pytest.mark.asyncio
async def test_save_and_path(tmp_path):
    storage = OutputStorage(str(tmp_path))
    data = b"fake-image-bytes"
    path = await storage.save_asset("t-1", "job-1", "asset-1", data, ext="png")
    assert Path(path).exists()
    assert path.endswith("asset-1.png")
