"""In-process TTL cache for Sleeper API responses.

Callers state a TTL directly. The named constants below carry the intent
that used to live in a data-type-to-TTL table.
"""

import logging
import time
from typing import Any, Dict, Generic, Optional, TypeVar
from threading import Lock
from dataclasses import dataclass

T = TypeVar('T')

logger = logging.getLogger(__name__)


# TTLs in seconds. Several share a value; the names carry the intent.
LEAGUE_SETTINGS_TTL = 86400  # league info, draft results - effectively static
LEAGUE_LIST_TTL = 3600  # a user's leagues, a league's users
ROSTER_TTL = 900  # rosters change on waivers and trades
PLAYER_TTL = 3600  # player search, player stats
TRENDING_TTL = 1800  # trending adds/drops move fast
MATCHUP_LIVE_TTL = 300  # games in progress
MATCHUP_FINAL_TTL = 3600  # completed week


@dataclass
class CacheEntry(Generic[T]):
    """Represents a single cache entry with data and expiration time."""
    data: T
    expires_at: float
    created_at: float

    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return time.time() > self.expires_at

    def age_seconds(self) -> float:
        """Get the age of the cache entry in seconds."""
        return time.time() - self.created_at


class CacheManager:
    """Thread-safe TTL cache.

    Entries expire on read; there is no background eviction. Nothing in this
    server writes to Sleeper, so expiry is the only invalidation mechanism.
    """

    def __init__(self) -> None:
        """Initialize an empty cache."""
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve data from cache if it exists and hasn't expired.

        Args:
            key: Cache key

        Returns:
            Cached data if available and not expired, None otherwise
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                logger.debug(f"Cache miss for key: {key}")
                return None

            if entry.is_expired():
                del self._cache[key]
                logger.debug(f"Cache expired for key: {key} (age: {entry.age_seconds():.1f}s)")
                return None

            logger.debug(f"Cache hit for key: {key} (age: {entry.age_seconds():.1f}s)")
            return entry.data

    def set(self, key: str, data: Any, ttl: int) -> None:
        """
        Store data in cache with TTL-based expiration.

        Args:
            key: Cache key
            data: Data to cache
            ttl: Seconds until the entry expires
        """
        current_time = time.time()
        entry = CacheEntry(
            data=data,
            expires_at=current_time + ttl,
            created_at=current_time,
        )

        with self._lock:
            self._cache[key] = entry

        logger.debug(f"Cached data for key: {key} (TTL: {ttl}s)")
