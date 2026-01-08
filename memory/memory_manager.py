"""
Memory Manager
==============

Unified interface for three-tier memory architecture:
- Tier 1: Redis (working memory, hot cache)
- Tier 2: Qdrant (semantic memory, vector search)
- Tier 3: PostgreSQL (structured data - handled by existing code)

This is the main API that agents use to interact with memory.
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog

from .embeddings import EmbeddingGenerator, get_embedding_generator
from .qdrant_client import QdrantClientWrapper, get_qdrant_client
from .redis_cache import RedisCache, get_redis_cache
from .collections import get_collection_config, get_all_collection_names

logger = structlog.get_logger(__name__)


class MemoryManager:
    """
    Unified memory manager for agent system.

    Usage:
        manager = MemoryManager()
        await manager.initialize()

        # Save memory
        await manager.save(
            collection="invoices",
            content="Invoice from SNCB for €22.70",
            metadata={"vendor": "SNCB", "amount": 22.70}
        )

        # Search memory
        results = await manager.search(
            collection="invoices",
            query="SNCB train ticket",
            top_k=5
        )
    """

    def __init__(
        self,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        qdrant_client: Optional[QdrantClientWrapper] = None,
        redis_cache: Optional[RedisCache] = None,
        enabled: bool = True
    ):
        """
        Initialize memory manager.

        Args:
            embedding_generator: Custom embedding generator (or uses global)
            qdrant_client: Custom Qdrant client (or uses global)
            redis_cache: Custom Redis cache (or uses global)
            enabled: Whether memory system is enabled (from ENABLE_MEMORY env var)
        """
        self.enabled = enabled and os.getenv("ENABLE_MEMORY", "true").lower() == "true"

        if not self.enabled:
            logger.info("memory_system_disabled")
            return

        # Initialize components
        self.embedding_generator = embedding_generator or get_embedding_generator()
        self.qdrant_client = qdrant_client or get_qdrant_client()
        self.redis_cache = redis_cache or get_redis_cache()

        # Config
        self.max_results = int(os.getenv("MAX_MEMORY_RESULTS", "10"))
        self.similarity_threshold = float(os.getenv("MEMORY_SIMILARITY_THRESHOLD", "0.75"))
        self.fallback_enabled = os.getenv("MEMORY_FALLBACK_ENABLED", "true").lower() == "true"

        logger.info(
            "memory_manager_initialized",
            enabled=self.enabled,
            max_results=self.max_results,
            similarity_threshold=self.similarity_threshold
        )

    async def initialize(self):
        """
        Initialize all memory components (call this on startup).

        - Connects to Redis
        - Verifies Qdrant health
        - Creates collections if needed
        """
        if not self.enabled:
            return

        logger.info("initializing_memory_system")

        # Connect Redis
        await self.redis_cache.connect()

        # Verify Qdrant health
        qdrant_healthy = await self.qdrant_client.health_check()
        if not qdrant_healthy:
            if self.fallback_enabled:
                logger.warning("qdrant_unhealthy_using_fallback")
            else:
                raise ConnectionError("Qdrant is unhealthy and fallback is disabled")

        # Create collections if they don't exist
        for collection_name in get_all_collection_names():
            try:
                await self.qdrant_client.create_collection_if_not_exists(collection_name)
            except Exception as e:
                logger.error("collection_creation_failed", collection=collection_name, error=str(e))

        logger.info("memory_system_initialized")

    async def save(
        self,
        collection: str,
        content: str,
        metadata: Dict[str, Any],
        doc_id: Optional[int] = None
    ) -> int:
        """
        Save content to memory (generates embedding and stores in Qdrant).

        Args:
            collection: Collection name (e.g., "invoices", "social_posts")
            content: Text content to embed
            metadata: Additional metadata to store with the vector
            doc_id: Optional document ID (auto-generated if not provided)

        Returns:
            Document ID

        Example:
            doc_id = await manager.save(
                collection="invoices",
                content="Invoice from SNCB for train ticket €22.70",
                metadata={
                    "vendor_name": "SNCB",
                    "amount": 22.70,
                    "date": "2024-01-05",
                    "matched": False
                }
            )
        """
        if not self.enabled:
            logger.debug("memory_disabled_skipping_save")
            return -1

        try:
            # Generate embedding
            vector = await self.embedding_generator.generate_single(content)

            # Add timestamp to metadata
            metadata_with_timestamp = {
                **metadata,
                "created_at": datetime.utcnow().isoformat(),
                "_content_preview": content[:100]  # Store preview for debugging
            }

            # Generate ID if not provided
            if doc_id is None:
                doc_id = hash(content + str(metadata))

            # Upsert to Qdrant
            points = [{
                "id": doc_id,
                "vector": vector,
                "payload": metadata_with_timestamp
            }]

            await self.qdrant_client.upsert_points(collection, points)

            logger.info(
                "memory_saved",
                collection=collection,
                doc_id=doc_id,
                content_preview=content[:50]
            )

            # Invalidate related cache entries
            await self.redis_cache.clear_collection(collection)

            return doc_id

        except Exception as e:
            logger.error(
                "memory_save_failed",
                collection=collection,
                error=str(e)
            )
            if not self.fallback_enabled:
                raise
            return -1

    async def search(
        self,
        collection: str,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search memory for similar content.

        Args:
            collection: Collection to search
            query: Query text
            top_k: Number of results (defaults to MAX_MEMORY_RESULTS)
            filters: Optional filters (e.g., {"matched": False})
            use_cache: Use Redis cache

        Returns:
            List of results with 'id', 'score', 'payload'

        Example:
            results = await manager.search(
                collection="invoices",
                query="SNCB train ticket around 20 euros",
                top_k=5,
                filters={"matched": False}
            )

            for result in results:
                print(f"Score: {result['score']:.2f}")
                print(f"Vendor: {result['payload']['vendor_name']}")
                print(f"Amount: {result['payload']['amount']}")
        """
        if not self.enabled:
            logger.debug("memory_disabled_returning_empty")
            return []

        # Use default top_k if not provided
        if top_k is None:
            top_k = self.max_results

        try:
            # Check cache first
            if use_cache:
                cached_results = await self.redis_cache.get(collection, query)
                if cached_results is not None:
                    logger.debug("using_cached_results", collection=collection)
                    return cached_results[:top_k]

            # Generate query embedding
            query_vector = await self.embedding_generator.generate_single(query)

            # Search Qdrant
            results = await self.qdrant_client.search(
                collection_name=collection,
                query_vector=query_vector,
                top_k=top_k,
                filters=filters,
                score_threshold=self.similarity_threshold
            )

            # Cache results
            if use_cache and results:
                await self.redis_cache.set(collection, query, results)

            logger.info(
                "memory_search_complete",
                collection=collection,
                query_preview=query[:50],
                results_count=len(results),
                top_score=results[0]["score"] if results else 0
            )

            return results

        except Exception as e:
            logger.error(
                "memory_search_failed",
                collection=collection,
                query_preview=query[:50],
                error=str(e)
            )

            if not self.fallback_enabled:
                raise

            return []

    async def batch_save(
        self,
        collection: str,
        items: List[Dict[str, Any]]
    ) -> int:
        """
        Save multiple items to memory in batch.

        Args:
            collection: Collection name
            items: List of dicts with 'content' and 'metadata' keys

        Returns:
            Number of items saved

        Example:
            items = [
                {
                    "content": "Invoice from SNCB €22.70",
                    "metadata": {"vendor": "SNCB", "amount": 22.70}
                },
                {
                    "content": "Invoice from Delhaize €45.30",
                    "metadata": {"vendor": "Delhaize", "amount": 45.30}
                }
            ]

            count = await manager.batch_save("invoices", items)
        """
        if not self.enabled or not items:
            return 0

        try:
            # Extract texts for batch embedding
            texts = [item["content"] for item in items]

            # Generate embeddings in batch
            vectors = await self.embedding_generator.generate_batch(texts, show_progress=True)

            # Prepare points
            points = []
            for i, item in enumerate(items):
                metadata_with_timestamp = {
                    **item["metadata"],
                    "created_at": datetime.utcnow().isoformat(),
                    "_content_preview": item["content"][:100]
                }

                doc_id = item.get("id", hash(item["content"] + str(item["metadata"])))

                points.append({
                    "id": doc_id,
                    "vector": vectors[i],
                    "payload": metadata_with_timestamp
                })

            # Upsert batch
            count = await self.qdrant_client.upsert_points(collection, points)

            logger.info(
                "batch_save_complete",
                collection=collection,
                items_saved=count
            )

            # Invalidate cache
            await self.redis_cache.clear_collection(collection)

            return count

        except Exception as e:
            logger.error(
                "batch_save_failed",
                collection=collection,
                error=str(e)
            )
            if not self.fallback_enabled:
                raise
            return 0

    async def get_collection_stats(self, collection: str) -> Dict[str, Any]:
        """
        Get statistics for a collection.

        Returns:
            Dict with points_count, vectors_count, etc.
        """
        if not self.enabled:
            return {"enabled": False}

        try:
            info = await self.qdrant_client.get_collection_info(collection)
            return info
        except Exception as e:
            logger.error("get_stats_failed", collection=collection, error=str(e))
            return {"error": str(e)}

    async def get_system_stats(self) -> Dict[str, Any]:
        """
        Get overall memory system statistics.

        Returns:
            Dict with cache stats, collection info, etc.
        """
        if not self.enabled:
            return {"enabled": False}

        stats = {
            "enabled": self.enabled,
            "cache": self.redis_cache.get_stats(),
            "embedding_cache": self.embedding_generator.get_cache_stats(),
            "collections": {}
        }

        # Get stats for each collection
        for collection_name in get_all_collection_names():
            try:
                stats["collections"][collection_name] = await self.get_collection_stats(collection_name)
            except Exception as e:
                stats["collections"][collection_name] = {"error": str(e)}

        return stats

    async def clear_cache(self):
        """Clear Redis cache (useful for testing)."""
        if not self.enabled:
            return

        await self.redis_cache.clear_all()
        logger.info("memory_cache_cleared")

    async def close(self):
        """Close all connections (call on shutdown)."""
        if not self.enabled:
            return

        await self.redis_cache.close()
        await self.qdrant_client.close()
        logger.info("memory_manager_closed")


# Global instance (lazy initialized)
_memory_manager: Optional[MemoryManager] = None


async def get_memory_manager() -> MemoryManager:
    """
    Get or create global memory manager instance.

    Note: Call initialize() on first use!
    """
    global _memory_manager

    if _memory_manager is None:
        _memory_manager = MemoryManager()
        await _memory_manager.initialize()

    return _memory_manager
