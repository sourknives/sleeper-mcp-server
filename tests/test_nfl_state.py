import pytest
from unittest.mock import AsyncMock
from sleeper_mcp_server.sleeper_client import SleeperClient
from sleeper_mcp_server.models import NflState


@pytest.mark.asyncio
async def test_get_nfl_state_parses_state_payload():
    client = SleeperClient()
    client._make_request = AsyncMock(return_value={
        "week": 0, "leg": 0, "season": "2026", "season_type": "off",
        "previous_season": "2025", "display_week": 1,
    })
    state = await client.get_nfl_state()
    await client.close()

    assert isinstance(state, NflState)
    assert state.season == "2026"
    assert state.season_type == "off"
    assert state.previous_season == "2025"
    assert state.display_week == 1
    client._make_request.assert_awaited_once_with("GET", "/state/nfl")
