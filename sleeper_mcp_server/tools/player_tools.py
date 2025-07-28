"""
Player information and search tools for the Sleeper MCP server.

This module provides MCP tools for querying player information, statistics,
and trending data from the Sleeper Fantasy Football API.
"""

import logging
from typing import Dict, List, Optional

from ..sleeper_client import SleeperClient, SleeperAPIError
from ..models import Player, TrendingPlayer, PlayerStats, ErrorResponse
from ..cache import CacheManager, CacheDataType

logger = logging.getLogger(__name__)


class PlayerTools:
    """Collection of MCP tools for player information functionality."""
    
    def __init__(self, client: SleeperClient, cache: CacheManager):
        """
        Initialize player tools.
        
        Args:
            client: Sleeper API client instance
            cache: Cache manager instance
        """
        self.client = client
        self.cache = cache
    
    async def search_players(self, query: str, position: Optional[str] = None) -> dict:
        """
        Search for players by name with optional position filtering.
        
        Args:
            query: Player name or partial name to search for
            position: Optional position filter (QB, RB, WR, TE, K, DEF)
            
        Returns:
            Dictionary with player search results or error information
        """
        try:
            # Check cache first
            cache_key = f"search_players:{query}:{position or 'all'}"
            cached_result = self.cache.get(cache_key, CacheDataType.PLAYER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get all players (this would normally be cached for a long time)
            all_players = await self.client.get_players("nfl")
            
            # Filter players by query
            matching_players = []
            query_lower = query.lower()
            
            for player_id, player in all_players.items():
                # Check if name matches
                if query_lower in player.full_name.lower():
                    # Apply position filter if specified
                    if position is None or player.position == position:
                        matching_players.append({
                            "player_id": player.player_id,
                            "full_name": player.full_name,
                            "position": player.position,
                            "team": player.team,
                            "status": player.status.value if player.status else None
                        })
            
            # Sort by relevance (exact matches first, then alphabetical)
            matching_players.sort(key=lambda p: (
                not p["full_name"].lower().startswith(query_lower),
                p["full_name"]
            ))
            
            # Limit results to prevent overwhelming response
            matching_players = matching_players[:20]
            
            result = {
                "query": query,
                "position_filter": position,
                "total_results": len(matching_players),
                "players": matching_players
            }
            
            # Cache for 1 hour
            self.cache.set(cache_key, result, CacheDataType.PLAYER_DATA, ttl_override=3600)
            
            logger.info(f"Found {len(matching_players)} players matching '{query}'")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error searching players: {e}")
            return {
                "error": f"Failed to search players: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error searching players: {e}")
            return {
                "error": "An unexpected error occurred while searching players",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def get_trending_players(self, sport: str = "nfl", add_drop: str = "add") -> dict:
        """
        Get trending players (most added/dropped).
        
        Args:
            sport: Sport type (default: "nfl")
            add_drop: Type of trend - "add" or "drop" (default: "add")
            
        Returns:
            Dictionary with trending players or error information
        """
        try:
            # Validate add_drop parameter
            if add_drop not in ["add", "drop"]:
                return {
                    "error": "Invalid add_drop parameter. Must be 'add' or 'drop'",
                    "suggestions": ["Use 'add' for most added players", "Use 'drop' for most dropped players"]
                }
            
            # Check cache first
            cache_key = f"trending_players:{sport}:{add_drop}"
            cached_result = self.cache.get(cache_key, CacheDataType.PLAYER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get trending players from API
            trending_data = await self.client.get_trending_players(sport, add_drop)
            
            if not trending_data:
                return {
                    "error": f"No trending {add_drop} data available for {sport}",
                    "suggestions": ["Try again later", "Check if the sport parameter is correct"]
                }
            
            # Get player details for trending players
            all_players = await self.client.get_players(sport)
            
            trending_players = []
            for trend in trending_data[:15]:  # Limit to top 15
                player_id = trend.player_id
                if player_id in all_players:
                    player = all_players[player_id]
                    trending_players.append({
                        "player_id": player.player_id,
                        "full_name": player.full_name,
                        "position": player.position,
                        "team": player.team,
                        "count": trend.count,
                        "status": player.status.value if player.status else None
                    })
            
            result = {
                "sport": sport,
                "trend_type": add_drop,
                "total_results": len(trending_players),
                "players": trending_players
            }
            
            # Cache for 30 minutes (trending data changes frequently)
            self.cache.set(cache_key, result, CacheDataType.PLAYER_DATA, ttl_override=1800)
            
            logger.info(f"Retrieved {len(trending_players)} trending {add_drop} players")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting trending players: {e}")
            return {
                "error": f"Failed to retrieve trending players: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting trending players: {e}")
            return {
                "error": "An unexpected error occurred while retrieving trending players",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def get_player_stats(self, player_id: str, season: str = "2024") -> dict:
        """
        Get player statistics for a specific season.
        
        Args:
            player_id: Player ID to get stats for
            season: Season year (default: "2024")
            
        Returns:
            Dictionary with player stats or error information
        """
        try:
            # Check cache first
            cache_key = f"player_stats:{player_id}:{season}"
            cached_result = self.cache.get(cache_key, CacheDataType.PLAYER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get player stats from API
            stats = await self.client.get_player_stats(player_id, season)
            
            if not stats:
                # Try to get player info to provide better error message
                all_players = await self.client.get_players("nfl")
                if player_id in all_players:
                    player = all_players[player_id]
                    return {
                        "error": f"No stats found for {player.full_name} in {season} season",
                        "suggestions": [
                            "Check if the player was active in this season",
                            "Try a different season year",
                            "Verify the player ID is correct"
                        ],
                        "player_name": player.full_name
                    }
                else:
                    return {
                        "error": f"Player ID '{player_id}' not found",
                        "suggestions": ["Verify the player ID is correct"]
                    }
            
            # Get player info for context
            all_players = await self.client.get_players("nfl")
            player_info = all_players.get(player_id)
            
            result = {
                "player_id": player_id,
                "season": season,
                "player_name": player_info.full_name if player_info else "Unknown",
                "position": player_info.position if player_info else "Unknown",
                "team": player_info.team if player_info else "Unknown",
                "stats": stats.stats if hasattr(stats, 'stats') else stats
            }
            
            # Cache for 1 hour (stats don't change frequently)
            self.cache.set(cache_key, result, CacheDataType.PLAYER_DATA, ttl_override=3600)
            
            logger.info(f"Retrieved stats for player {player_id} in {season}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting player stats: {e}")
            return {
                "error": f"Failed to retrieve player stats: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting player stats: {e}")
            return {
                "error": "An unexpected error occurred while retrieving player stats",
                "suggestions": ["Try again in a few moments"]
            }