"""
League management tools for the Sleeper MCP server.

This module provides MCP tools for querying league information, rosters,
and user data from the Sleeper Fantasy Football API.
"""

import asyncio
import logging
from typing import List, Optional

from ..sleeper_client import SleeperClient, SleeperAPIError
from ..models import League, User, Roster, ErrorResponse
from ..cache import CacheManager, CacheDataType

logger = logging.getLogger(__name__)


class LeagueTools:
    """Collection of MCP tools for league management functionality."""
    
    def __init__(self, client: SleeperClient, cache: CacheManager):
        """
        Initialize league tools.
        
        Args:
            client: Sleeper API client instance
            cache: Cache manager instance
        """
        self.client = client
        self.cache = cache
    
    async def get_user_leagues(self, username: str, season: str = "2024") -> dict:
        """
        Get all leagues for a username in a specific season.
        
        Args:
            username: Sleeper username to look up
            season: Season year (default: "2024")
            
        Returns:
            Dictionary with leagues list or error information
        """
        try:
            # Check cache first
            cache_key = f"user_leagues:{username}:{season}"
            cached_result = self.cache.get(cache_key, CacheDataType.LEAGUE_SETTINGS)
            if cached_result is not None:
                return cached_result
            
            # Get user information first
            user = await self.client.get_user(username)
            if user is None:
                return {
                    "error": f"User '{username}' not found",
                    "suggestions": [
                        "Check the username spelling",
                        "Ensure the user has a public Sleeper profile"
                    ]
                }
            
            # Get user's leagues
            leagues = await self.client.get_user_leagues(user.user_id, season)
            
            # Format response
            result = {
                "username": username,
                "user_id": user.user_id,
                "season": season,
                "leagues": [
                    {
                        "league_id": league.league_id,
                        "name": league.name,
                        "status": league.status.value,
                        "total_rosters": league.total_rosters,
                        "sport": league.sport,
                        "season_type": league.season_type
                    }
                    for league in leagues
                ]
            }
            
            # Cache the result for 1 hour
            self.cache.set(cache_key, result, CacheDataType.LEAGUE_SETTINGS, ttl_override=3600)
            
            logger.info(f"Retrieved {len(leagues)} leagues for user {username}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting leagues for {username}: {e}")
            return {
                "error": f"Failed to retrieve leagues: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting leagues for {username}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving leagues",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def get_league_info(self, league_id: str) -> dict:
        """
        Get detailed information about a specific league.
        
        Args:
            league_id: League ID to retrieve information for
            
        Returns:
            Dictionary with league information or error details
        """
        try:
            # Check cache first
            cache_key = f"league_info:{league_id}"
            cached_result = self.cache.get(cache_key, CacheDataType.LEAGUE_SETTINGS)
            if cached_result is not None:
                return cached_result
            
            # Get league information
            league = await self.client.get_league(league_id)
            if league is None:
                return {
                    "error": f"League '{league_id}' not found",
                    "suggestions": [
                        "Verify the league ID is correct",
                        "Ensure you have access to this league"
                    ]
                }
            
            # Format detailed league information
            result = {
                "league_id": league.league_id,
                "name": league.name,
                "season": league.season,
                "season_type": league.season_type,
                "status": league.status.value,
                "sport": league.sport,
                "total_rosters": league.total_rosters,
                "draft_id": league.draft_id,
                "avatar": league.avatar,
                "settings": {
                    "num_teams": league.settings.num_teams,
                    "playoff_teams": league.settings.playoff_teams,
                    "playoff_weeks": league.settings.playoff_weeks,
                    "daily_waivers": league.settings.daily_waivers,
                    "waiver_type": league.settings.waiver_type,
                    "waiver_clear_days": league.settings.waiver_clear_days,
                    "reserve_slots": league.settings.reserve_slots,
                    "taxi_slots": league.settings.taxi_slots,
                    "bench_lock": league.settings.bench_lock
                },
                "roster_positions": league.roster_positions,
                "scoring_settings": league.scoring_settings
            }
            
            # Cache the result for 24 hours (league settings rarely change)
            self.cache.set(cache_key, result, CacheDataType.LEAGUE_SETTINGS)
            
            logger.info(f"Retrieved league info for {league_id}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting league info for {league_id}: {e}")
            return {
                "error": f"Failed to retrieve league information: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting league info for {league_id}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving league information",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def get_league_rosters_with_draft_info(self, league_id: str) -> dict:
        """
        Get all team rosters in a league with draft position metadata for each player.
        
        Args:
            league_id: League ID to retrieve rosters for
            
        Returns:
            Dictionary with roster information including draft metadata or error details
        """
        try:
            # Check cache first
            cache_key = f"league_rosters_with_draft:{league_id}"
            cached_result = self.cache.get(cache_key, CacheDataType.ROSTER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get league info, rosters, users, players, and draft data concurrently
            league_task = self.client.get_league(league_id)
            rosters_task = self.client.get_league_rosters(league_id)
            users_task = self.client.get_league_users(league_id)
            players_task = self.client.get_players()
            
            league, rosters, users, all_players = await asyncio.gather(
                league_task, rosters_task, users_task, players_task, return_exceptions=True
            )
            
            # Handle rosters result
            if isinstance(rosters, Exception) or not rosters:
                return {
                    "error": f"No rosters found for league '{league_id}'",
                    "suggestions": [
                        "Verify the league ID is correct",
                        "Check if the league has been set up with teams"
                    ]
                }
            
            # Get draft data if available
            draft_picks_map = {}  # player_id -> draft info
            if not isinstance(league, Exception) and league and league.draft_id:
                try:
                    draft_picks = await self.client.get_draft_picks(league.draft_id)
                    if draft_picks:
                        for pick in draft_picks:
                            player_id = pick.get("player_id")
                            if player_id:
                                draft_picks_map[player_id] = {
                                    "pick_no": pick.get("pick_no"),
                                    "round": pick.get("round"),
                                    "draft_slot": pick.get("draft_slot"),
                                    "is_keeper": pick.get("is_keeper", False),
                                    "drafted_by": pick.get("picked_by")
                                }
                except Exception as e:
                    logger.warning(f"Could not retrieve draft data: {e}")
            
            # Create user mapping (owner_id -> user info)
            user_map = {}
            if not isinstance(users, Exception) and users:
                user_map = {
                    user.user_id: {
                        "username": user.username,
                        "display_name": user.display_name,
                        "avatar": user.avatar,
                        "is_owner": user.is_owner
                    }
                    for user in users
                }
            
            # Create player mapping (player_id -> player info)
            player_map = {}
            if not isinstance(all_players, Exception) and all_players:
                player_map = {
                    player_id: {
                        "full_name": player.full_name,
                        "position": player.position,
                        "team": player.team,
                        "status": player.status.value if player.status else None
                    }
                    for player_id, player in all_players.items()
                }
            
            # Helper function to enrich player list with names and draft info
            def enrich_player_list_with_draft(player_ids):
                enriched_players = []
                for player_id in (player_ids or []):
                    player_info = player_map.get(player_id, {
                        "full_name": f"Player {player_id}",
                        "position": "Unknown",
                        "team": None,
                        "status": None
                    })
                    
                    # Add draft information
                    draft_info = draft_picks_map.get(player_id)
                    if draft_info:
                        # Add team name that drafted the player
                        drafted_by_id = draft_info.get("drafted_by")
                        drafted_by_info = user_map.get(drafted_by_id, {})
                        drafted_by_name = drafted_by_info.get("display_name") or drafted_by_info.get("username") or f"User {drafted_by_id}"
                        
                        # Create enhanced draft info with team name
                        enhanced_draft_info = draft_info.copy()
                        enhanced_draft_info["drafted_by_name"] = drafted_by_name
                        
                        player_info["draft_info"] = enhanced_draft_info
                        player_info["acquisition_type"] = "draft"
                    else:
                        player_info["draft_info"] = None
                        player_info["acquisition_type"] = "free_agent"
                    
                    enriched_players.append({
                        "player_id": player_id,
                        "player_info": player_info
                    })
                
                return enriched_players
            
            # Format roster information with user details, player names, and draft info
            result = {
                "league_id": league_id,
                "draft_available": bool(draft_picks_map),
                "total_drafted_players": len(draft_picks_map),
                "rosters": [
                    {
                        "roster_id": roster.roster_id,
                        "owner_id": roster.owner_id,
                        "owner_info": user_map.get(roster.owner_id, {
                            "username": None,
                            "display_name": f"User {roster.owner_id}",
                            "avatar": None,
                            "is_owner": False
                        }),
                        "players": enrich_player_list_with_draft(roster.players),
                        "starters": enrich_player_list_with_draft(roster.starters),
                        "reserve": enrich_player_list_with_draft(roster.reserve),
                        "taxi": enrich_player_list_with_draft(roster.taxi),
                        "player_count": len(roster.players or []),
                        "starter_count": len(roster.starters or []),
                        "drafted_players": len([p for p in (roster.players or []) if p in draft_picks_map]),
                        "free_agent_pickups": len([p for p in (roster.players or []) if p not in draft_picks_map]),
                        "settings": roster.settings or {},
                        "metadata": roster.metadata or {}
                    }
                    for roster in rosters
                ]
            }
            
            # Cache the result for 15 minutes (rosters change frequently)
            self.cache.set(cache_key, result, CacheDataType.ROSTER_DATA)
            
            logger.info(f"Retrieved {len(rosters)} rosters with draft info for league {league_id}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting rosters with draft info for league {league_id}: {e}")
            return {
                "error": f"Failed to retrieve league rosters with draft info: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting rosters with draft info for league {league_id}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving league rosters with draft info",
                "suggestions": ["Try again in a few moments"]
            }

    async def get_league_rosters(self, league_id: str) -> dict:
        """
        Get all team rosters in a league.
        
        Args:
            league_id: League ID to retrieve rosters for
            
        Returns:
            Dictionary with roster information or error details
        """
        try:
            # Check cache first
            cache_key = f"league_rosters:{league_id}"
            cached_result = self.cache.get(cache_key, CacheDataType.ROSTER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get league rosters, users, and all players concurrently for better performance
            rosters_task = self.client.get_league_rosters(league_id)
            users_task = self.client.get_league_users(league_id)
            players_task = self.client.get_players()
            
            rosters, users, all_players = await asyncio.gather(rosters_task, users_task, players_task, return_exceptions=True)
            
            # Handle rosters result
            if isinstance(rosters, Exception) or not rosters:
                return {
                    "error": f"No rosters found for league '{league_id}'",
                    "suggestions": [
                        "Verify the league ID is correct",
                        "Check if the league has been set up with teams"
                    ]
                }
            
            # Create user mapping (owner_id -> user info)
            user_map = {}
            if not isinstance(users, Exception) and users:
                user_map = {
                    user.user_id: {
                        "username": user.username,
                        "display_name": user.display_name,
                        "avatar": user.avatar,
                        "is_owner": user.is_owner
                    }
                    for user in users
                }
            
            # Create player mapping (player_id -> player info)
            player_map = {}
            if not isinstance(all_players, Exception) and all_players:
                player_map = {
                    player_id: {
                        "full_name": player.full_name,
                        "position": player.position,
                        "team": player.team,
                        "status": player.status.value if player.status else None
                    }
                    for player_id, player in all_players.items()
                }
            
            # Helper function to enrich player list with names
            def enrich_player_list(player_ids):
                return [
                    {
                        "player_id": player_id,
                        "player_info": player_map.get(player_id, {
                            "full_name": f"Player {player_id}",
                            "position": "Unknown",
                            "team": None,
                            "status": None
                        })
                    }
                    for player_id in (player_ids or [])
                ]
            
            # Format roster information with user details and player names
            result = {
                "league_id": league_id,
                "rosters": [
                    {
                        "roster_id": roster.roster_id,
                        "owner_id": roster.owner_id,
                        "owner_info": user_map.get(roster.owner_id, {
                            "username": None,
                            "display_name": f"User {roster.owner_id}",
                            "avatar": None,
                            "is_owner": False
                        }),
                        "players": enrich_player_list(roster.players),
                        "starters": enrich_player_list(roster.starters),
                        "reserve": enrich_player_list(roster.reserve),
                        "taxi": enrich_player_list(roster.taxi),
                        "player_count": len(roster.players or []),
                        "starter_count": len(roster.starters or []),
                        "settings": roster.settings or {},
                        "metadata": roster.metadata or {}
                    }
                    for roster in rosters
                ]
            }
            
            # Cache the result for 15 minutes (rosters change frequently)
            self.cache.set(cache_key, result, CacheDataType.ROSTER_DATA)
            
            logger.info(f"Retrieved {len(rosters)} rosters for league {league_id}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting rosters for league {league_id}: {e}")
            return {
                "error": f"Failed to retrieve league rosters: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting rosters for league {league_id}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving league rosters",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def get_league_users(self, league_id: str) -> dict:
        """
        Get all users/participants in a league.
        
        Args:
            league_id: League ID to retrieve users for
            
        Returns:
            Dictionary with user information or error details
        """
        try:
            # Check cache first
            cache_key = f"league_users:{league_id}"
            cached_result = self.cache.get(cache_key, CacheDataType.LEAGUE_SETTINGS)
            if cached_result is not None:
                return cached_result
            
            # Get league users
            users = await self.client.get_league_users(league_id)
            if not users:
                return {
                    "error": f"No users found for league '{league_id}'",
                    "suggestions": [
                        "Verify the league ID is correct",
                        "Check if the league exists and has participants"
                    ]
                }
            
            # Format user information
            result = {
                "league_id": league_id,
                "users": [
                    {
                        "user_id": user.user_id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "avatar": user.avatar,
                        "is_owner": user.is_owner,
                        "metadata": user.metadata or {}
                    }
                    for user in users
                ]
            }
            
            # Cache the result for 1 hour (user list rarely changes mid-season)
            self.cache.set(cache_key, result, CacheDataType.LEAGUE_SETTINGS, ttl_override=3600)
            
            logger.info(f"Retrieved {len(users)} users for league {league_id}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting users for league {league_id}: {e}")
            return {
                "error": f"Failed to retrieve league users: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting users for league {league_id}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving league users",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def get_roster_user_mapping(self, league_id: str) -> dict:
        """
        Get a mapping of roster IDs to user information.
        
        Args:
            league_id: League ID to get roster-user mapping for
            
        Returns:
            Dictionary with roster-to-user mapping or error details
        """
        try:
            # Check cache first
            cache_key = f"roster_user_mapping:{league_id}"
            cached_result = self.cache.get(cache_key, CacheDataType.ROSTER_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get both rosters and users concurrently
            rosters_task = self.client.get_league_rosters(league_id)
            users_task = self.client.get_league_users(league_id)
            
            rosters, users = await asyncio.gather(rosters_task, users_task, return_exceptions=True)
            
            # Handle rosters result
            if isinstance(rosters, Exception) or not rosters:
                return {
                    "error": f"Could not retrieve rosters for league '{league_id}'",
                    "suggestions": [
                        "Verify the league ID is correct",
                        "Check if the league has been set up with teams"
                    ]
                }
            
            # Create user mapping (owner_id -> user info)
            user_map = {}
            if not isinstance(users, Exception) and users:
                user_map = {
                    user.user_id: {
                        "username": user.username,
                        "display_name": user.display_name,
                        "avatar": user.avatar,
                        "is_owner": user.is_owner
                    }
                    for user in users
                }
            
            # Create roster-to-user mapping
            roster_mapping = []
            for roster in rosters:
                user_info = user_map.get(roster.owner_id, {
                    "username": None,
                    "display_name": f"User {roster.owner_id}",
                    "avatar": None,
                    "is_owner": False
                })
                
                roster_mapping.append({
                    "roster_id": roster.roster_id,
                    "owner_id": roster.owner_id,
                    "user_info": user_info,
                    "player_count": len(roster.players),
                    "starter_count": len(roster.starters)
                })
            
            # Sort by roster_id for consistent ordering
            roster_mapping.sort(key=lambda x: x["roster_id"])
            
            result = {
                "league_id": league_id,
                "roster_count": len(roster_mapping),
                "roster_user_mapping": roster_mapping
            }
            
            # Cache the result for 15 minutes
            self.cache.set(cache_key, result, CacheDataType.ROSTER_DATA, ttl_override=900)
            
            logger.info(f"Retrieved roster-user mapping for {len(roster_mapping)} rosters in league {league_id}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting roster-user mapping for league {league_id}: {e}")
            return {
                "error": f"Failed to retrieve roster-user mapping: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting roster-user mapping for league {league_id}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving roster-user mapping",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def get_league_draft(self, league_id: str) -> dict:
        """
        Get draft information for a league.
        
        Args:
            league_id: League ID to get draft information for
            
        Returns:
            Dictionary with draft information or error details
        """
        try:
            # Check cache first
            cache_key = f"league_draft:{league_id}"
            cached_result = self.cache.get(cache_key, CacheDataType.LEAGUE_SETTINGS)
            if cached_result is not None:
                return cached_result
            
            # First get league info to get the draft_id
            league = await self.client.get_league(league_id)
            if not league or not league.draft_id:
                return {
                    "error": f"No draft found for league '{league_id}'",
                    "suggestions": [
                        "This league may not have completed a draft yet",
                        "Check if this is a dynasty/keeper league with draft history",
                        "Verify the league ID is correct"
                    ]
                }
            
            # Get draft data, draft picks, and users concurrently
            draft_task = self.client.get_draft(league.draft_id)
            picks_task = self.client.get_draft_picks(league.draft_id)
            users_task = self.client.get_league_users(league_id)
            
            draft_data, draft_picks_data, users = await asyncio.gather(draft_task, picks_task, users_task, return_exceptions=True)
            
            if isinstance(draft_data, Exception) or not draft_data:
                return {
                    "error": f"Could not retrieve draft data for league '{league_id}'",
                    "suggestions": [
                        "The draft may not be accessible",
                        "Try again in a few moments"
                    ]
                }
            
            # Handle draft picks data
            if isinstance(draft_picks_data, Exception):
                logger.warning(f"Could not retrieve draft picks: {draft_picks_data}")
                draft_picks_data = []
            
            # Create user mapping for draft picks
            user_map = {}
            if not isinstance(users, Exception) and users:
                user_map = {
                    user.user_id: {
                        "username": user.username,
                        "display_name": user.display_name,
                        "avatar": user.avatar,
                        "is_owner": user.is_owner
                    }
                    for user in users
                }
            
            # Use the separate draft picks data
            picks = draft_picks_data or []
            draft_order = draft_data.get("draft_order", [])
            
            logger.info(f"Retrieved draft data with {len(picks)} picks for league {league_id}")
            
            # Get player data for draft picks
            try:
                all_players = await self.client.get_players()
                player_map = {
                    player_id: {
                        "full_name": player.full_name,
                        "position": player.position,
                        "team": player.team,
                        "status": player.status.value if player.status else None
                    }
                    for player_id, player in all_players.items()
                } if all_players else {}
            except Exception:
                player_map = {}
            
            # Format draft picks with player and user information
            formatted_picks = []
            for pick in picks:
                player_id = pick.get("player_id")
                picked_by = pick.get("picked_by")
                
                player_info = player_map.get(player_id, {
                    "full_name": f"Player {player_id}",
                    "position": "Unknown",
                    "team": None,
                    "status": None
                })
                
                user_info = user_map.get(picked_by, {
                    "username": None,
                    "display_name": f"User {picked_by}",
                    "avatar": None,
                    "is_owner": False
                })
                
                formatted_picks.append({
                    "pick_no": pick.get("pick_no", 0),
                    "round": pick.get("round", 0),
                    "draft_slot": pick.get("draft_slot", 0),
                    "player_id": player_id,
                    "player_info": player_info,
                    "picked_by": picked_by,
                    "user_info": user_info,
                    "is_keeper": pick.get("is_keeper", False),
                    "metadata": pick.get("metadata", {})
                })
            
            # Sort picks by pick number
            formatted_picks.sort(key=lambda x: x["pick_no"])
            
            result = {
                "league_id": league_id,
                "draft_id": league.draft_id,
                "draft_type": draft_data.get("type", "unknown"),
                "status": draft_data.get("status", "unknown"),
                "season": draft_data.get("season", "unknown"),
                "total_picks": len(formatted_picks),
                "draft_picks": formatted_picks,
                "draft_order": draft_order
            }
            
            # Cache the result for 24 hours (draft data doesn't change)
            self.cache.set(cache_key, result, CacheDataType.LEAGUE_SETTINGS, ttl_override=86400)
            
            logger.info(f"Retrieved draft data with {len(formatted_picks)} picks for league {league_id}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting draft for league {league_id}: {e}")
            return {
                "error": f"Failed to retrieve draft data: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting draft for league {league_id}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving draft data",
                "suggestions": ["Try again in a few moments"]
            }