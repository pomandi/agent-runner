"""
Duplicate Data Detector
========================

Three-layer duplicate detection system for analytics data:
1. Hash-based (fastest) - exact match using SHA256 hash
2. Memory-Hub lookup - check for existing source + date combination
3. Qdrant semantic similarity - fuzzy duplicate detection (>0.98 threshold)

Usage:
    detector = DuplicateDetector(memory_hub_client, qdrant_client, redis_client)
    result = await detector.check_duplicate(data)

    if result["is_duplicate"]:
        if result["recommended_action"] == "skip":
            # Skip this data entirely
        elif result["recommended_action"] == "update":
            # Update existing record instead of creating new
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib
import json
import structlog

logger = structlog.get_logger(__name__)


class DuplicateDetector:
    """
    Veri toplama sırasında ve sonrasında duplicate tespiti yapar.

    Üç katmanlı kontrol:
    1. Hash-based: Hızlı, exact match için
    2. Memory-Hub: data_source + data_date unique constraint
    3. Qdrant: Semantic similarity (fuzzy duplicate)

    Attributes:
        memory_hub: Memory-Hub MCP client
        qdrant: Qdrant vector database client
        redis: Redis cache client
        config: Configuration options
    """

    def __init__(
        self,
        memory_hub_client=None,
        qdrant_client=None,
        redis_client=None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize DuplicateDetector.

        Args:
            memory_hub_client: Memory-Hub MCP client (optional)
            qdrant_client: Qdrant client (optional)
            redis_client: Redis client for hash caching (optional)
            config: Configuration dict with options like:
                - hash_ttl: TTL for hash cache in seconds (default: 604800 = 7 days)
                - similarity_threshold: Qdrant similarity threshold (default: 0.98)
                - on_duplicate: Action on duplicate - "skip", "update", "warn" (default: "skip")
        """
        self.memory_hub = memory_hub_client
        self.qdrant = qdrant_client
        self.redis = redis_client

        # Default configuration
        self.config = {
            "hash_ttl": 604800,  # 7 days
            "similarity_threshold": 0.98,
            "on_duplicate": "skip",
            "enabled_checks": ["hash", "memory_hub", "qdrant"]
        }
        if config:
            self.config.update(config)

        # In-memory hash cache (fallback if Redis not available)
        self._local_hash_cache: Dict[str, str] = {}

        logger.info(
            "duplicate_detector_initialized",
            memory_hub=self.memory_hub is not None,
            qdrant=self.qdrant is not None,
            redis=self.redis is not None,
            config=self.config
        )

    async def check_duplicate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Veri için duplicate kontrolü yapar.

        Args:
            data: Dictionary containing at minimum:
                - source: Data source name (e.g., "google_ads")
                - date: Data date (e.g., "2026-01-12")
                - brand: Brand name (e.g., "pomandi")

        Returns:
            {
                "is_duplicate": bool,
                "duplicate_type": str,  # "exact", "memory_hub", "semantic", None
                "existing_id": str,     # Existing record ID
                "similarity_score": float,  # For semantic duplicates
                "recommended_action": str,  # "skip", "update", "proceed"
                "details": dict
            }
        """
        result = {
            "is_duplicate": False,
            "duplicate_type": None,
            "existing_id": None,
            "similarity_score": None,
            "recommended_action": "proceed",
            "details": {},
            "checks_performed": []
        }

        source = data.get("source", "unknown")
        date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        brand = data.get("brand", "unknown")

        logger.debug(
            "checking_duplicate",
            source=source,
            date=date,
            brand=brand
        )

        # === 1. Hash-based check (fastest) ===
        if "hash" in self.config["enabled_checks"]:
            hash_result = await self._check_hash_duplicate(data)
            result["checks_performed"].append("hash")

            if hash_result["is_duplicate"]:
                result.update({
                    "is_duplicate": True,
                    "duplicate_type": "exact",
                    "existing_id": hash_result.get("existing_id"),
                    "recommended_action": "skip",
                    "details": {"hash": hash_result.get("hash")}
                })
                logger.warning(
                    "duplicate_detected_hash",
                    source=source,
                    date=date,
                    existing_id=hash_result.get("existing_id")
                )
                return result

        # === 2. Memory-Hub check ===
        if "memory_hub" in self.config["enabled_checks"] and self.memory_hub:
            mh_result = await self._check_memory_hub_duplicate(source, date, brand)
            result["checks_performed"].append("memory_hub")

            if mh_result["is_duplicate"]:
                result.update({
                    "is_duplicate": True,
                    "duplicate_type": "memory_hub",
                    "existing_id": mh_result.get("existing_id"),
                    "recommended_action": "update",  # Update instead of create
                    "details": {"card_type": mh_result.get("card_type")}
                })
                logger.warning(
                    "duplicate_detected_memory_hub",
                    source=source,
                    date=date,
                    existing_id=mh_result.get("existing_id")
                )
                return result

        # === 3. Qdrant similarity check (slowest, most thorough) ===
        if "qdrant" in self.config["enabled_checks"] and self.qdrant:
            qdrant_result = await self._check_qdrant_similarity(data)
            result["checks_performed"].append("qdrant")

            if qdrant_result["is_duplicate"]:
                result.update({
                    "is_duplicate": True,
                    "duplicate_type": "semantic",
                    "existing_id": qdrant_result.get("existing_id"),
                    "similarity_score": qdrant_result.get("similarity_score"),
                    "recommended_action": "warn",  # Warn but don't block
                    "details": {"similar_to": qdrant_result.get("similar_to")}
                })
                logger.warning(
                    "duplicate_detected_semantic",
                    source=source,
                    date=date,
                    similarity=qdrant_result.get("similarity_score")
                )
                return result

        # === Not a duplicate - cache the hash ===
        if "hash" in self.config["enabled_checks"]:
            await self._cache_hash(data)

        logger.debug(
            "no_duplicate_found",
            source=source,
            date=date,
            checks=result["checks_performed"]
        )

        return result

    async def _check_hash_duplicate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check for exact duplicate using hash."""
        data_hash = self._compute_hash(data)

        # Check Redis first
        if self.redis:
            try:
                cached = await self.redis.get(f"data_hash:{data_hash}")
                if cached:
                    return {
                        "is_duplicate": True,
                        "existing_id": cached.decode() if isinstance(cached, bytes) else cached,
                        "hash": data_hash
                    }
            except Exception as e:
                logger.warning("redis_hash_check_failed", error=str(e))

        # Fallback to local cache
        if data_hash in self._local_hash_cache:
            return {
                "is_duplicate": True,
                "existing_id": self._local_hash_cache[data_hash],
                "hash": data_hash
            }

        return {"is_duplicate": False, "hash": data_hash}

    async def _check_memory_hub_duplicate(
        self,
        source: str,
        date: str,
        brand: str
    ) -> Dict[str, Any]:
        """Check for duplicate in Memory-Hub."""
        try:
            # Call Memory-Hub MCP to search for existing card
            # The search query looks for analytics_data cards with matching source and date
            search_result = await self.memory_hub.search({
                "type": "analytics_data",
                "data_source": source,
                "data_date": date,
                "project": brand
            })

            if search_result and len(search_result) > 0:
                existing_card = search_result[0]
                return {
                    "is_duplicate": True,
                    "existing_id": existing_card.get("id"),
                    "card_type": existing_card.get("type")
                }
        except Exception as e:
            logger.warning("memory_hub_check_failed", error=str(e))

        return {"is_duplicate": False}

    async def _check_qdrant_similarity(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check for semantic duplicate using Qdrant vector search."""
        try:
            search_text = self._create_search_text(data)

            # Search Qdrant for similar vectors
            results = await self.qdrant.search(
                collection="analytics_data",
                query=search_text,
                top_k=1,
                score_threshold=self.config["similarity_threshold"]
            )

            if results and len(results) > 0 and results[0].get("score", 0) >= self.config["similarity_threshold"]:
                return {
                    "is_duplicate": True,
                    "existing_id": results[0].get("id"),
                    "similarity_score": results[0].get("score"),
                    "similar_to": results[0].get("payload", {}).get("source", "unknown")
                }
        except Exception as e:
            logger.warning("qdrant_similarity_check_failed", error=str(e))

        return {"is_duplicate": False}

    async def _cache_hash(self, data: Dict[str, Any]) -> None:
        """Cache the data hash for future duplicate detection."""
        data_hash = self._compute_hash(data)
        data_id = data.get("id", f"{data.get('source')}_{data.get('date')}")

        # Cache in Redis
        if self.redis:
            try:
                await self.redis.set(
                    f"data_hash:{data_hash}",
                    data_id,
                    ex=self.config["hash_ttl"]
                )
                logger.debug("hash_cached_redis", hash=data_hash[:8])
            except Exception as e:
                logger.warning("redis_cache_failed", error=str(e))

        # Also cache locally (fallback)
        self._local_hash_cache[data_hash] = data_id

        # Limit local cache size
        if len(self._local_hash_cache) > 1000:
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(self._local_hash_cache.keys())[:100]
            for key in keys_to_remove:
                del self._local_hash_cache[key]

    def _compute_hash(self, data: Dict[str, Any]) -> str:
        """
        Compute deterministic hash for data.

        Uses only key fields to ensure consistent hashing:
        - source
        - date
        - brand
        - total_spend (rounded)
        - total_clicks
        - total_conversions
        """
        # Extract only key fields for hashing
        hash_data = {
            "source": data.get("source", ""),
            "date": data.get("date", ""),
            "brand": data.get("brand", ""),
            "spend": round(float(data.get("total_spend", 0) or 0), 2),
            "clicks": int(data.get("total_clicks", 0) or 0),
            "conversions": int(data.get("total_conversions", 0) or 0)
        }

        # Create deterministic string
        hash_str = json.dumps(hash_data, sort_keys=True)

        # Return first 16 chars of SHA256
        return hashlib.sha256(hash_str.encode()).hexdigest()[:16]

    def _create_search_text(self, data: Dict[str, Any]) -> str:
        """Create text representation for semantic search."""
        parts = [
            data.get("source", ""),
            data.get("date", ""),
            data.get("brand", ""),
            f"spend:{data.get('total_spend', 0)}",
            f"clicks:{data.get('total_clicks', 0)}",
            f"conversions:{data.get('total_conversions', 0)}"
        ]
        return " ".join(str(p) for p in parts if p)

    async def batch_check_duplicates(
        self,
        data_list: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Check multiple data items for duplicates.

        Args:
            data_list: List of data dictionaries to check

        Returns:
            Dict mapping source names to their duplicate check results
        """
        results = {}

        for data in data_list:
            source = data.get("source", "unknown")
            result = await self.check_duplicate(data)
            results[source] = result

        # Summary stats
        total = len(data_list)
        duplicates = sum(1 for r in results.values() if r["is_duplicate"])

        logger.info(
            "batch_duplicate_check_complete",
            total=total,
            duplicates=duplicates,
            duplicate_rate=f"{(duplicates/total)*100:.1f}%" if total > 0 else "0%"
        )

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get duplicate detection statistics."""
        return {
            "local_cache_size": len(self._local_hash_cache),
            "config": self.config,
            "clients": {
                "memory_hub": self.memory_hub is not None,
                "qdrant": self.qdrant is not None,
                "redis": self.redis is not None
            }
        }

    def clear_cache(self) -> None:
        """Clear local hash cache."""
        self._local_hash_cache.clear()
        logger.info("duplicate_detector_cache_cleared")


# Convenience function for standalone usage
async def check_data_duplicate(
    data: Dict[str, Any],
    memory_hub_client=None,
    qdrant_client=None,
    redis_client=None
) -> Dict[str, Any]:
    """
    Quick duplicate check without maintaining a detector instance.

    Args:
        data: Data to check for duplicates
        memory_hub_client: Optional Memory-Hub client
        qdrant_client: Optional Qdrant client
        redis_client: Optional Redis client

    Returns:
        Duplicate check result dictionary
    """
    detector = DuplicateDetector(
        memory_hub_client=memory_hub_client,
        qdrant_client=qdrant_client,
        redis_client=redis_client
    )
    return await detector.check_duplicate(data)
