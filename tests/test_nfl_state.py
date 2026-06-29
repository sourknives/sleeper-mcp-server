import pytest
from unittest.mock import AsyncMock
from sleeper_mcp_server.sleeper_client import SleeperClient
from sleeper_mcp_server.models import NflState
from sleeper_mcp_server.nfl_state import resolve_default_season


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


@pytest.mark.asyncio
async def test_get_nfl_state_caches_within_ttl():
    client = SleeperClient()
    client._make_request = AsyncMock(return_value={
        "week": 0, "season": "2026", "season_type": "off",
        "previous_season": "2025", "display_week": 1})
    first = await client.get_nfl_state()
    second = await client.get_nfl_state()
    await client.close()
    assert first.season == "2026" and second.season == "2026"
    client._make_request.assert_awaited_once()


def _state(**kw):
    base = {"season": "2026", "season_type": "regular", "week": 3,
            "display_week": 3, "previous_season": "2025"}
    base.update(kw)
    return NflState.model_validate(base)


def test_resolver_uses_current_season_in_season():
    assert resolve_default_season(_state(season_type="regular")) == "2026"


def test_resolver_falls_back_to_previous_in_offseason():
    assert resolve_default_season(_state(season_type="off")) == "2025"


def test_resolver_uses_current_when_no_previous():
    assert resolve_default_season(_state(season_type="off", previous_season=None)) == "2026"
