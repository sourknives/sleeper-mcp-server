"""
MCP server implementation for Sleeper Fantasy Football API.

This module implements the main MCP server class that handles tool registration,
execution, and communication with Claude Desktop through the MCP protocol.
"""

import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional, Sequence

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
    EmbeddedResource,
)

from .sleeper_client import SleeperClient
from .cache import CacheManager
from .tools.league_tools import LeagueTools
from .tools.matchup_tools import MatchupTools
from .tools.trade_tools import TradeTools
from .tools.player_tools import PlayerTools

logger = logging.getLogger(__name__)


class SleeperMCPServer:
    """Main MCP server class for Sleeper Fantasy Football API integration."""
    
    def __init__(self):
        """Initialize the Sleeper MCP server."""
        self.server = Server("sleeper-mcp-server")
        self.client: Optional[SleeperClient] = None
        self.cache: Optional[CacheManager] = None
        self.league_tools: Optional[LeagueTools] = None
        self.matchup_tools: Optional[MatchupTools] = None
        self.trade_tools: Optional[TradeTools] = None
        self.player_tools: Optional[PlayerTools] = None
        
        # Register MCP handlers
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register MCP protocol handlers."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """Handle list_tools request from Claude Desktop."""
            return await self._list_tools()
        
        @self.server.call_tool()
        async def handle_call_tool(
            name: str, 
            arguments: Optional[Dict[str, Any]] = None
        ) -> List[TextContent | EmbeddedResource]:
            """Handle call_tool request from Claude Desktop."""
            return await self._call_tool(name, arguments or {})
    
    async def initialize(self) -> None:
        """Initialize server components."""
        try:
            # Initialize Sleeper API client
            self.client = SleeperClient()
            
            # Initialize cache manager
            self.cache = CacheManager()
            
            # Initialize tool handlers
            self.league_tools = LeagueTools(self.client, self.cache)
            self.matchup_tools = MatchupTools(self.client, self.cache)
            self.trade_tools = TradeTools(self.client, self.cache)
            self.player_tools = PlayerTools(self.client, self.cache)
            
            logger.info("Sleeper MCP Server initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Sleeper MCP Server: {e}")
            raise
    
    async def _list_tools(self) -> List[Tool]:
        """
        List all available MCP tools.
        
        Returns:
            List of Tool objects describing available functionality
        """
        tools = [
            # League Tools
            Tool(
                name="get_user_leagues",
                description="Get all leagues for a username in a specific season",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Sleeper username to look up"
                        },
                        "season": {
                            "type": "string",
                            "description": "Season year (default: '2024')",
                            "default": "2024"
                        }
                    },
                    "required": ["username"]
                }
            ),
            Tool(
                name="get_league_info",
                description="Get detailed information about a specific league",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to retrieve information for"
                        }
                    },
                    "required": ["league_id"]
                }
            ),
            Tool(
                name="get_league_rosters",
                description="Get all team rosters in a league",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to retrieve rosters for"
                        }
                    },
                    "required": ["league_id"]
                }
            ),
            Tool(
                name="get_league_rosters_with_draft_info",
                description="Get all team rosters in a league with draft position metadata for each player",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to retrieve rosters for"
                        }
                    },
                    "required": ["league_id"]
                }
            ),
            Tool(
                name="get_league_users",
                description="Get all users/participants in a league",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to retrieve users for"
                        }
                    },
                    "required": ["league_id"]
                }
            ),
            Tool(
                name="get_roster_user_mapping",
                description="Get a clear mapping of roster IDs to user names for a league",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to get roster-user mapping for"
                        }
                    },
                    "required": ["league_id"]
                }
            ),
            Tool(
                name="get_league_draft",
                description="Get draft results and pick information for a league",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to get draft information for"
                        }
                    },
                    "required": ["league_id"]
                }
            ),
            
            # Player Tools
            Tool(
                name="search_players",
                description="Search for players by name with optional position filtering",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Player name or partial name to search for"
                        },
                        "position": {
                            "type": "string",
                            "description": "Optional position filter (QB, RB, WR, TE, K, DEF)",
                            "enum": ["QB", "RB", "WR", "TE", "K", "DEF"]
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="get_trending_players",
                description="Get trending players (most added/dropped)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "sport": {
                            "type": "string",
                            "description": "Sport type (default: 'nfl')",
                            "default": "nfl"
                        },
                        "add_drop": {
                            "type": "string",
                            "description": "Type of trend - 'add' or 'drop' (default: 'add')",
                            "enum": ["add", "drop"],
                            "default": "add"
                        }
                    }
                }
            ),
            Tool(
                name="get_player_stats",
                description="Get player statistics for a specific season",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "player_id": {
                            "type": "string",
                            "description": "Player ID to get stats for"
                        },
                        "season": {
                            "type": "string",
                            "description": "Season year (default: '2024')",
                            "default": "2024"
                        }
                    },
                    "required": ["player_id"]
                }
            ),
            
            # Matchup Tools
            Tool(
                name="get_matchups",
                description="Get matchups for a specific week in a league",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to retrieve matchups for"
                        },
                        "week": {
                            "type": "integer",
                            "description": "Week number (1-22)",
                            "minimum": 1,
                            "maximum": 22
                        }
                    },
                    "required": ["league_id", "week"]
                }
            ),
            Tool(
                name="get_matchup_scores",
                description="Get real-time scoring information for matchups in a specific week",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to retrieve scores for"
                        },
                        "week": {
                            "type": "integer",
                            "description": "Week number (1-22)",
                            "minimum": 1,
                            "maximum": 22
                        }
                    },
                    "required": ["league_id", "week"]
                }
            ),
            
            # Trade Tools
            Tool(
                name="analyze_trade_targets",
                description="Analyze potential trade targets for a roster based on positional needs",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to analyze"
                        },
                        "roster_id": {
                            "type": "integer",
                            "description": "Roster ID requesting trade analysis"
                        },
                        "position": {
                            "type": "string",
                            "description": "Optional position to focus analysis on (QB, RB, WR, TE, K, DEF)",
                            "enum": ["QB", "RB", "WR", "TE", "K", "DEF"]
                        }
                    },
                    "required": ["league_id", "roster_id"]
                }
            ),
            Tool(
                name="evaluate_roster_needs",
                description="Evaluate roster strengths and weaknesses across all positions",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "league_id": {
                            "type": "string",
                            "description": "League ID to analyze"
                        },
                        "roster_id": {
                            "type": "integer",
                            "description": "Roster ID to evaluate"
                        }
                    },
                    "required": ["league_id", "roster_id"]
                }
            )
        ]
        
        return tools
    
    async def _call_tool(
        self, 
        name: str, 
        arguments: Dict[str, Any]
    ) -> List[TextContent | EmbeddedResource]:
        """
        Execute a tool call and return formatted results.
        
        Args:
            name: Name of the tool to execute
            arguments: Tool arguments
            
        Returns:
            List of content objects for Claude Desktop
        """
        try:
            # Ensure server is initialized
            if not self.client or not self.cache:
                await self.initialize()
            
            # Route tool calls to appropriate handlers
            result = await self._route_tool_call(name, arguments)
            
            # Format response for Claude Desktop
            return await self._format_response(name, result)
            
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}")
            error_result = {
                "error": f"Tool execution failed: {str(e)}",
                "suggestions": [
                    "Check your input parameters",
                    "Try again in a few moments",
                    "Verify the Sleeper API is accessible"
                ]
            }
            return await self._format_response(name, error_result)
    
    async def _route_tool_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route tool calls to the appropriate tool handler.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        # League Tools
        if name == "get_user_leagues":
            return await self.league_tools.get_user_leagues(
                username=arguments["username"],
                season=arguments.get("season", "2024")
            )
        elif name == "get_league_info":
            return await self.league_tools.get_league_info(
                league_id=arguments["league_id"]
            )
        elif name == "get_league_rosters":
            return await self.league_tools.get_league_rosters(
                league_id=arguments["league_id"]
            )
        elif name == "get_league_rosters_with_draft_info":
            return await self.league_tools.get_league_rosters_with_draft_info(
                league_id=arguments["league_id"]
            )
        elif name == "get_league_users":
            return await self.league_tools.get_league_users(
                league_id=arguments["league_id"]
            )
        elif name == "get_roster_user_mapping":
            return await self.league_tools.get_roster_user_mapping(
                league_id=arguments["league_id"]
            )
        elif name == "get_league_draft":
            return await self.league_tools.get_league_draft(
                league_id=arguments["league_id"]
            )
        
        # Player Tools
        elif name == "search_players":
            return await self.player_tools.search_players(
                query=arguments["query"],
                position=arguments.get("position")
            )
        elif name == "get_trending_players":
            return await self.player_tools.get_trending_players(
                sport=arguments.get("sport", "nfl"),
                add_drop=arguments.get("add_drop", "add")
            )
        elif name == "get_player_stats":
            return await self.player_tools.get_player_stats(
                player_id=arguments["player_id"],
                season=arguments.get("season", "2024")
            )
        
        # Matchup Tools
        elif name == "get_matchups":
            return await self.matchup_tools.get_matchups(
                league_id=arguments["league_id"],
                week=arguments["week"]
            )
        elif name == "get_matchup_scores":
            return await self.matchup_tools.get_matchup_scores(
                league_id=arguments["league_id"],
                week=arguments["week"]
            )
        
        # Trade Tools
        elif name == "analyze_trade_targets":
            return await self.trade_tools.analyze_trade_targets(
                league_id=arguments["league_id"],
                roster_id=arguments["roster_id"],
                position=arguments.get("position")
            )
        elif name == "evaluate_roster_needs":
            return await self.trade_tools.evaluate_roster_needs(
                league_id=arguments["league_id"],
                roster_id=arguments["roster_id"]
            )
        
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    async def _format_response(
        self, 
        tool_name: str, 
        result: Dict[str, Any]
    ) -> List[TextContent]:
        """
        Format tool results for Claude Desktop consumption.
        
        Args:
            tool_name: Name of the executed tool
            result: Tool execution result
            
        Returns:
            List of TextContent objects
        """
        try:
            # Check if result contains an error
            if "error" in result:
                return [TextContent(
                    type="text",
                    text=self._format_error_response(tool_name, result)
                )]
            
            # Format successful responses based on tool type
            formatted_text = await self._format_success_response(tool_name, result)
            
            return [TextContent(
                type="text",
                text=formatted_text
            )]
            
        except Exception as e:
            logger.error(f"Error formatting response for {tool_name}: {e}")
            return [TextContent(
                type="text",
                text=f"Error formatting response: {str(e)}"
            )]
    
    def _format_error_response(self, tool_name: str, result: Dict[str, Any]) -> str:
        """
        Format error responses in a user-friendly way.
        
        Args:
            tool_name: Name of the tool that failed
            result: Error result dictionary
            
        Returns:
            Formatted error message
        """
        error_msg = result.get("error", "Unknown error occurred")
        suggestions = result.get("suggestions", [])
        retry_after = result.get("retry_after")
        
        formatted = f"❌ **{tool_name} Error**\n\n{error_msg}"
        
        if suggestions:
            formatted += "\n\n**Suggestions:**\n"
            for suggestion in suggestions:
                formatted += f"• {suggestion}\n"
        
        if retry_after:
            formatted += f"\n⏱️ Please wait {retry_after} seconds before retrying."
        
        return formatted
    
    async def _format_success_response(self, tool_name: str, result: Dict[str, Any]) -> str:
        """
        Format successful responses based on tool type.
        
        Args:
            tool_name: Name of the executed tool
            result: Successful result dictionary
            
        Returns:
            Formatted response text
        """
        if tool_name == "get_user_leagues":
            return self._format_user_leagues_response(result)
        elif tool_name == "get_league_info":
            return self._format_league_info_response(result)
        elif tool_name == "get_league_rosters":
            return self._format_league_rosters_response(result)
        elif tool_name == "get_league_rosters_with_draft_info":
            return self._format_league_rosters_with_draft_response(result)
        elif tool_name == "get_league_users":
            return self._format_league_users_response(result)
        elif tool_name == "get_roster_user_mapping":
            return self._format_roster_user_mapping_response(result)
        elif tool_name == "get_league_draft":
            return self._format_league_draft_response(result)
        elif tool_name == "search_players":
            return self._format_search_players_response(result)
        elif tool_name == "get_trending_players":
            return self._format_trending_players_response(result)
        elif tool_name == "get_player_stats":
            return self._format_player_stats_response(result)
        elif tool_name == "get_matchups":
            return self._format_matchups_response(result)
        elif tool_name == "get_matchup_scores":
            return self._format_matchup_scores_response(result)
        elif tool_name == "analyze_trade_targets":
            return self._format_trade_analysis_response(result)
        elif tool_name == "evaluate_roster_needs":
            return self._format_roster_evaluation_response(result)
        else:
            # Fallback to JSON representation
            import json
            return f"**{tool_name} Result:**\n```json\n{json.dumps(result, indent=2)}\n```"
    
    def _format_user_leagues_response(self, result: Dict[str, Any]) -> str:
        """Format user leagues response."""
        username = result.get("username", "Unknown")
        season = result.get("season", "Unknown")
        leagues = result.get("leagues", [])
        
        formatted = f"🏈 **Leagues for {username} ({season} season)**\n\n"
        
        if not leagues:
            formatted += "No leagues found for this user."
            return formatted
        
        for i, league in enumerate(leagues, 1):
            formatted += f"**{i}. {league['name']}**\n"
            formatted += f"   • League ID: `{league['league_id']}`\n"
            formatted += f"   • Status: {league['status'].replace('_', ' ').title()}\n"
            formatted += f"   • Teams: {league['total_rosters']}\n"
            formatted += f"   • Sport: {league['sport'].upper()}\n\n"
        
        return formatted
    
    def _format_league_info_response(self, result: Dict[str, Any]) -> str:
        """Format league info response."""
        name = result.get("name", "Unknown League")
        league_id = result.get("league_id", "Unknown")
        status = result.get("status", "unknown").replace("_", " ").title()
        season = result.get("season", "Unknown")
        total_rosters = result.get("total_rosters", 0)
        settings = result.get("settings", {})
        
        formatted = f"🏆 **{name}**\n\n"
        formatted += f"**League Details:**\n"
        formatted += f"• ID: `{league_id}`\n"
        formatted += f"• Season: {season}\n"
        formatted += f"• Status: {status}\n"
        formatted += f"• Teams: {total_rosters}\n\n"
        
        if settings:
            formatted += f"**League Settings:**\n"
            formatted += f"• Playoff Teams: {settings.get('playoff_teams', 'N/A')}\n"
            formatted += f"• Waiver Type: {settings.get('waiver_type', 'N/A')}\n"
            formatted += f"• Reserve Slots: {settings.get('reserve_slots', 0)}\n"
            formatted += f"• Taxi Slots: {settings.get('taxi_slots', 0)}\n\n"
        
        roster_positions = result.get("roster_positions", [])
        if roster_positions:
            formatted += f"**Roster Positions:** {', '.join(roster_positions)}\n"
        
        return formatted
    
    def _format_league_rosters_response(self, result: Dict[str, Any]) -> str:
        """Format league rosters response."""
        league_id = result.get("league_id", "Unknown")
        rosters = result.get("rosters", [])
        
        formatted = f"👥 **Rosters for League {league_id}**\n\n"
        
        if not rosters:
            formatted += "No rosters found in this league."
            return formatted
        
        for roster in rosters:
            roster_id = roster.get("roster_id", "Unknown")
            owner_info = roster.get("owner_info", {})
            players = roster.get("players", [])
            starters = roster.get("starters", [])
            
            # Get the best available name for the owner
            display_name = owner_info.get("display_name")
            username = owner_info.get("username")
            is_league_owner = owner_info.get("is_owner", False)
            
            if display_name and display_name != f"User {roster.get('owner_id')}":
                owner_text = display_name
                if username:
                    owner_text += f" (@{username})"
            elif username:
                owner_text = f"@{username}"
            else:
                owner_text = f"User {roster.get('owner_id', 'Unknown')}"
            
            if is_league_owner:
                owner_text += " 👑"
            
            formatted += f"**Roster {roster_id}** - {owner_text}\n"
            
            # Show player counts
            player_count = roster.get("player_count", len(players))
            starter_count = roster.get("starter_count", len(starters))
            formatted += f"• Total Players: {player_count}\n"
            formatted += f"• Starters: {starter_count}\n"
            formatted += f"• Bench: {player_count - starter_count}\n"
            
            # Show starting lineup with player names
            if starters and len(starters) > 0:
                formatted += f"\n**Starting Lineup:**\n"
                for starter in starters[:10]:  # Limit to first 10 to avoid too much text
                    player_info = starter.get("player_info", {})
                    player_name = player_info.get("full_name", f"Player {starter.get('player_id', 'Unknown')}")
                    position = player_info.get("position", "")
                    team = player_info.get("team", "")
                    
                    player_display = player_name
                    if position:
                        player_display += f" ({position}"
                        if team:
                            player_display += f", {team}"
                        player_display += ")"
                    
                    formatted += f"  • {player_display}\n"
                
                if len(starters) > 10:
                    formatted += f"  • ... and {len(starters) - 10} more\n"
            
            formatted += "\n"
        
        return formatted
    
    def _format_league_rosters_with_draft_response(self, result: Dict[str, Any]) -> str:
        """Format league rosters with draft info response."""
        league_id = result.get("league_id", "Unknown")
        rosters = result.get("rosters", [])
        draft_available = result.get("draft_available", False)
        total_drafted = result.get("total_drafted_players", 0)
        
        formatted = f"🏈 **Rosters with Draft Info for League {league_id}**\n\n"
        
        if draft_available:
            formatted += f"📊 **Draft Summary**: {total_drafted} players drafted\n\n"
        else:
            formatted += "⚠️ **No draft data available for this league**\n\n"
        
        if not rosters:
            formatted += "No rosters found in this league."
            return formatted
        
        for roster in rosters:
            roster_id = roster.get("roster_id", "Unknown")
            owner_info = roster.get("owner_info", {})
            players = roster.get("players", [])
            starters = roster.get("starters", [])
            drafted_count = roster.get("drafted_players", 0)
            fa_count = roster.get("free_agent_pickups", 0)
            
            # Get the best available name for the owner
            display_name = owner_info.get("display_name")
            username = owner_info.get("username")
            is_league_owner = owner_info.get("is_owner", False)
            
            if display_name and display_name != f"User {roster.get('owner_id')}":
                owner_text = display_name
                if username:
                    owner_text += f" (@{username})"
            elif username:
                owner_text = f"@{username}"
            else:
                owner_text = f"User {roster.get('owner_id', 'Unknown')}"
            
            if is_league_owner:
                owner_text += " 👑"
            
            formatted += f"**Roster {roster_id}** - {owner_text}\n"
            
            # Show player counts with draft info
            player_count = roster.get("player_count", len(players))
            starter_count = roster.get("starter_count", len(starters))
            formatted += f"• Total Players: {player_count}\n"
            formatted += f"• Starters: {starter_count}\n"
            formatted += f"• Bench: {player_count - starter_count}\n"
            
            if draft_available:
                formatted += f"• Drafted Players: {drafted_count}\n"
                formatted += f"• Free Agent Pickups: {fa_count}\n"
            
            # Show starting lineup with player names and draft info
            if starters and len(starters) > 0:
                formatted += f"\n**Starting Lineup:**\n"
                for starter in starters[:10]:  # Limit to first 10 to avoid too much text
                    player_info = starter.get("player_info", {})
                    player_name = player_info.get("full_name", f"Player {starter.get('player_id', 'Unknown')}")
                    position = player_info.get("position", "")
                    team = player_info.get("team", "")
                    draft_info = player_info.get("draft_info")
                    acquisition_type = player_info.get("acquisition_type", "unknown")
                    
                    player_display = player_name
                    if position:
                        player_display += f" ({position}"
                        if team:
                            player_display += f", {team}"
                        player_display += ")"
                    
                    # Add draft information
                    if draft_info:
                        round_num = draft_info.get("round")
                        pick_no = draft_info.get("pick_no")
                        is_keeper = draft_info.get("is_keeper", False)
                        drafted_by_name = draft_info.get("drafted_by_name", "Unknown")
                        keeper_text = " 🔒" if is_keeper else ""
                        player_display += f" - Round {round_num}, Pick {pick_no} ({drafted_by_name}){keeper_text}"
                    elif acquisition_type == "free_agent":
                        player_display += " - Free Agent"
                    
                    formatted += f"  • {player_display}\n"
                
                if len(starters) > 10:
                    formatted += f"  • ... and {len(starters) - 10} more\n"
            
            # Show some bench players with draft info
            bench_players = [p for p in players if p not in starters]
            if bench_players and len(bench_players) > 0:
                formatted += f"\n**Key Bench Players:**\n"
                for bench_player in bench_players[:5]:  # Show first 5 bench players
                    player_info = bench_player.get("player_info", {})
                    player_name = player_info.get("full_name", f"Player {bench_player.get('player_id', 'Unknown')}")
                    position = player_info.get("position", "")
                    team = player_info.get("team", "")
                    draft_info = player_info.get("draft_info")
                    acquisition_type = player_info.get("acquisition_type", "unknown")
                    
                    player_display = player_name
                    if position:
                        player_display += f" ({position}"
                        if team:
                            player_display += f", {team}"
                        player_display += ")"
                    
                    # Add draft information
                    if draft_info:
                        round_num = draft_info.get("round")
                        pick_no = draft_info.get("pick_no")
                        is_keeper = draft_info.get("is_keeper", False)
                        drafted_by_name = draft_info.get("drafted_by_name", "Unknown")
                        keeper_text = " 🔒" if is_keeper else ""
                        player_display += f" - Round {round_num}, Pick {pick_no} ({drafted_by_name}){keeper_text}"
                    elif acquisition_type == "free_agent":
                        player_display += " - Free Agent"
                    
                    formatted += f"  • {player_display}\n"
                
                if len(bench_players) > 5:
                    formatted += f"  • ... and {len(bench_players) - 5} more bench players\n"
            
            formatted += "\n"
        
        return formatted
    
    def _format_league_users_response(self, result: Dict[str, Any]) -> str:
        """Format league users response."""
        league_id = result.get("league_id", "Unknown")
        users = result.get("users", [])
        
        formatted = f"👤 **Users in League {league_id}**\n\n"
        
        if not users:
            formatted += "No users found in this league."
            return formatted
        
        for user in users:
            username = user.get("username", "Unknown")
            display_name = user.get("display_name", "Unknown")
            is_owner = user.get("is_owner", False)
            
            formatted += f"**{display_name}** (@{username})"
            if is_owner:
                formatted += " 👑 *League Owner*"
            formatted += "\n"
        
        return formatted
    
    def _format_matchups_response(self, result: Dict[str, Any]) -> str:
        """Format matchups response."""
        league_id = result.get("league_id", "Unknown")
        week = result.get("week", "Unknown")
        matchups = result.get("matchups", [])
        total_matchups = result.get("total_matchups", 0)
        
        formatted = f"⚔️ **Week {week} Matchups - League {league_id}**\n\n"
        
        if not matchups:
            formatted += "No matchups found for this week."
            return formatted
        
        for i, matchup in enumerate(matchups, 1):
            matchup_type = matchup.get("type", "unknown")
            teams = matchup.get("teams", [])
            
            if matchup_type == "bye":
                team = teams[0] if teams else {}
                user_info = team.get("user_info", {})
                team_name = self._format_team_name(team.get('roster_id', 'Unknown'), user_info)
                formatted += f"**Matchup {i}: BYE WEEK**\n"
                formatted += f"• {team_name}: {team.get('points', 0):.1f} pts\n\n"
            else:
                formatted += f"**Matchup {i}:**\n"
                for team in teams:
                    user_info = team.get("user_info", {})
                    team_name = self._format_team_name(team.get('roster_id', 'Unknown'), user_info)
                    formatted += f"• {team_name}: {team.get('points', 0):.1f} pts\n"
                formatted += "\n"
        
        return formatted
    
    def _format_roster_user_mapping_response(self, result: Dict[str, Any]) -> str:
        """Format roster-user mapping response."""
        league_id = result.get("league_id", "Unknown")
        roster_count = result.get("roster_count", 0)
        roster_mapping = result.get("roster_user_mapping", [])
        
        formatted = f"🔗 **Roster-User Mapping for League {league_id}**\n\n"
        
        if not roster_mapping:
            formatted += "No roster-user mapping found for this league."
            return formatted
        
        formatted += f"**{roster_count} Teams:**\n\n"
        
        for mapping in roster_mapping:
            roster_id = mapping.get("roster_id", "Unknown")
            user_info = mapping.get("user_info", {})
            player_count = mapping.get("player_count", 0)
            starter_count = mapping.get("starter_count", 0)
            
            # Get the best available name for the owner
            display_name = user_info.get("display_name")
            username = user_info.get("username")
            is_league_owner = user_info.get("is_owner", False)
            
            if display_name and display_name != f"User {mapping.get('owner_id')}":
                owner_text = display_name
                if username:
                    owner_text += f" (@{username})"
            elif username:
                owner_text = f"@{username}"
            else:
                owner_text = f"User {mapping.get('owner_id', 'Unknown')}"
            
            if is_league_owner:
                owner_text += " 👑"
            
            formatted += f"**Roster {roster_id}** → {owner_text}\n"
            formatted += f"  • Players: {player_count} | Starters: {starter_count}\n\n"
        
        return formatted
    
    def _format_league_draft_response(self, result: Dict[str, Any]) -> str:
        """Format league draft response."""
        league_id = result.get("league_id", "Unknown")
        draft_id = result.get("draft_id", "Unknown")
        draft_type = result.get("draft_type", "unknown")
        status = result.get("status", "unknown")
        season = result.get("season", "unknown")
        total_picks = result.get("total_picks", 0)
        draft_picks = result.get("draft_picks", [])
        
        formatted = f"📋 **Draft Results for League {league_id}**\n\n"
        formatted += f"**Draft Info:**\n"
        formatted += f"• Draft ID: `{draft_id}`\n"
        formatted += f"• Season: {season}\n"
        formatted += f"• Type: {draft_type.replace('_', ' ').title()}\n"
        formatted += f"• Status: {status.replace('_', ' ').title()}\n"
        formatted += f"• Total Picks: {total_picks}\n\n"
        
        if not draft_picks:
            formatted += "No draft picks found."
            return formatted
        
        # Group picks by round for better display
        rounds = {}
        for pick in draft_picks:
            round_num = pick.get("round", 0)
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(pick)
        
        # Show first few rounds in detail
        max_rounds_to_show = 3
        rounds_shown = 0
        
        for round_num in sorted(rounds.keys()):
            if rounds_shown >= max_rounds_to_show:
                remaining_rounds = len(rounds) - rounds_shown
                formatted += f"**... and {remaining_rounds} more rounds with {sum(len(picks) for r, picks in rounds.items() if r > round_num)} picks**\n"
                break
                
            round_picks = rounds[round_num]
            formatted += f"**Round {round_num}:**\n"
            
            for pick in round_picks[:12]:  # Show max 12 picks per round
                pick_no = pick.get("pick_no", 0)
                player_info = pick.get("player_info", {})
                user_info = pick.get("user_info", {})
                is_keeper = pick.get("is_keeper", False)
                
                player_name = player_info.get("full_name", "Unknown Player")
                position = player_info.get("position", "")
                team = player_info.get("team", "")
                
                # Format user name
                display_name = user_info.get("display_name")
                username = user_info.get("username")
                if display_name and display_name != f"User {pick.get('picked_by')}":
                    user_text = display_name
                    if username:
                        user_text += f" (@{username})"
                elif username:
                    user_text = f"@{username}"
                else:
                    user_text = f"User {pick.get('picked_by', 'Unknown')}"
                
                # Format player info
                player_display = player_name
                if position:
                    player_display += f" ({position}"
                    if team:
                        player_display += f", {team}"
                    player_display += ")"
                
                keeper_indicator = " 🔒" if is_keeper else ""
                formatted += f"  {pick_no}. {player_display} → {user_text}{keeper_indicator}\n"
            
            if len(round_picks) > 12:
                formatted += f"  ... and {len(round_picks) - 12} more picks in this round\n"
            
            formatted += "\n"
            rounds_shown += 1
        
        # Add keeper legend if any keepers exist
        if any(pick.get("is_keeper", False) for pick in draft_picks):
            formatted += "🔒 = Keeper pick\n"
        
        return formatted
    
    def _format_team_name(self, roster_id: str, user_info: Dict[str, Any]) -> str:
        """Format a team name with user information."""
        display_name = user_info.get("display_name")
        username = user_info.get("username")
        is_league_owner = user_info.get("is_owner", False)
        
        if display_name and display_name != f"User {roster_id}":
            team_name = display_name
            if username:
                team_name += f" (@{username})"
        elif username:
            team_name = f"@{username}"
        else:
            team_name = f"Roster {roster_id}"
        
        if is_league_owner:
            team_name += " 👑"
        
        return team_name
    
    def _format_matchup_scores_response(self, result: Dict[str, Any]) -> str:
        """Format matchup scores response."""
        league_id = result.get("league_id", "Unknown")
        week = result.get("week", "Unknown")
        scores = result.get("scores", [])
        summary = result.get("summary", {})
        
        formatted = f"📊 **Week {week} Scores - League {league_id}**\n\n"
        
        if summary:
            formatted += f"**Summary:**\n"
            formatted += f"• Teams: {summary.get('total_teams', 0)}\n"
            formatted += f"• Average Score: {summary.get('average_score', 0):.1f}\n"
            formatted += f"• Highest Score: {summary.get('highest_score', 0):.1f}\n"
            formatted += f"• Lowest Score: {summary.get('lowest_score', 0):.1f}\n\n"
        
        if not scores:
            formatted += "No scores found for this week."
            return formatted
        
        # Group scores by matchup for better display
        head_to_head = [s for s in scores if s.get("type") == "head_to_head"]
        byes = [s for s in scores if s.get("type") == "bye"]
        
        if head_to_head:
            formatted += "**Head-to-Head Matchups:**\n"
            matchup_groups = {}
            for score in head_to_head:
                matchup_id = score.get("matchup_id")
                if matchup_id not in matchup_groups:
                    matchup_groups[matchup_id] = []
                matchup_groups[matchup_id].append(score)
            
            for matchup_id, teams in matchup_groups.items():
                formatted += f"• Matchup {matchup_id}: "
                team_scores = []
                for team in teams:
                    roster_id = team.get("roster_id", "Unknown")
                    user_info = team.get("user_info", {})
                    team_name = self._format_team_name(roster_id, user_info)
                    points = team.get("points", 0)
                    is_winning = team.get("is_winning", False)
                    status = " 🏆" if is_winning else ""
                    team_scores.append(f"{team_name}: {points:.1f}{status}")
                formatted += " vs ".join(team_scores) + "\n"
            formatted += "\n"
        
        if byes:
            formatted += "**Bye Weeks:**\n"
            for score in byes:
                roster_id = score.get("roster_id", "Unknown")
                user_info = score.get("user_info", {})
                team_name = self._format_team_name(roster_id, user_info)
                points = score.get("points", 0)
                formatted += f"• {team_name}: {points:.1f} pts\n"
        
        return formatted
    
    def _format_trade_analysis_response(self, result: Dict[str, Any]) -> str:
        """Format trade analysis response."""
        roster_id = result.get("roster_id", "Unknown")
        target_position = result.get("target_position")
        roster_analysis = result.get("roster_analysis", {})
        target_teams = result.get("target_teams", [])
        suggested_trades = result.get("suggested_trades", [])
        analysis_summary = result.get("analysis_summary", "")
        
        formatted = f"🔄 **Trade Analysis for Roster {roster_id}**\n\n"
        
        if target_position:
            formatted += f"**Target Position:** {target_position}\n\n"
        
        if analysis_summary:
            formatted += f"**Summary:** {analysis_summary}\n\n"
        
        # Roster strength analysis
        positional_strength = roster_analysis.get("positional_strength", {})
        if positional_strength:
            formatted += "**Positional Strength:**\n"
            for position, strength in positional_strength.items():
                strength_pct = strength * 100
                if strength >= 0.8:
                    emoji = "💪"
                elif strength >= 0.6:
                    emoji = "👍"
                elif strength >= 0.4:
                    emoji = "⚠️"
                else:
                    emoji = "🔴"
                formatted += f"• {position}: {strength_pct:.0f}% {emoji}\n"
            formatted += "\n"
        
        # Trade targets
        if target_teams:
            formatted += f"**Potential Trade Partners:** {len(target_teams)} teams\n"
            formatted += f"• Target Roster IDs: {', '.join(map(str, target_teams))}\n\n"
        
        # Trade suggestions
        if suggested_trades:
            formatted += "**Trade Suggestions:**\n"
            for i, trade in enumerate(suggested_trades[:3], 1):  # Show top 3
                target_roster = trade.get("target_roster_id", "Unknown")
                rationale = trade.get("trade_rationale", "No rationale provided")
                confidence = trade.get("confidence", 0) * 100
                formatted += f"{i}. **Target Roster {target_roster}** (Confidence: {confidence:.0f}%)\n"
                formatted += f"   {rationale}\n\n"
        
        return formatted
    
    def _format_roster_evaluation_response(self, result: Dict[str, Any]) -> str:
        """Format roster evaluation response."""
        roster_id = result.get("roster_id", "Unknown")
        positional_strength = result.get("positional_strength", {})
        overall_rating = result.get("overall_rating", 0)
        recommendations = result.get("recommendations", [])
        league_comparison = result.get("league_comparison", {})
        
        formatted = f"📋 **Roster Evaluation for Roster {roster_id}**\n\n"
        
        # Overall rating
        rating_pct = overall_rating * 100
        if overall_rating >= 0.8:
            rating_emoji = "🌟"
        elif overall_rating >= 0.6:
            rating_emoji = "👍"
        elif overall_rating >= 0.4:
            rating_emoji = "⚠️"
        else:
            rating_emoji = "🔴"
        
        formatted += f"**Overall Rating:** {rating_pct:.0f}% {rating_emoji}\n\n"
        
        # Positional breakdown
        if positional_strength:
            formatted += "**Positional Strength:**\n"
            sorted_positions = sorted(positional_strength.items(), key=lambda x: x[1], reverse=True)
            
            for position, strength in sorted_positions:
                strength_pct = strength * 100
                if strength >= 0.8:
                    emoji = "💪"
                elif strength >= 0.6:
                    emoji = "👍"
                elif strength >= 0.4:
                    emoji = "⚠️"
                else:
                    emoji = "🔴"
                
                # Add league comparison if available
                comparison = league_comparison.get(position, 0)
                if comparison > 0.1:
                    comp_text = f" (+{comparison*100:.0f}% vs league avg)"
                elif comparison < -0.1:
                    comp_text = f" ({comparison*100:.0f}% vs league avg)"
                else:
                    comp_text = " (≈ league avg)"
                
                formatted += f"• {position}: {strength_pct:.0f}% {emoji}{comp_text}\n"
            formatted += "\n"
        
        # Recommendations
        if recommendations:
            formatted += "**Recommendations:**\n"
            for rec in recommendations:
                formatted += f"• {rec}\n"
        
        return formatted
    
    def _format_search_players_response(self, result: Dict[str, Any]) -> str:
        """Format search players response."""
        query = result.get("query", "Unknown")
        position_filter = result.get("position_filter")
        total_results = result.get("total_results", 0)
        players = result.get("players", [])
        
        formatted = f"🔍 **Player Search Results for '{query}'**"
        if position_filter:
            formatted += f" (Position: {position_filter})"
        formatted += f"\n\n**Found {total_results} players:**\n\n"
        
        if not players:
            formatted += "No players found matching your search criteria."
            return formatted
        
        for i, player in enumerate(players, 1):
            name = player.get("full_name", "Unknown")
            position = player.get("position", "Unknown")
            team = player.get("team", "FA")
            status = player.get("status", "Unknown")
            
            status_emoji = "✅" if status == "Active" else "❌"
            formatted += f"{i}. **{name}** ({position} - {team}) {status_emoji}\n"
            formatted += f"   Player ID: `{player.get('player_id', 'Unknown')}`\n\n"
        
        return formatted
    
    def _format_trending_players_response(self, result: Dict[str, Any]) -> str:
        """Format trending players response."""
        sport = result.get("sport", "nfl").upper()
        trend_type = result.get("trend_type", "add")
        total_results = result.get("total_results", 0)
        players = result.get("players", [])
        
        trend_emoji = "📈" if trend_type == "add" else "📉"
        trend_text = "Most Added" if trend_type == "add" else "Most Dropped"
        
        formatted = f"{trend_emoji} **{trend_text} Players ({sport})**\n\n"
        formatted += f"**Top {total_results} trending players:**\n\n"
        
        if not players:
            formatted += f"No trending {trend_type} data available."
            return formatted
        
        for i, player in enumerate(players, 1):
            name = player.get("full_name", "Unknown")
            position = player.get("position", "Unknown")
            team = player.get("team", "FA")
            count = player.get("count", 0)
            status = player.get("status", "Unknown")
            
            status_emoji = "✅" if status == "Active" else "❌"
            formatted += f"{i}. **{name}** ({position} - {team}) {status_emoji}\n"
            formatted += f"   {trend_type.title()} count: {count:,}\n\n"
        
        return formatted
    
    def _format_player_stats_response(self, result: Dict[str, Any]) -> str:
        """Format player stats response."""
        player_name = result.get("player_name", "Unknown")
        position = result.get("position", "Unknown")
        team = result.get("team", "Unknown")
        season = result.get("season", "Unknown")
        stats = result.get("stats", {})
        
        formatted = f"📊 **{player_name} Stats ({season})**\n\n"
        formatted += f"**Player Info:**\n"
        formatted += f"• Position: {position}\n"
        formatted += f"• Team: {team}\n"
        formatted += f"• Season: {season}\n\n"
        
        if not stats:
            formatted += "No statistics available for this player/season."
            return formatted
        
        formatted += "**Statistics:**\n"
        
        # Group stats by category for better display
        passing_stats = {k: v for k, v in stats.items() if k.startswith('pass_')}
        rushing_stats = {k: v for k, v in stats.items() if k.startswith('rush_')}
        receiving_stats = {k: v for k, v in stats.items() if k.startswith('rec_')}
        other_stats = {k: v for k, v in stats.items() 
                      if not any(k.startswith(prefix) for prefix in ['pass_', 'rush_', 'rec_'])}
        
        if passing_stats:
            formatted += "\n**Passing:**\n"
            for stat, value in passing_stats.items():
                stat_name = stat.replace('pass_', '').replace('_', ' ').title()
                formatted += f"• {stat_name}: {value}\n"
        
        if rushing_stats:
            formatted += "\n**Rushing:**\n"
            for stat, value in rushing_stats.items():
                stat_name = stat.replace('rush_', '').replace('_', ' ').title()
                formatted += f"• {stat_name}: {value}\n"
        
        if receiving_stats:
            formatted += "\n**Receiving:**\n"
            for stat, value in receiving_stats.items():
                stat_name = stat.replace('rec_', '').replace('_', ' ').title()
                formatted += f"• {stat_name}: {value}\n"
        
        if other_stats:
            formatted += "\n**Other:**\n"
            for stat, value in other_stats.items():
                stat_name = stat.replace('_', ' ').title()
                formatted += f"• {stat_name}: {value}\n"
        
        return formatted
    
    async def run(self) -> None:
        """Run the MCP server."""
        # Initialize server components
        await self.initialize()
        
        # Run the server with stdio transport
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="sleeper-mcp-server",
                    server_version="0.1.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(
                            prompts_changed=False,
                            resources_changed=False,
                            tools_changed=False
                        ),
                        experimental_capabilities={}
                    )
                )
            )


async def main() -> None:
    """Main entry point for the MCP server."""
    # Configure logging to stderr to avoid interfering with MCP protocol
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr
    )
    
    try:
        # Create and run server
        server = SleeperMCPServer()
        await server.run()
    except KeyboardInterrupt:
        # Handle graceful shutdown
        pass
    except Exception as e:
        # Log errors to stderr to avoid breaking MCP protocol
        logger.error(f"Fatal server error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())