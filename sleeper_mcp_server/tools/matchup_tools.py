"""
Matchup and scoring tools for the Sleeper MCP server.

This module provides MCP tools for querying matchup information, scores,
and historical matchup data from the Sleeper Fantasy Football API.
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any

from ..sleeper_client import SleeperClient, SleeperAPIError
from ..models import Matchup, League, ErrorResponse
from ..cache import CacheManager, CacheDataType

logger = logging.getLogger(__name__)


class MatchupTools:
    """Collection of MCP tools for matchup and scoring functionality."""
    
    def __init__(self, client: SleeperClient, cache: CacheManager):
        """
        Initialize matchup tools.
        
        Args:
            client: Sleeper API client instance
            cache: Cache manager instance
        """
        self.client = client
        self.cache = cache
    
    def _validate_week_number(self, week: int, league: Optional[League] = None) -> Optional[str]:
        """
        Validate week number is within reasonable bounds.
        
        Args:
            week: Week number to validate
            league: Optional league info for more specific validation
            
        Returns:
            Error message if invalid, None if valid
        """
        if week < 1:
            return "Week number must be 1 or greater"
        
        # NFL regular season is typically weeks 1-18, playoffs 19-22
        if week > 22:
            return "Week number cannot exceed 22 (NFL season + playoffs)"
        
        # If we have league info, we could do more specific validation
        # based on league settings, but for now keep it simple
        
        return None
    
    async def get_matchups(self, league_id: str, week: int) -> dict:
        """
        Get matchups for a specific week in a league.
        
        Args:
            league_id: League ID to retrieve matchups for
            week: Week number (1-22)
            
        Returns:
            Dictionary with matchup information or error details
        """
        try:
            # Validate week number
            week_error = self._validate_week_number(week)
            if week_error:
                return {
                    "error": week_error,
                    "suggestions": [
                        "Use week numbers between 1 and 18 for regular season",
                        "Use week numbers 19-22 for playoffs"
                    ]
                }
            
            # Check cache first
            cache_key = f"matchups:{league_id}:{week}"
            cached_result = self.cache.get(cache_key, CacheDataType.MATCHUP_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get matchups and users concurrently for better performance
            matchups_task = self.client.get_matchups(league_id, week)
            users_task = self.client.get_league_users(league_id)
            
            matchups, users = await asyncio.gather(matchups_task, users_task, return_exceptions=True)
            
            # Handle matchups result
            if isinstance(matchups, Exception):
                matchups = None
            
            # Handle case where no matchups exist for the week
            if not matchups:
                # Try to get league info to provide better error message
                league = await self.client.get_league(league_id)
                if league is None:
                    return {
                        "error": f"League '{league_id}' not found",
                        "suggestions": [
                            "Verify the league ID is correct",
                            "Ensure you have access to this league"
                        ]
                    }
                
                return {
                    "error": f"No matchups found for week {week} in league '{league.name}'",
                    "suggestions": [
                        f"Check if week {week} has started or is scheduled",
                        "Verify the week number is within the current season",
                        "Try a different week number"
                    ],
                    "league_name": league.name,
                    "league_status": league.status.value
                }
            
            # Create user mapping (roster_id -> user info)
            user_map = {}
            if not isinstance(users, Exception) and users:
                # First get roster data to map owner_id to roster_id
                try:
                    rosters = await self.client.get_league_rosters(league_id)
                    if rosters:
                        roster_to_owner = {roster.roster_id: roster.owner_id for roster in rosters}
                        user_info_map = {
                            user.user_id: {
                                "username": user.username,
                                "display_name": user.display_name,
                                "avatar": user.avatar,
                                "is_owner": user.is_owner
                            }
                            for user in users
                        }
                        # Map roster_id to user info
                        for roster_id, owner_id in roster_to_owner.items():
                            if owner_id in user_info_map:
                                user_map[roster_id] = user_info_map[owner_id]
                except Exception:
                    pass  # Continue without user mapping if roster fetch fails
            
            # Group matchups by matchup_id to show head-to-head pairings
            matchup_groups: Dict[Optional[int], List[Matchup]] = {}
            for matchup in matchups:
                matchup_id = matchup.matchup_id
                if matchup_id not in matchup_groups:
                    matchup_groups[matchup_id] = []
                matchup_groups[matchup_id].append(matchup)
            
            # Format the response
            formatted_matchups = []
            for matchup_id, teams in matchup_groups.items():
                if matchup_id is None:
                    # Handle bye weeks or single-team matchups
                    for team in teams:
                        user_info = user_map.get(team.roster_id, {
                            "username": None,
                            "display_name": f"User {team.roster_id}",
                            "avatar": None,
                            "is_owner": False
                        })
                        formatted_matchups.append({
                            "matchup_id": None,
                            "type": "bye",
                            "teams": [{
                                "roster_id": team.roster_id,
                                "user_info": user_info,
                                "points": team.points,
                                "points_bonus": team.points_bonus or 0.0,
                                "players": team.players,
                                "starters": team.starters,
                                "starters_points": team.starters_points or [],
                                "players_points": team.players_points or {},
                                "custom_points": team.custom_points
                            }]
                        })
                else:
                    # Regular head-to-head matchup
                    formatted_teams = []
                    for team in teams:
                        user_info = user_map.get(team.roster_id, {
                            "username": None,
                            "display_name": f"User {team.roster_id}",
                            "avatar": None,
                            "is_owner": False
                        })
                        formatted_teams.append({
                            "roster_id": team.roster_id,
                            "user_info": user_info,
                            "points": team.points,
                            "points_bonus": team.points_bonus or 0.0,
                            "players": team.players,
                            "starters": team.starters,
                            "starters_points": team.starters_points or [],
                            "players_points": team.players_points or {},
                            "custom_points": team.custom_points
                        })
                    
                    formatted_matchups.append({
                        "matchup_id": matchup_id,
                        "type": "head_to_head",
                        "teams": formatted_teams
                    })
            
            result = {
                "league_id": league_id,
                "week": week,
                "matchups": formatted_matchups,
                "total_matchups": len(formatted_matchups)
            }
            
            # Cache the result - shorter TTL for current week, longer for completed weeks
            # Assume current week if points are still changing (incomplete matchups)
            is_live = any(
                any(team["points"] > 0 and team.get("players_points") for team in matchup["teams"])
                for matchup in formatted_matchups
            )
            ttl = 300 if is_live else 3600  # 5 minutes if live, 1 hour if completed
            
            self.cache.set(cache_key, result, CacheDataType.MATCHUP_DATA, ttl_override=ttl)
            
            logger.info(f"Retrieved {len(formatted_matchups)} matchups for league {league_id}, week {week}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting matchups for league {league_id}, week {week}: {e}")
            return {
                "error": f"Failed to retrieve matchups: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting matchups for league {league_id}, week {week}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving matchups",
                "suggestions": ["Try again in a few moments"]
            }
    
    async def get_matchup_scores(self, league_id: str, week: int) -> dict:
        """
        Get real-time scoring information for matchups in a specific week.
        
        Args:
            league_id: League ID to retrieve scores for
            week: Week number (1-22)
            
        Returns:
            Dictionary with scoring information or error details
        """
        try:
            # Validate week number
            week_error = self._validate_week_number(week)
            if week_error:
                return {
                    "error": week_error,
                    "suggestions": [
                        "Use week numbers between 1 and 18 for regular season",
                        "Use week numbers 19-22 for playoffs"
                    ]
                }
            
            # Check cache first (shorter TTL for scores as they update frequently)
            cache_key = f"matchup_scores:{league_id}:{week}"
            cached_result = self.cache.get(cache_key, CacheDataType.MATCHUP_DATA)
            if cached_result is not None:
                return cached_result
            
            # Get matchups and users concurrently for better performance
            matchups_task = self.client.get_matchups(league_id, week)
            users_task = self.client.get_league_users(league_id)
            
            matchups, users = await asyncio.gather(matchups_task, users_task, return_exceptions=True)
            
            # Handle matchups result
            if isinstance(matchups, Exception):
                matchups = None
            
            if not matchups:
                # Try to get league info for better error message
                league = await self.client.get_league(league_id)
                league_name = league.name if league else "Unknown"
                
                return {
                    "error": f"No scoring data found for week {week} in league '{league_name}'",
                    "suggestions": [
                        f"Check if week {week} has started",
                        "Verify the week number is within the current season",
                        "Try a different week number"
                    ]
                }
            
            # Create user mapping (roster_id -> user info)
            user_map = {}
            if not isinstance(users, Exception) and users:
                # First get roster data to map owner_id to roster_id
                try:
                    rosters = await self.client.get_league_rosters(league_id)
                    if rosters:
                        roster_to_owner = {roster.roster_id: roster.owner_id for roster in rosters}
                        user_info_map = {
                            user.user_id: {
                                "username": user.username,
                                "display_name": user.display_name,
                                "avatar": user.avatar,
                                "is_owner": user.is_owner
                            }
                            for user in users
                        }
                        # Map roster_id to user info
                        for roster_id, owner_id in roster_to_owner.items():
                            if owner_id in user_info_map:
                                user_map[roster_id] = user_info_map[owner_id]
                except Exception:
                    pass  # Continue without user mapping if roster fetch fails
            
            # Group by matchup_id and calculate scores
            matchup_scores = []
            matchup_groups: Dict[Optional[int], List[Matchup]] = {}
            
            for matchup in matchups:
                matchup_id = matchup.matchup_id
                if matchup_id not in matchup_groups:
                    matchup_groups[matchup_id] = []
                matchup_groups[matchup_id].append(matchup)
            
            total_points = 0.0
            highest_score = 0.0
            lowest_score = float('inf')
            
            for matchup_id, teams in matchup_groups.items():
                if matchup_id is None:
                    # Bye week
                    for team in teams:
                        total_points += team.points
                        highest_score = max(highest_score, team.points)
                        if team.points > 0:  # Don't count 0 as lowest score
                            lowest_score = min(lowest_score, team.points)
                        
                        user_info = user_map.get(team.roster_id, {
                            "username": None,
                            "display_name": f"User {team.roster_id}",
                            "avatar": None,
                            "is_owner": False
                        })
                        matchup_scores.append({
                            "matchup_id": None,
                            "type": "bye",
                            "roster_id": team.roster_id,
                            "user_info": user_info,
                            "points": team.points,
                            "points_bonus": team.points_bonus or 0.0,
                            "opponent_roster_id": None,
                            "opponent_points": None,
                            "is_winning": None,
                            "point_differential": None
                        })
                else:
                    # Head-to-head matchup
                    if len(teams) == 2:
                        team1, team2 = teams
                        total_points += team1.points + team2.points
                        highest_score = max(highest_score, team1.points, team2.points)
                        if team1.points > 0:
                            lowest_score = min(lowest_score, team1.points)
                        if team2.points > 0:
                            lowest_score = min(lowest_score, team2.points)
                        
                        point_diff = team1.points - team2.points
                        
                        user_info1 = user_map.get(team1.roster_id, {
                            "username": None,
                            "display_name": f"User {team1.roster_id}",
                            "avatar": None,
                            "is_owner": False
                        })
                        user_info2 = user_map.get(team2.roster_id, {
                            "username": None,
                            "display_name": f"User {team2.roster_id}",
                            "avatar": None,
                            "is_owner": False
                        })
                        
                        matchup_scores.extend([
                            {
                                "matchup_id": matchup_id,
                                "type": "head_to_head",
                                "roster_id": team1.roster_id,
                                "user_info": user_info1,
                                "points": team1.points,
                                "points_bonus": team1.points_bonus or 0.0,
                                "opponent_roster_id": team2.roster_id,
                                "opponent_user_info": user_info2,
                                "opponent_points": team2.points,
                                "is_winning": team1.points > team2.points,
                                "point_differential": point_diff
                            },
                            {
                                "matchup_id": matchup_id,
                                "type": "head_to_head",
                                "roster_id": team2.roster_id,
                                "user_info": user_info2,
                                "points": team2.points,
                                "points_bonus": team2.points_bonus or 0.0,
                                "opponent_roster_id": team1.roster_id,
                                "opponent_user_info": user_info1,
                                "opponent_points": team1.points,
                                "is_winning": team2.points > team1.points,
                                "point_differential": -point_diff
                            }
                        ])
                    else:
                        # Handle unusual cases (more than 2 teams in a matchup)
                        for team in teams:
                            total_points += team.points
                            highest_score = max(highest_score, team.points)
                            if team.points > 0:
                                lowest_score = min(lowest_score, team.points)
                            
                            matchup_scores.append({
                                "matchup_id": matchup_id,
                                "type": "multi_team",
                                "roster_id": team.roster_id,
                                "points": team.points,
                                "points_bonus": team.points_bonus or 0.0,
                                "opponent_roster_id": None,
                                "opponent_points": None,
                                "is_winning": None,
                                "point_differential": None
                            })
            
            # Calculate summary statistics
            num_teams = len(matchup_scores)
            average_score = total_points / num_teams if num_teams > 0 else 0.0
            if lowest_score == float('inf'):
                lowest_score = 0.0
            
            result = {
                "league_id": league_id,
                "week": week,
                "scores": matchup_scores,
                "summary": {
                    "total_teams": num_teams,
                    "average_score": round(average_score, 2),
                    "highest_score": highest_score,
                    "lowest_score": lowest_score,
                    "total_points": round(total_points, 2)
                }
            }
            
            # Cache for 5 minutes during active games, 1 hour for completed weeks
            has_active_scoring = any(score["points"] > 0 for score in matchup_scores)
            ttl = 300 if has_active_scoring else 3600
            
            self.cache.set(cache_key, result, CacheDataType.MATCHUP_DATA, ttl_override=ttl)
            
            logger.info(f"Retrieved scores for {num_teams} teams in league {league_id}, week {week}")
            return result
            
        except SleeperAPIError as e:
            logger.error(f"API error getting scores for league {league_id}, week {week}: {e}")
            return {
                "error": f"Failed to retrieve matchup scores: {e}",
                "retry_after": getattr(e, 'retry_after', None)
            }
        except Exception as e:
            logger.error(f"Unexpected error getting scores for league {league_id}, week {week}: {e}")
            return {
                "error": "An unexpected error occurred while retrieving matchup scores",
                "suggestions": ["Try again in a few moments"]
            }