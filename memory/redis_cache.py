"""
Redis Cache Layer
=================

Session-based caching for working memory (24h TTL).
Used for hot data during agent execution.
"""

import os
import json
import hashlib
from typing import Optional, Any, Dict
import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


class RedisCache:
    """
    Async Redis cache for working memory.

    Features:
    - TTL-based expiration (default 24h)
    - JSON serialization
    - Connection pooling
    - Health checks
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        default_ttl: int = 86400,  # 24 hours
        enabled: bool = True
    ):
        """
        Initialize Redis cache.

        Args:
            host: Redis host (defaults to REDIS_HOST env var)
            port: Redis port (defaults to REDIS_PORT env var)
            password: Redis password (optional)
            default_ttl: Default TTL in seconds
            enabled: Whether caching is enabled
        """
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.password = password or os.getenv("REDIS_PASSWORD")
        self.default_ttl = default_ttl
        self.enabled = enabled and os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true"

        self.client: Optional[aioredis.Redis] = None

        # Stats
        self.hits = 0
        self.misses = 0

        logger.info(
            "redis_cache_initialized",
            host=self.host,
            port=self.port,
            ttl_seconds=self.default_ttl,
            enabled=self.enabled
        )

    async def connect(self):
        """Establish Redis connection."""
        if not self.enabled:
            logger.info("redis_cache_disabled")
            return

        try:
            self.client = await aioredis.from_url(
                f"redis://{self.host}:{self.port}",
                password=self.password,
                encoding="utf-8",
                decode_responses=True
            )

            # Test connection
            await self.client.ping()
            logger.info("redis_connected")

        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            self.enabled = False  # Disable cache on connection failure

    async def health_check(self) -> bool:
        """
        Check if Redis is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.error("redis_health_check_failed", error=str(e))
            return False

    def _make_key(self, collection: str, query: str) -> str:
        """
        Generate cache key from collection and query.

        Args:
            collection: Collection name
            query: Query text

        Returns:
            Cache key (hash-based)
        """
        content = f"{collection}:{query}"
        hash_digest = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"memory:{collection}:{hash_digest}"

    async def get(self, collection: str, query: str) -> Optional[list]:
        """
        Get cached search results.

        Args:
            collection: Collection name
            query: Query text

        Returns:
            Cached results or None
        """
        if not self.enabled or not self.client:
            return None

        try:
            key = self._make_key(collection, query)
            cached_json = await self.client.get(key)

            if cached_json:
                self.hits += 1
                logger.debug(
                    "cache_hit",
                    collection=collection,
                    query_preview=query[:50]
                )
                return json.loads(cached_json)
            else:
                self.misses += 1
                return None

        except Exception as e:
            logger.error("cache_get_failed", error=str(e))
            return None

    async def set(
        self,
        collection: str,
        query: str,
        results: list,
        ttl: Optional[int] = None
    ):
        """
        Cache search results.

        Args:
            collection: Collection name
            query: Query text
            results: Search results to cache
            ttl: Time-to-live in seconds (defaults to default_ttl)
        """
        if not self.enabled or not self.client:
            return

        try:
            key = self._make_key(collection, query)
            results_json = json.dumps(results)
            ttl_seconds = ttl or self.default_ttl

            await self.client.setex(
                name=key,
                time=ttl_seconds,
                value=results_json
            )

            logger.debug(
                "cache_set",
                collection=collection,
                query_preview=query[:50],
                ttl_seconds=ttl_seconds
            )

        except Exception as e:
            logger.error("cache_set_failed", error=str(e))

    async def invalidate(self, collection: str, query: str):
        """
        Invalidate cached results for a specific query.

        Args:
            collection: Collection name
            query: Query text
        """
        if not self.enabled or not self.client:
            return

        try:
            key = self._make_key(collection, query)
            await self.client.delete(key)

            logger.debug(
                "cache_invalidated",
                collection=collection,
                query_preview=query[:50]
            )

        except Exception as e:
            logger.error("cache_invalidation_failed", error=str(e))

    async def clear_collection(self, collection: str):
        """
        Clear all cached results for a collection.

        Args:
            collection: Collection name
        """
        if not self.enabled or not self.client:
            return

        try:
            # Find all keys for this collection
            pattern = f"memory:{collection}:*"
            keys = await self.client.keys(pattern)

            if keys:
                await self.client.delete(*keys)
                logger.info("collection_cache_cleared", collection=collection, keys_deleted=len(keys))

        except Exception as e:
            logger.error("clear_collection_failed", collection=collection, error=str(e))

    async def clear_all(self):
        """Clear entire cache (use with caution!)."""
        if not self.enabled or not self.client:
            return

        try:
            await self.client.flushdb()
            logger.warning("cache_cleared_all")

        except Exception as e:
            logger.error("clear_all_failed", error=str(e))

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate
        """
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0

        return {
            "enabled": self.enabled,
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": total,
            "hit_rate_percent": round(hit_rate, 2)
        }

    async def close(self):
        """Close Redis connection."""
        if self.client:
            try:
                await self.client.close()
                logger.info("redis_connection_closed")
            except Exception as e:
                logger.error("redis_close_failed", error=str(e))


# Global instance (lazy initialized)
_redis_cache: Optional[RedisCache] = None


def get_redis_cache() -> RedisCache:
    """Get or create global Redis cache instance."""
    global _redis_cache

    if _redis_cache is None:
        _redis_cache = RedisCache(
            default_ttl=int(os.getenv("REDIS_TTL", "86400")),
            enabled=os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true"
        )

    return _redis_cache
