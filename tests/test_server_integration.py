import pytest
from unittest.mock import AsyncMock
from mcp.shared.memory import create_connected_server_and_client_session

import sleeper_mcp_server.server as srv
from sleeper_mcp_server.models import NflState


@pytest.mark.asyncio
async def test_get_nfl_state_tool_roundtrip(monkeypatch):
    async def fake_state(self, sport="nfl"):
        return NflState(season="2026", season_type="off", week=0,
                        display_week=1, previous_season="2025")
    monkeypatch.setattr("sleeper_mcp_server.sleeper_client.SleeperClient.get_nfl_state", fake_state)

    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert "get_nfl_state" in names

        res = await client.call_tool("get_nfl_state", {})
        assert res.structuredContent["season"] == "2026"
        assert res.structuredContent["season_type"] == "off"
