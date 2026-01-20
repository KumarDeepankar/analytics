"""
Permission Cache with TTL and LRU Eviction

In-memory cache for user permissions. Invalidated on role/permission changes.
TTL provides fallback expiry (5 minutes default).
"""

import time
import threading
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


class PermissionCache:
    """Thread-safe permission cache with TTL and LRU eviction."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 50000):
        self._cache: Dict[str, Dict[str, Any]] = {}
        # Timestamps: {user_id: (created_at, accessed_at)}
        self._times: Dict[str, Tuple[float, float]] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.RLock()

        # Stats
        self._hits = 0
        self._misses = 0
        self._invalidations = 0

        logger.info(f"PermissionCache initialized: ttl={ttl_seconds}s, max={max_entries}")

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached permissions. Returns None if not cached or expired."""
        with self._lock:
            if user_id not in self._cache:
                self._misses += 1
                return None

            created_at, _ = self._times[user_id]
            age = time.time() - created_at

            if age > self._ttl:
                del self._cache[user_id]
                del self._times[user_id]
                self._misses += 1
                return None

            # Update access time for LRU
            self._times[user_id] = (created_at, time.time())
            self._hits += 1
            return self._cache[user_id]

    def set(self, user_id: str, data: Dict[str, Any]) -> None:
        """Cache permission data for user."""
        with self._lock:
            if len(self._cache) >= self._max_entries and user_id not in self._cache:
                self._evict_lru()

            now = time.time()
            self._cache[user_id] = data
            self._times[user_id] = (now, now)

    def _evict_lru(self) -> None:
        """Evict least recently accessed entry."""
        if not self._times:
            return
        # Find user with oldest access time
        lru_user = min(self._times, key=lambda u: self._times[u][1])
        del self._cache[lru_user]
        del self._times[lru_user]

    def invalidate_user(self, user_id: str) -> None:
        """Invalidate cache for specific user."""
        with self._lock:
            if user_id in self._cache:
                del self._cache[user_id]
                del self._times[user_id]
                self._invalidations += 1

    def invalidate_users(self, user_ids: List[str]) -> None:
        """Invalidate cache for multiple users."""
        with self._lock:
            for user_id in user_ids:
                if user_id in self._cache:
                    del self._cache[user_id]
                    del self._times[user_id]
                    self._invalidations += 1

    def invalidate_by_role(self, role_id: str, get_users_func) -> None:
        """Invalidate cache for all users with a role."""
        try:
            user_ids = get_users_func(role_id)
            self.invalidate_users(user_ids)
            logger.info(f"Cache invalidated for role {role_id}: {len(user_ids)} users")
        except Exception as e:
            logger.warning(f"Failed to get users for role {role_id}, invalidating all: {e}")
            self.invalidate_all()

    def invalidate_all(self) -> None:
        """Clear entire cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._times.clear()
            self._invalidations += count
            logger.info(f"Cache invalidated: {count} entries cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total * 100, 2) if total else 0,
                "invalidations": self._invalidations
            }


# Global singleton
permission_cache = PermissionCache(ttl_seconds=300, max_entries=50000)
