"""
Sleeper API client with rate limiting and error handling.

This module provides a comprehensive HTTP client for interacting with the Sleeper
Fantasy Football API, including rate limiting, retry logic, and proper error handling.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import httpx
from pydantic import ValidationError

from .models import (
    League,
    User,
    Player,
    TrendingPlayer,
    PlayerStats,
    Roster,
    Matchup,
    ErrorResponse,
)


logger = logging.getLogger(__name__)


class SleeperAPIError(Exception):
    """Base exception for Sleeper API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, retry_after: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class RateLimitError(SleeperAPIError):
    """Exception raised when rate limit is exceeded."""
    pass


class SleeperClient:
    """
    HTTP client for Sleeper Fantasy Football API with rate limiting and error handling.
    
    This client implements:
    - Rate limiting with exponential backoff
    - Automatic retries for transient failures
    - Proper timeout and error handling
    - Typed responses using Pydantic models
    """
    
    def __init__(
        self,
        base_url: str = "https://api.sleeper.app/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        rate_limit_delay: float = 1.0,
        max_rate_limit_delay: float = 60.0,
    ):
        """
        Initialize the Sleeper API client.
        
        Args:
            base_url: Base URL for Sleeper API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            rate_limit_delay: Initial delay for rate limiting (seconds)
            max_rate_limit_delay: Maximum delay for rate limiting (seconds)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay
        self.max_rate_limit_delay = max_rate_limit_delay
        
        # Rate limiting state
        self._last_request_time = 0.0
        self._request_count = 0
        self._rate_limit_reset_time = 0.0
        
        # HTTP client configuration
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={
                "User-Agent": "sleeper-mcp-server/0.1.0",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        
        # Reset rate limit counter if enough time has passed
        if current_time >= self._rate_limit_reset_time:
            self._request_count = 0
            self._rate_limit_reset_time = current_time + 60  # Reset every minute
        
        # Simple rate limiting: max 60 requests per minute
        if self._request_count >= 60:
            wait_time = self._rate_limit_reset_time - current_time
            if wait_time > 0:
                logger.info(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
                self._request_count = 0
                self._rate_limit_reset_time = time.time() + 60
        
        # Ensure minimum delay between requests
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.rate_limit_delay:
            wait_time = self.rate_limit_delay - time_since_last
            await asyncio.sleep(wait_time)
        
        self._last_request_time = time.time()
        self._request_count += 1
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with retry logic and error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body
            
        Returns:
            Parsed JSON response
            
        Raises:
            SleeperAPIError: For API-related errors
            RateLimitError: When rate limit is exceeded
        """
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        retry_count = 0
        last_exception = None
        
        while retry_count <= self.max_retries:
            try:
                await self._wait_for_rate_limit()
                
                logger.debug(f"Making {method} request to {url}")
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                )
                
                # Handle successful responses
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as e:
                        raise SleeperAPIError(f"Invalid JSON response: {e}")
                
                # Handle rate limiting
                elif response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 60))
                    retry_after = min(retry_after, self.max_rate_limit_delay)
                    
                    if retry_count < self.max_retries:
                        logger.warning(f"Rate limited, waiting {retry_after} seconds before retry {retry_count + 1}")
                        await asyncio.sleep(retry_after)
                        retry_count += 1
                        continue
                    else:
                        raise RateLimitError(
                            "Rate limit exceeded and max retries reached",
                            status_code=429,
                            retry_after=retry_after
                        )
                
                # Handle client errors (4xx)
                elif 400 <= response.status_code < 500:
                    error_msg = f"Client error {response.status_code}"
                    try:
                        error_data = response.json()
                        if isinstance(error_data, dict) and "error" in error_data:
                            error_msg = error_data["error"]
                    except ValueError:
                        error_msg = response.text or error_msg
                    
                    raise SleeperAPIError(error_msg, status_code=response.status_code)
                
                # Handle server errors (5xx) - retry these
                elif response.status_code >= 500:
                    if retry_count < self.max_retries:
                        delay = min(2 ** retry_count, 30)  # Exponential backoff, max 30s
                        logger.warning(f"Server error {response.status_code}, retrying in {delay} seconds")
                        await asyncio.sleep(delay)
                        retry_count += 1
                        continue
                    else:
                        raise SleeperAPIError(
                            f"Server error {response.status_code} after {self.max_retries} retries",
                            status_code=response.status_code
                        )
                
                else:
                    raise SleeperAPIError(f"Unexpected status code: {response.status_code}")
                    
            except httpx.TimeoutException as e:
                last_exception = e
                if retry_count < self.max_retries:
                    delay = min(2 ** retry_count, 30)
                    logger.warning(f"Request timeout, retrying in {delay} seconds")
                    await asyncio.sleep(delay)
                    retry_count += 1
                    continue
                else:
                    raise SleeperAPIError(f"Request timeout after {self.max_retries} retries")
            
            except httpx.RequestError as e:
                last_exception = e
                if retry_count < self.max_retries:
                    delay = min(2 ** retry_count, 30)
                    logger.warning(f"Request error: {e}, retrying in {delay} seconds")
                    await asyncio.sleep(delay)
                    retry_count += 1
                    continue
                else:
                    raise SleeperAPIError(f"Request failed after {self.max_retries} retries: {e}")
        
        # This should not be reached, but just in case
        if last_exception:
            raise SleeperAPIError(f"Request failed: {last_exception}")
        raise SleeperAPIError("Request failed for unknown reason")
    
    # User and League endpoints
    
    async def get_user(self, username: str) -> Optional[User]:
        """
        Get user information by username.
        
        Args:
            username: Sleeper username
            
        Returns:
            User model or None if not found
        """
        try:
            data = await self._make_request("GET", f"/user/{username}")
            if data is None:
                return None
            return User.model_validate(data)
        except SleeperAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    async def get_user_leagues(self, user_id: str, season: str) -> List[League]:
        """
        Get all leagues for a user in a specific season.
        
        Args:
            user_id: User ID
            season: Season year (e.g., "2023")
            
        Returns:
            List of League models
        """
        data = await self._make_request("GET", f"/user/{user_id}/leagues/nfl/{season}")
        if not data:
            return []
        
        leagues = []
        for league_data in data:
            try:
                leagues.append(League.model_validate(league_data))
            except ValidationError as e:
                logger.warning(f"Failed to validate league data: {e}")
                continue
        
        return leagues
    
    async def get_league(self, league_id: str) -> Optional[League]:
        """
        Get league information by ID.
        
        Args:
            league_id: League ID
            
        Returns:
            League model or None if not found
        """
        try:
            data = await self._make_request("GET", f"/league/{league_id}")
            if data is None:
                return None
            return League.model_validate(data)
        except SleeperAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    async def get_league_users(self, league_id: str) -> List[User]:
        """
        Get all users in a league.
        
        Args:
            league_id: League ID
            
        Returns:
            List of User models
        """
        data = await self._make_request("GET", f"/league/{league_id}/users")
        if not data:
            return []
        
        users = []
        for user_data in data:
            try:
                users.append(User.model_validate(user_data))
            except ValidationError as e:
                logger.warning(f"Failed to validate user data: {e}")
                continue
        
        return users
    
    async def get_league_rosters(self, league_id: str) -> List[Roster]:
        """
        Get all rosters in a league.
        
        Args:
            league_id: League ID
            
        Returns:
            List of Roster models
        """
        data = await self._make_request("GET", f"/league/{league_id}/rosters")
        if not data:
            return []
        
        rosters = []
        for roster_data in data:
            try:
                rosters.append(Roster.model_validate(roster_data))
            except ValidationError as e:
                logger.warning(f"Failed to validate roster data: {e}")
                continue
        
        return rosters
    
    # Player endpoints
    
    async def get_players(self, sport: str = "nfl") -> Dict[str, Player]:
        """
        Get all players for a sport.
        
        Args:
            sport: Sport type (default: "nfl")
            
        Returns:
            Dictionary mapping player IDs to Player models
        """
        data = await self._make_request("GET", f"/players/{sport}")
        if not data:
            return {}
        
        players = {}
        for player_id, player_data in data.items():
            try:
                players[player_id] = Player.model_validate(player_data)
            except ValidationError as e:
                logger.warning(f"Failed to validate player {player_id}: {e}")
                continue
        
        return players
    
    async def get_trending_players(
        self, 
        sport: str, 
        add_drop: str, 
        hours: int = 24,
        limit: int = 25
    ) -> List[TrendingPlayer]:
        """
        Get trending players (most added/dropped).
        
        Args:
            sport: Sport type (e.g., "nfl")
            add_drop: "add" or "drop"
            hours: Hours to look back (default: 24)
            limit: Maximum number of results (default: 25)
            
        Returns:
            List of TrendingPlayer models
        """
        params = {
            "lookback_hours": hours,
            "limit": limit,
        }
        
        data = await self._make_request("GET", f"/players/{sport}/trending/{add_drop}", params=params)
        if not data:
            return []
        
        trending = []
        for trend_data in data:
            try:
                trending.append(TrendingPlayer.model_validate(trend_data))
            except ValidationError as e:
                logger.warning(f"Failed to validate trending player data: {e}")
                continue
        
        return trending
    
    async def get_player_stats(
        self, 
        sport: str, 
        season: str, 
        season_type: str = "regular",
        week: Optional[int] = None
    ) -> Dict[str, PlayerStats]:
        """
        Get player statistics for a season/week.
        
        Args:
            sport: Sport type (e.g., "nfl")
            season: Season year (e.g., "2023")
            season_type: "regular" or "post" (default: "regular")
            week: Specific week number (optional)
            
        Returns:
            Dictionary mapping player IDs to PlayerStats models
        """
        endpoint = f"/stats/{sport}/{season_type}"
        if week is not None:
            endpoint += f"/{week}"
        
        data = await self._make_request("GET", endpoint)
        if not data:
            return {}
        
        stats = {}
        for player_id, stats_data in data.items():
            try:
                stats_model = PlayerStats(
                    player_id=player_id,
                    season=season,
                    season_type=season_type,
                    week=week,
                    stats=stats_data
                )
                stats[player_id] = stats_model
            except ValidationError as e:
                logger.warning(f"Failed to validate stats for player {player_id}: {e}")
                continue
        
        return stats
    
    # Matchup endpoints
    
    async def get_matchups(self, league_id: str, week: int) -> List[Matchup]:
        """
        Get matchups for a specific week.
        
        Args:
            league_id: League ID
            week: Week number
            
        Returns:
            List of Matchup models
        """
        data = await self._make_request("GET", f"/league/{league_id}/matchups/{week}")
        if not data:
            return []
        
        matchups = []
        for matchup_data in data:
            try:
                matchups.append(Matchup.model_validate(matchup_data))
            except ValidationError as e:
                logger.warning(f"Failed to validate matchup data: {e}")
                continue
        
        return matchups
    
    async def get_winners_bracket(self, league_id: str) -> List[Matchup]:
        """
        Get winners bracket playoff matchups.
        
        Args:
            league_id: League ID
            
        Returns:
            List of Matchup models
        """
        data = await self._make_request("GET", f"/league/{league_id}/winners_bracket")
        if not data:
            return []
        
        matchups = []
        for matchup_data in data:
            try:
                matchups.append(Matchup.model_validate(matchup_data))
            except ValidationError as e:
                logger.warning(f"Failed to validate bracket matchup data: {e}")
                continue
        
        return matchups
    
    async def get_losers_bracket(self, league_id: str) -> List[Matchup]:
        """
        Get losers bracket playoff matchups.
        
        Args:
            league_id: League ID
            
        Returns:
            List of Matchup models
        """
        data = await self._make_request("GET", f"/league/{league_id}/losers_bracket")
        if not data:
            return []
        
        matchups = []
        for matchup_data in data:
            try:
                matchups.append(Matchup.model_validate(matchup_data))
            except ValidationError as e:
                logger.warning(f"Failed to validate bracket matchup data: {e}")
                continue
        
        return matchups
    
    # Draft endpoints (for future use)
    
    async def get_drafts_for_user(self, user_id: str, sport: str, season: str) -> List[Dict[str, Any]]:
        """
        Get drafts for a user in a specific season.
        
        Args:
            user_id: User ID
            sport: Sport type (e.g., "nfl")
            season: Season year
            
        Returns:
            List of draft data dictionaries
        """
        data = await self._make_request("GET", f"/user/{user_id}/drafts/{sport}/{season}")
        return data or []
    
    async def get_draft(self, draft_id: str) -> Optional[Dict[str, Any]]:
        """
        Get draft information by ID.
        
        Args:
            draft_id: Draft ID
            
        Returns:
            Draft data dictionary or None if not found
        """
        try:
            data = await self._make_request("GET", f"/draft/{draft_id}")
            return data
        except SleeperAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    async def get_draft_picks(self, draft_id: str) -> List[Dict[str, Any]]:
        """
        Get draft picks for a specific draft.
        
        Args:
            draft_id: Draft ID
            
        Returns:
            List of draft pick data dictionaries
        """
        try:
            data = await self._make_request("GET", f"/draft/{draft_id}/picks")
            return data or []
        except SleeperAPIError as e:
            if e.status_code == 404:
                return []
            raise
    
    # Utility methods
    
    async def search_players_by_name(
        self, 
        name: str, 
        sport: str = "nfl",
        position: Optional[str] = None
    ) -> List[Player]:
        """
        Search for players by name (client-side filtering).
        
        Args:
            name: Player name to search for
            sport: Sport type (default: "nfl")
            position: Optional position filter
            
        Returns:
            List of matching Player models
        """
        # Get all players and filter client-side
        # Note: Sleeper doesn't have a search endpoint, so we need to get all players
        all_players = await self.get_players(sport)
        
        name_lower = name.lower()
        matches = []
        
        for player in all_players.values():
            # Check if name matches
            if (name_lower in player.full_name.lower() or 
                (player.first_name and name_lower in player.first_name.lower()) or
                (player.last_name and name_lower in player.last_name.lower())):
                
                # Apply position filter if specified
                if position is None or player.position == position.upper():
                    matches.append(player)
        
        # Sort by relevance (exact matches first, then partial matches)
        def sort_key(player: Player) -> tuple:
            full_name_lower = player.full_name.lower()
            if full_name_lower == name_lower:
                return (0, player.full_name)  # Exact match
            elif full_name_lower.startswith(name_lower):
                return (1, player.full_name)  # Starts with
            else:
                return (2, player.full_name)  # Contains
        
        matches.sort(key=sort_key)
        return matches[:50]  # Limit results
    
    async def health_check(self) -> bool:
        """
        Check if the Sleeper API is accessible.
        
        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Try to get NFL players as a health check
            await self._make_request("GET", "/players/nfl", params={"limit": 1})
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False