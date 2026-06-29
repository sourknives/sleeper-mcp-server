import pytest
from unittest.mock import AsyncMock

from sleeper_mcp_server.sleeper_client import SleeperClient


@pytest.mark.asyncio
async def test_get_projections_uses_sleeper_com_and_browser_ua():
    client = SleeperClient()
    client._make_request = AsyncMock(
        return_value=[{"player_id": "1", "stats": {"adp_dd_ppr": 3.0}}]
    )
    out = await client.get_projections("2026", week=1)
    await client.close()

    args, kwargs = client._make_request.await_args
    assert args[1] == "/projections/nfl/2026/1"
    assert kwargs["base_url"] == "https://api.sleeper.com"
    assert "Mozilla" in kwargs["headers"]["User-Agent"]
    assert kwargs["params"]["season_type"] == "regular"
    assert out[0]["player_id"] == "1"


def test_package_reexports_client():
    import sleeper_mcp_server as pkg
    assert pkg.SleeperClient is SleeperClient
