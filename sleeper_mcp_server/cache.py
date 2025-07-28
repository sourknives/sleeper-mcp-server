"""
Cache manager with TTL-based expiration for different data types.

This module provides a comprehensive caching system for the Sleeper MCP server,
with configurable TTL values for different data types and cache hit/miss logging
for performance monitoring.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, TypeVar, Generic
from threading import Lock
from dataclasses import dataclass
from enum import Enum

T = TypeVar('T')

logger = logging.getLogger(__name__)


class CacheDataType(str, Enum):
    """Enum for different types of cached data with their default TTL values."""
    PLAYER_DATA = "player_data"  # 1 hour TTL
    LEAGUE_SETTINGS = "league_settings"  # 24 hours TTL
    MATCHUP_DATA = "matchup_data"  # 5 minutes TTL during games, 1 hour otherwise
    TRENDING_PLAYERS = "trending_players"  # 30 minutes TTL
    ROSTER_DATA = "roster_data"  # 15 minutes TTL


@dataclass
class CacheEntry(Generic[T]):
    """Represents a single cache entry with data and expiration time."""
    data: T
    expires_at: float
    created_at: float
    data_type: CacheDataType
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return time.time() > self.expires_at
    
    def age_seconds(self) -> float:
        """Get the age of the cache entry in seconds."""
        return time.time() - self.created_at


class CacheManager:
    """
    Thread-safe cache manager with TTL-based expiration for different data types.
    
    Provides caching functionality with configurable TTL values, cache invalidation
    strategies, and performance monitoring through hit/miss logging.
    """
    
    # Default TTL values in seconds for different data types
    DEFAULT_TTL_CONFIG = {
        CacheDataType.PLAYER_DATA: 3600,  # 1 hour
        CacheDataType.LEAGUE_SETTINGS: 86400,  # 24 hours
        CacheDataType.MATCHUP_DATA: 3600,  # 1 hour (default, can be overridden)
        CacheDataType.TRENDING_PLAYERS: 1800,  # 30 minutes
        CacheDataType.ROSTER_DATA: 900,  # 15 minutes
    }
    
    def __init__(self, ttl_config: Optional[Dict[CacheDataType, int]] = None):
        """
        Initialize the cache manager.
        
        Args:
            ttl_config: Optional custom TTL configuration for data types
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._ttl_config = {**self.DEFAULT_TTL_CONFIG}
        if ttl_config:
            self._ttl_config.update(ttl_config)
        
        # Performance monitoring counters
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'invalidations': 0
        }
        
        logger.info(f"Cache manager initialized with TTL config: {self._ttl_config}")
    
    def get(self, key: str, data_type: CacheDataType) -> Optional[Any]:
        """
        Retrieve data from cache if it exists and hasn't expired.
        
        Args:
            key: Cache key
            data_type: Type of data being cached
            
        Returns:
            Cached data if available and not expired, None otherwise
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats['misses'] += 1
                logger.debug(f"Cache miss for key: {key} (type: {data_type})")
                return None
            
            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                self._stats['evictions'] += 1
                self._stats['misses'] += 1
                logger.debug(f"Cache expired for key: {key} (type: {data_type}, age: {entry.age_seconds():.1f}s)")
                return None
            
            self._stats['hits'] += 1
            logger.debug(f"Cache hit for key: {key} (type: {data_type}, age: {entry.age_seconds():.1f}s)")
            return entry.data
    
    def set(self, key: str, data: Any, data_type: CacheDataType, ttl_override: Optional[int] = None) -> None:
        """
        Store data in cache with TTL-based expiration.
        
        Args:
            key: Cache key
            data: Data to cache
            data_type: Type of data being cached
            ttl_override: Optional TTL override in seconds
        """
        ttl = ttl_override if ttl_override is not None else self._ttl_config[data_type]
        current_time = time.time()
        expires_at = current_time + ttl
        
        entry = CacheEntry(
            data=data,
            expires_at=expires_at,
            created_at=current_time,
            data_type=data_type
        )
        
        with self._lock:
            self._cache[key] = entry
        
        logger.debug(f"Cached data for key: {key} (type: {data_type}, TTL: {ttl}s)")
    
    def invalidate(self, key: str) -> bool:
        """
        Remove a specific key from cache.
        
        Args:
            key: Cache key to invalidate
            
        Returns:
            True if key was found and removed, False otherwise
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats['invalidations'] += 1
                logger.debug(f"Invalidated cache key: {key}")
                return True
            return False
    
    def invalidate_by_pattern(self, pattern: str) -> int:
        """
        Remove all keys matching a pattern from cache.
        
        Args:
            pattern: Pattern to match (simple string contains matching)
            
        Returns:
            Number of keys invalidated
        """
        keys_to_remove = []
        
        with self._lock:
            for key in self._cache.keys():
                if pattern in key:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._cache[key]
                self._stats['invalidations'] += 1
        
        if keys_to_remove:
            logger.debug(f"Invalidated {len(keys_to_remove)} cache keys matching pattern: {pattern}")
        
        return len(keys_to_remove)
    
    def invalidate_by_type(self, data_type: CacheDataType) -> int:
        """
        Remove all entries of a specific data type from cache.
        
        Args:
            data_type: Type of data to invalidate
            
        Returns:
            Number of entries invalidated
        """
        keys_to_remove = []
        
        with self._lock:
            for key, entry in self._cache.items():
                if entry.data_type == data_type:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._cache[key]
                self._stats['invalidations'] += 1
        
        if keys_to_remove:
            logger.debug(f"Invalidated {len(keys_to_remove)} cache entries of type: {data_type}")
        
        return len(keys_to_remove)
    
    def clear(self) -> int:
        """
        Clear all entries from cache.
        
        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats['invalidations'] += count
        
        logger.info(f"Cleared all cache entries ({count} entries)")
        return count
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from cache.
        
        Returns:
            Number of expired entries removed
        """
        current_time = time.time()
        keys_to_remove = []
        
        with self._lock:
            for key, entry in self._cache.items():
                if entry.expires_at <= current_time:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._cache[key]
                self._stats['evictions'] += 1
        
        if keys_to_remove:
            logger.debug(f"Cleaned up {len(keys_to_remove)} expired cache entries")
        
        return len(keys_to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics.
        
        Returns:
            Dictionary containing cache statistics
        """
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate_percent': round(hit_rate, 2),
                'evictions': self._stats['evictions'],
                'invalidations': self._stats['invalidations'],
                'total_entries': len(self._cache),
                'total_requests': total_requests
            }
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get detailed information about cache contents.
        
        Returns:
            Dictionary containing cache information
        """
        current_time = time.time()
        info = {
            'total_entries': 0,
            'expired_entries': 0,
            'entries_by_type': {},
            'oldest_entry_age': 0,
            'newest_entry_age': 0
        }
        
        with self._lock:
            if not self._cache:
                return info
            
            ages = []
            for entry in self._cache.values():
                age = current_time - entry.created_at
                ages.append(age)
                
                # Count by type
                type_name = entry.data_type.value
                if type_name not in info['entries_by_type']:
                    info['entries_by_type'][type_name] = {'count': 0, 'expired': 0}
                
                info['entries_by_type'][type_name]['count'] += 1
                
                if entry.is_expired():
                    info['expired_entries'] += 1
                    info['entries_by_type'][type_name]['expired'] += 1
            
            info['total_entries'] = len(self._cache)
            if ages:
                info['oldest_entry_age'] = max(ages)
                info['newest_entry_age'] = min(ages)
        
        return info
    
    def get_matchup_ttl(self, is_game_time: bool = False) -> int:
        """
        Get TTL for matchup data based on whether games are currently active.
        
        Args:
            is_game_time: Whether games are currently being played
            
        Returns:
            TTL in seconds (5 minutes during games, 1 hour otherwise)
        """
        return 300 if is_game_time else 3600  # 5 minutes vs 1 hour
    
    def log_performance_summary(self) -> None:
        """Log a summary of cache performance statistics."""
        stats = self.get_stats()
        info = self.get_cache_info()
        
        logger.info(
            f"Cache Performance Summary - "
            f"Hit Rate: {stats['hit_rate_percent']}% "
            f"({stats['hits']}/{stats['total_requests']} requests), "
            f"Entries: {info['total_entries']} "
            f"(Expired: {info['expired_entries']}), "
            f"Evictions: {stats['evictions']}, "
            f"Invalidations: {stats['invalidations']}"
        )


# Global cache instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """
    Get the global cache manager instance.
    
    Returns:
        Global CacheManager instance
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def initialize_cache(ttl_config: Optional[Dict[CacheDataType, int]] = None) -> CacheManager:
    """
    Initialize the global cache manager with custom configuration.
    
    Args:
        ttl_config: Optional custom TTL configuration
        
    Returns:
        Initialized CacheManager instance
    """
    global _cache_manager
    _cache_manager = CacheManager(ttl_config)
    return _cache_manager