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


@mcp.tool(title="User Leagues", annotations=READ_ONLY)
async def get_user_leagues(username: str, ctx: Context, season: Optional[str] = None) -> dict[str, Any]:
    """Get all NFL leagues for a Sleeper username. Defaults to the current season."""
    app = _ctx(ctx)
    season = season or await _default_season(app)
    return await app.league.get_user_leagues(username=username, season=season)


@mcp.tool(title="League Info", annotations=READ_ONLY)
async def get_league_info(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get detailed information about a specific league."""
    return await _ctx(ctx).league.get_league_info(league_id=league_id)


@mcp.tool(title="League Rosters", annotations=READ_ONLY)
async def get_league_rosters(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get all team rosters in a league."""
    return await _ctx(ctx).league.get_league_rosters(league_id=league_id)


@mcp.tool(title="League Rosters with Draft Info", annotations=READ_ONLY)
async def get_league_rosters_with_draft_info(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get all rosters with draft-position metadata per player."""
    return await _ctx(ctx).league.get_league_rosters_with_draft_info(league_id=league_id)


@mcp.tool(title="League Users", annotations=READ_ONLY)
async def get_league_users(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get all users/participants in a league."""
    return await _ctx(ctx).league.get_league_users(league_id=league_id)


@mcp.tool(title="Roster-User Mapping", annotations=READ_ONLY)
async def get_roster_user_mapping(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get a mapping of roster IDs to user names for a league."""
    return await _ctx(ctx).league.get_roster_user_mapping(league_id=league_id)


@mcp.tool(title="League Draft", annotations=READ_ONLY)
async def get_league_draft(league_id: str, ctx: Context) -> dict[str, Any]:
    """Get draft results and pick information for a league."""
    return await _ctx(ctx).league.get_league_draft(league_id=league_id)


@mcp.tool(title="Search Players", annotations=READ_ONLY)
async def search_players(
    query: str, ctx: Context,
    position: Optional[Literal["QB", "RB", "WR", "TE", "K", "DEF"]] = None,
) -> dict[str, Any]:
    """Search for players by name, with optional position filter."""
    return await _ctx(ctx).player.search_players(query=query, position=position)


@mcp.tool(title="Trending Players", annotations=READ_ONLY)
async def get_trending_players(
    ctx: Context,
    add_drop: Literal["add", "drop"] = "add",
    sport: str = "nfl",
) -> dict[str, Any]:
    """Get trending players (most added or dropped)."""
    return await _ctx(ctx).player.get_trending_players(sport=sport, add_drop=add_drop)


@mcp.tool(title="Player Stats", annotations=READ_ONLY)
async def get_player_stats(
    player_id: str, ctx: Context,
    season: Optional[str] = None, week: Optional[int] = None,
) -> dict[str, Any]:
    """Get a player's stats for a season (optionally one week)."""
    app = _ctx(ctx)
    season = season or await _default_season(app)
    return await app.player.get_player_stats(player_id=player_id, season=season, week=week)


@mcp.tool(title="Matchups", annotations=READ_ONLY)
async def get_matchups(league_id: str, week: int, ctx: Context) -> dict[str, Any]:
    """Get matchups for a specific week in a league."""
    return await _ctx(ctx).matchup.get_matchups(league_id=league_id, week=week)


@mcp.tool(title="Matchup Scores", annotations=READ_ONLY)
async def get_matchup_scores(league_id: str, week: int, ctx: Context) -> dict[str, Any]:
    """Get real-time scoring for matchups in a specific week."""
    return await _ctx(ctx).matchup.get_matchup_scores(league_id=league_id, week=week)
