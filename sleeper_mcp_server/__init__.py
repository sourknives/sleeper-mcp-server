"""Sleeper MCP Server - A Model Context Protocol server for Sleeper Fantasy Football API.

Also usable as a library: `from sleeper_mcp_server import SleeperClient`.
"""

from .sleeper_client import SleeperClient, SleeperAPIError, RateLimitError
from .models import (
    NflState,
    League,
    Roster,
    Matchup,
    Player,
    PlayerStats,
    User,
)

__version__ = "0.1.0"
__author__ = "Sleeper MCP Server"
__description__ = "MCP server providing access to Sleeper Fantasy Football API"

__all__ = [
    "SleeperClient",
    "SleeperAPIError",
    "RateLimitError",
    "NflState",
    "League",
    "Roster",
    "Matchup",
    "Player",
    "PlayerStats",
    "User",
]