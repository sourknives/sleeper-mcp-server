import pytest
from unittest.mock import AsyncMock
from sleeper_mcp_server.sleeper_client import SleeperClient


@pytest.mark.asyncio
async def test_get_player_stats_hits_sleeper_com_with_season():
    client = SleeperClient()
    client._make_request = AsyncMock(return_value={"stats": {"pts_ppr": 300.0}})

    result = await client.get_player_stats("4046", "2025")
    await client.close()

    args, kwargs = client._make_request.await_args
    assert args[0] == "GET"
    assert args[1] == "/stats/nfl/player/4046"
    assert kwargs["params"]["season"] == "2025"
    assert kwargs["params"]["season_type"] == "regular"
    assert kwargs["base_url"] == "https://api.sleeper.com"
    assert result["stats"]["pts_ppr"] == 300.0
