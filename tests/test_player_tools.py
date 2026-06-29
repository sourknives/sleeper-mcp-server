import pytest
from unittest.mock import AsyncMock, MagicMock
from sleeper_mcp_server.sleeper_client import SleeperClient
from sleeper_mcp_server.tools.player_tools import PlayerTools
from sleeper_mcp_server.models import Player


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


@pytest.mark.asyncio
async def test_get_player_stats_week_filters_result():
    client = SleeperClient()
    client._make_request = AsyncMock(return_value={"1": {"pts_ppr": 15.0}, "2": {"pts_ppr": 22.0}})

    result = await client.get_player_stats("4046", "2025", week=1)
    await client.close()

    args, kwargs = client._make_request.await_args
    assert kwargs["params"]["grouping"] == "week"
    assert result == {"pts_ppr": 15.0}


def _player(**kw):
    base = dict(player_id="4046", full_name="Josh Allen", position="QB", team="BUF")
    base.update(kw)
    return Player.model_validate(base)


@pytest.mark.asyncio
async def test_player_tools_get_player_stats_shapes_result():
    client = MagicMock()
    client.get_player_stats = AsyncMock(return_value={"stats": {"pts_ppr": 300.0}})
    client.get_players = AsyncMock(return_value={"4046": _player()})
    cache = MagicMock()
    cache.get.return_value = None

    tools = PlayerTools(client, cache)
    result = await tools.get_player_stats("4046", season="2025")

    assert result["player_name"] == "Josh Allen"
    assert result["position"] == "QB"
    assert result["season"] == "2025"
    assert result["stats"] == {"pts_ppr": 300.0}
    assert result["week"] is None
    assert result["player_id"] == "4046"
    assert result["team"] == "BUF"


@pytest.mark.asyncio
async def test_get_players_caches_within_day():
    client = SleeperClient()
    client._make_request = AsyncMock(return_value={"4046": {
        "player_id": "4046", "full_name": "Josh Allen", "position": "QB", "team": "BUF"}})

    first = await client.get_players("nfl")
    second = await client.get_players("nfl")
    await client.close()

    assert "4046" in first and "4046" in second
    client._make_request.assert_awaited_once()  # only one network fetch
