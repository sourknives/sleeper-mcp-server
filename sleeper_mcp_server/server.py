"""FastMCP server for the Sleeper Fantasy Football API."""

import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .sleeper_client import SleeperClient
from .cache import CacheManager
from .nfl_state import resolve_default_season
from .tools.league_tools import LeagueTools
from .tools.matchup_tools import MatchupTools
from .tools.player_tools import PlayerTools
from .models import NflState

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


@dataclass
class AppContext:
    client: SleeperClient
    cache: CacheManager
    league: LeagueTools
    player: PlayerTools
    matchup: MatchupTools


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    client = SleeperClient()
    cache = CacheManager()
    try:
        yield AppContext(
            client=client,
            cache=cache,
            league=LeagueTools(client, cache),
            player=PlayerTools(client, cache),
            matchup=MatchupTools(client, cache),
        )
    finally:
        await client.close()


mcp = FastMCP("sleeper-mcp-server", lifespan=lifespan)


def _ctx(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


async def _default_season(app: AppContext) -> str:
    return resolve_default_season(await app.client.get_nfl_state())


@mcp.tool(title="NFL State", annotations=READ_ONLY)
async def get_nfl_state(ctx: Context) -> NflState:
    """Get the current NFL season, week, and season type from Sleeper."""
    return await _ctx(ctx).client.get_nfl_state()
