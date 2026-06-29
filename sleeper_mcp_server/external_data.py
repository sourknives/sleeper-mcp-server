"""
External data integration for FantasyPros player rankings.

This module provides web scraping functionality to retrieve consensus player rankings
from FantasyPros public ranking pages, with proper rate limiting and error handling.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from .cache import CacheDataType, get_cache_manager
from .models import PlayerRanking, PlayerRankings

logger = logging.getLogger(__name__)


class FantasyProsScraper:
    """
    Web scraper for FantasyPros consensus player rankings.
    
    Handles scraping of PPR and Half-PPR rankings from public FantasyPros pages
    with proper rate limiting, user-agent headers, and error handling.
    """
    
    BASE_URL = "https://www.fantasypros.com"
    
    # Ranking URLs for different scoring formats
    RANKING_URLS = {
        "ppr": "/nfl/rankings/ros-ppr-overall.php",
        "half_ppr": "/nfl/rankings/ros-half-point-ppr-overall.php"
    }
    
    # User agent to identify as a legitimate browser
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Rate limiting configuration
    MIN_REQUEST_INTERVAL = 2.0  # Minimum seconds between requests
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 30.0
    
    def __init__(self):
        """Initialize the FantasyPros scraper."""
        self._last_request_time = 0.0
        self._cache = get_cache_manager()
        
        # HTTP client configuration
        self._client_config = {
            "timeout": httpx.Timeout(self.TIMEOUT_SECONDS),
            "headers": {
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            "follow_redirects": True
        }
    
    async def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self.MIN_REQUEST_INTERVAL:
            sleep_time = self.MIN_REQUEST_INTERVAL - time_since_last
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    async def _fetch_page(self, url: str) -> str:
        """
        Fetch a web page with proper error handling and retries.
        
        Args:
            url: URL to fetch
            
        Returns:
            HTML content of the page
            
        Raises:
            httpx.HTTPError: If the request fails after all retries
        """
        await self._rate_limit()
        
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(**self._client_config) as client:
                    logger.debug(f"Fetching FantasyPros page: {url} (attempt {attempt + 1})")
                    response = await client.get(url)
                    response.raise_for_status()
                    
                    logger.info(f"Successfully fetched FantasyPros page: {url}")
                    return response.text
                    
            except httpx.HTTPError as e:
                logger.warning(f"HTTP error fetching {url} (attempt {attempt + 1}): {e}")
                if attempt == self.MAX_RETRIES - 1:
                    raise
                
                # Exponential backoff for retries
                sleep_time = 2 ** attempt
                await asyncio.sleep(sleep_time)
    
    def _parse_ranking_table(self, html: str, scoring_format: str) -> List[PlayerRanking]:
        """
        Parse the FantasyPros ranking table from HTML.
        
        Args:
            html: HTML content of the rankings page
            scoring_format: Scoring format ("ppr" or "half_ppr")
            
        Returns:
            List of PlayerRanking objects
            
        Raises:
            ValueError: If the ranking table cannot be parsed
        """
        soup = BeautifulSoup(html, 'html.parser')
        rankings = []
        
        # Find the main ranking table
        table = soup.find('table', {'id': 'ranking-table'})
        if not table:
            # Try alternative table selectors
            table = soup.find('table', class_=re.compile(r'ranking'))
            if not table:
                table = soup.find('div', {'id': 'ranking-table'})
        
        if not table:
            raise ValueError("Could not find ranking table in FantasyPros page")
        
        # Find table body or rows
        tbody = table.find('tbody')
        rows = tbody.find_all('tr') if tbody else table.find_all('tr')
        
        if not rows:
            raise ValueError("No ranking rows found in table")
        
        logger.debug(f"Found {len(rows)} ranking rows to parse")
        
        for row_idx, row in enumerate(rows):
            try:
                ranking = self._parse_ranking_row(row, row_idx + 1, scoring_format)
                if ranking:
                    rankings.append(ranking)
            except Exception as e:
                logger.warning(f"Failed to parse ranking row {row_idx + 1}: {e}")
                continue
        
        if not rankings:
            raise ValueError("No valid rankings could be parsed from the table")
        
        logger.info(f"Successfully parsed {len(rankings)} player rankings")
        return rankings
    
    def _parse_ranking_row(self, row: Tag, rank: int, scoring_format: str) -> Optional[PlayerRanking]:
        """
        Parse a single ranking row from the table.
        
        Args:
            row: BeautifulSoup Tag representing a table row
            rank: Rank number for this row
            scoring_format: Scoring format being parsed
            
        Returns:
            PlayerRanking object or None if parsing fails
        """
        cells = row.find_all(['td', 'th'])
        if len(cells) < 3:  # Need at least rank, player, and some data
            return None
        
        try:
            # Extract player name (usually in second or third column)
            player_name = None
            player_cell = None
            
            for cell in cells[1:4]:  # Check first few columns for player name
                text = cell.get_text(strip=True)
                if text and not text.isdigit() and len(text) > 2:
                    player_name = text
                    player_cell = cell
                    break
            
            if not player_name:
                return None
            
            # Clean up player name (remove team info, position info)
            player_name = self._clean_player_name(player_name)
            
            # Extract projected points (look for numeric values in later columns)
            projected_points = self._extract_projected_points(cells)
            
            # Generate a simple player ID from name (FantasyPros doesn't provide IDs)
            player_id = self._generate_player_id(player_name)
            
            # Determine tier (every 12 players is a new tier, roughly)
            tier = ((rank - 1) // 12) + 1
            
            return PlayerRanking(
                player_id=player_id,
                rank=rank,
                projected_points=projected_points,
                tier=tier,
                fantasypros_rank=rank
            )
            
        except Exception as e:
            logger.debug(f"Error parsing ranking row: {e}")
            return None
    
    def _clean_player_name(self, raw_name: str) -> str:
        """
        Clean up player name by removing team and position information.
        
        Args:
            raw_name: Raw player name from FantasyPros
            
        Returns:
            Cleaned player name
        """
        # Remove common patterns like "Player Name (TEAM - POS)"
        name = re.sub(r'\s*\([^)]*\)\s*$', '', raw_name)
        
        # Remove position abbreviations at the end
        name = re.sub(r'\s+(QB|RB|WR|TE|K|DEF|DST)\s*$', '', name, flags=re.IGNORECASE)
        
        # Remove team abbreviations at the end (2-4 capital letters, but not if it's part of a name)
        # Only remove if it's clearly a team abbreviation (3+ letters or common 2-letter teams)
        name = re.sub(r'\s+(SF|LAC|LAR|MIA|BUF|NE|NYG|NYJ|TB|NO|ATL|CAR|WAS|DAL|PHI|GB|MIN|CHI|DET|SEA|ARI|LAR|LV|DEN|KC|LAC|PIT|CLE|BAL|CIN|TEN|IND|JAX|HOU)\s*$', '', name)
        name = re.sub(r'\s+[A-Z]{3,4}\s*$', '', name)  # 3-4 letter abbreviations
        
        # Clean up extra whitespace
        name = ' '.join(name.split())
        
        return name.strip()
    
    def _extract_projected_points(self, cells: List[Tag]) -> float:
        """
        Extract projected points from table cells.
        
        Args:
            cells: List of table cells
            
        Returns:
            Projected points value
        """
        # Look for numeric values that could be projected points
        for cell in cells[2:]:  # Skip first couple columns (rank, name)
            text = cell.get_text(strip=True)
            
            # Try to find a decimal number that looks like projected points
            match = re.search(r'(\d+\.?\d*)', text)
            if match:
                try:
                    value = float(match.group(1))
                    # Reasonable range for projected points (5-25 per game)
                    if 50 <= value <= 400:  # Season totals
                        return value
                    elif 5 <= value <= 25:  # Per game averages
                        return value * 17  # Convert to season total
                except ValueError:
                    continue
        
        # Default fallback based on rank (try to extract rank safely)
        try:
            rank_text = cells[0].get_text(strip=True) if cells else "1"
            # Extract just the numeric part for rank
            rank_match = re.search(r'(\d+)', rank_text)
            rank = int(rank_match.group(1)) if rank_match else 1
            return max(200 - (rank * 2), 50)
        except (ValueError, IndexError):
            return 150.0  # Safe fallback
    
    def _generate_player_id(self, player_name: str) -> str:
        """
        Generate a consistent player ID from player name.
        
        Args:
            player_name: Player's name
            
        Returns:
            Generated player ID
        """
        # Create a simple ID from name (lowercase, no spaces, no special chars)
        player_id = re.sub(r'[^a-zA-Z0-9]', '', player_name.lower())
        return f"fp_{player_id}"
    
    async def get_player_rankings(
        self, 
        scoring_format: str, 
        position: Optional[str] = None,
        use_cache: bool = True
    ) -> PlayerRankings:
        """
        Get current player rankings from FantasyPros.
        
        Args:
            scoring_format: Scoring format ("ppr" or "half_ppr")
            position: Optional position filter (not implemented for FantasyPros)
            use_cache: Whether to use cached data if available
            
        Returns:
            PlayerRankings object with current rankings
            
        Raises:
            ValueError: If scoring format is not supported
            httpx.HTTPError: If the request fails
        """
        if scoring_format not in self.RANKING_URLS:
            raise ValueError(f"Unsupported scoring format: {scoring_format}. Must be 'ppr' or 'half_ppr'")
        
        # Check cache first
        cache_key = f"fantasypros_rankings_{scoring_format}_{position or 'all'}"
        if use_cache:
            cached_rankings = self._cache.get_fantasypros_data(cache_key)
            if cached_rankings:
                logger.debug(f"Using cached FantasyPros rankings for {scoring_format}")
                return cached_rankings
        
        try:
            # Fetch and parse rankings
            url = urljoin(self.BASE_URL, self.RANKING_URLS[scoring_format])
            html = await self._fetch_page(url)
            
            rankings_list = self._parse_ranking_table(html, scoring_format)
            
            # Filter by position if specified
            if position:
                # Note: FantasyPros doesn't provide position info in the basic scraping
                # This would require more sophisticated parsing or different endpoints
                logger.warning(f"Position filtering ({position}) not implemented for FantasyPros scraping")
            
            rankings = PlayerRankings(
                rankings=rankings_list,
                last_updated=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                scoring_format=scoring_format
            )
            
            # Cache the results using FantasyPros-specific caching
            self._cache.set_fantasypros_data(cache_key, rankings)
            
            logger.info(f"Retrieved {len(rankings_list)} FantasyPros rankings for {scoring_format}")
            return rankings
            
        except Exception as e:
            logger.error(f"Failed to get FantasyPros rankings for {scoring_format}: {e}")
            
            # Try to return cached data even if expired
            if use_cache:
                cached_rankings = self._cache.get_stale_fantasypros_data(cache_key)
                if cached_rankings:
                    logger.warning("Using expired cached FantasyPros rankings due to fetch failure")
                    return cached_rankings
            
            raise
    
    async def warm_cache(self, scoring_formats: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Pre-warm cache with FantasyPros data for specified scoring formats.
        
        Args:
            scoring_formats: List of scoring formats to warm. Defaults to ["ppr", "half_ppr"]
            
        Returns:
            Dictionary mapping scoring format to success status
        """
        if scoring_formats is None:
            scoring_formats = ["ppr", "half_ppr"]
        
        results = {}
        
        for scoring_format in scoring_formats:
            try:
                logger.info(f"Warming cache for FantasyPros {scoring_format} rankings")
                rankings = await self.get_player_rankings(scoring_format, use_cache=False)
                results[scoring_format] = True
                logger.info(f"Successfully warmed cache for {scoring_format} with {len(rankings.rankings)} rankings")
                
            except Exception as e:
                logger.error(f"Failed to warm cache for FantasyPros {scoring_format}: {e}")
                results[scoring_format] = False
        
        return results
    
    def invalidate_stale_data(self, max_age_hours: float = 12.0) -> int:
        """
        Invalidate stale FantasyPros data from cache.
        
        Args:
            max_age_hours: Maximum age in hours before data is considered stale
            
        Returns:
            Number of entries invalidated
        """
        return self._cache.invalidate_stale_fantasypros_data(max_age_hours)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get FantasyPros-specific cache statistics.
        
        Returns:
            Dictionary containing cache statistics
        """
        return self._cache.get_fantasypros_cache_stats()
    
    def log_cache_performance(self) -> None:
        """Log FantasyPros cache performance statistics."""
        self._cache.log_fantasypros_performance()
    
    def validate_ranking_data(self, rankings: PlayerRankings) -> Tuple[bool, List[str]]:
        """
        Validate scraped ranking data for consistency and completeness.
        
        Args:
            rankings: PlayerRankings object to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        if not rankings.rankings:
            issues.append("No rankings data found")
            return False, issues
        
        if len(rankings.rankings) < 50:
            issues.append(f"Too few rankings found: {len(rankings.rankings)} (expected 100+)")
        
        # Check for reasonable projected points
        total_points = sum(r.projected_points for r in rankings.rankings)
        avg_points = total_points / len(rankings.rankings)
        
        if avg_points < 50 or avg_points > 300:
            issues.append(f"Unrealistic average projected points: {avg_points:.1f}")
        
        # Check for duplicate ranks
        ranks = [r.rank for r in rankings.rankings]
        if len(set(ranks)) != len(ranks):
            issues.append("Duplicate ranks found in rankings")
        
        # Check for reasonable rank progression
        sorted_ranks = sorted(ranks)
        if sorted_ranks != list(range(1, len(sorted_ranks) + 1)):
            issues.append("Non-sequential ranking numbers")
        
        # Check scoring format
        if rankings.scoring_format not in ["ppr", "half_ppr"]:
            issues.append(f"Invalid scoring format: {rankings.scoring_format}")
        
        is_valid = len(issues) == 0
        
        if issues:
            logger.warning(f"Ranking validation issues: {issues}")
        else:
            logger.debug("Ranking data validation passed")
        
        return is_valid, issues


# Global scraper instance
_scraper: Optional[FantasyProsScraper] = None


def get_fantasypros_scraper() -> FantasyProsScraper:
    """
    Get the global FantasyPros scraper instance.
    
    Returns:
        Global FantasyProsScraper instance
    """
    global _scraper
    if _scraper is None:
        _scraper = FantasyProsScraper()
    return _scraper


async def get_current_player_rankings(
    scoring_format: str,
    position: Optional[str] = None,
    use_cache: bool = True
) -> PlayerRankings:
    """
    Convenience function to get current player rankings.
    
    Args:
        scoring_format: Scoring format ("ppr" or "half_ppr")
        position: Optional position filter
        use_cache: Whether to use cached data
        
    Returns:
        PlayerRankings object
    """
    scraper = get_fantasypros_scraper()
    return await scraper.get_player_rankings(scoring_format, position, use_cache)


async def warm_fantasypros_cache(scoring_formats: Optional[List[str]] = None) -> Dict[str, bool]:
    """
    Convenience function to warm FantasyPros cache.
    
    Args:
        scoring_formats: List of scoring formats to warm. Defaults to ["ppr", "half_ppr"]
        
    Returns:
        Dictionary mapping scoring format to success status
    """
    scraper = get_fantasypros_scraper()
    return await scraper.warm_cache(scoring_formats)


def invalidate_stale_fantasypros_data(max_age_hours: float = 12.0) -> int:
    """
    Convenience function to invalidate stale FantasyPros data.
    
    Args:
        max_age_hours: Maximum age in hours before data is considered stale
        
    Returns:
        Number of entries invalidated
    """
    scraper = get_fantasypros_scraper()
    return scraper.invalidate_stale_data(max_age_hours)


def get_fantasypros_cache_stats() -> Dict[str, Any]:
    """
    Convenience function to get FantasyPros cache statistics.
    
    Returns:
        Dictionary containing cache statistics
    """
    scraper = get_fantasypros_scraper()
    return scraper.get_cache_stats()


def log_fantasypros_cache_performance() -> None:
    """Convenience function to log FantasyPros cache performance."""
    scraper = get_fantasypros_scraper()
    scraper.log_cache_performance()