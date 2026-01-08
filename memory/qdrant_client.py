"""
Qdrant Client Wrapper
=====================

Async wrapper for Qdrant vector database operations.
Handles connection pooling, error handling, and retries.
"""

import os
from typing import List, Dict, Any, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest
)
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .collections import get_collection_config, get_all_collection_names

logger = structlog.get_logger(__name__)


class QdrantClientWrapper:
    """
    Async Qdrant client with convenience methods.

    Features:
    - Connection management
    - Collection initialization
    - Upsert with automatic ID generation
    - Search with filters
    - Health checks
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        api_key: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize Qdrant client.

        Args:
            host: Qdrant host (defaults to QDRANT_HOST env var)
            port: Qdrant port (defaults to QDRANT_PORT env var)
            api_key: API key for authentication (optional)
            timeout: Request timeout in seconds
        """
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.timeout = timeout

        # Initialize client
        self.client = AsyncQdrantClient(
            host=self.host,
            port=self.port,
            api_key=self.api_key,
            timeout=self.timeout
        )

        logger.info(
            "qdrant_client_initialized",
            host=self.host,
            port=self.port,
            has_api_key=bool(self.api_key)
        )

    async def health_check(self) -> bool:
        """
        Check if Qdrant is healthy and accessible.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Try to list collections
            await self.client.get_collections()
            logger.info("qdrant_health_check_passed")
            return True
        except Exception as e:
            logger.error("qdrant_health_check_failed", error=str(e))
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def create_collection_if_not_exists(
        self,
        collection_name: str,
        vectors_config: Optional[VectorParams] = None
    ) -> bool:
        """
        Create collection if it doesn't exist.

        Args:
            collection_name: Name of the collection
            vectors_config: Vector configuration (defaults to config from collections.py)

        Returns:
            True if created, False if already exists
        """
        try:
            # Check if collection exists
            collections = await self.client.get_collections()
            existing_names = [c.name for c in collections.collections]

            if collection_name in existing_names:
                logger.debug("collection_already_exists", collection=collection_name)
                return False

            # Get default config if not provided
            if vectors_config is None:
                config = get_collection_config(collection_name)
                vectors_config = config["vectors_config"]

            # Create collection
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config
            )

            logger.info(
                "collection_created",
                collection=collection_name,
                vector_size=vectors_config.size,
                distance=vectors_config.distance
            )
            return True

        except Exception as e:
            logger.error("collection_creation_failed", collection=collection_name, error=str(e))
            raise

    async def upsert_points(
        self,
        collection_name: str,
        points: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Upsert points into collection (insert or update).

        Args:
            collection_name: Target collection
            points: List of points with 'id', 'vector', and 'payload'
            batch_size: Points per batch

        Returns:
            Number of points upserted
        """
        if not points:
            return 0

        try:
            # Convert to PointStruct objects
            point_structs = [
                PointStruct(
                    id=point.get("id", hash(str(point["payload"]))),  # Auto-generate ID if missing
                    vector=point["vector"],
                    payload=point["payload"]
                )
                for point in points
            ]

            # Upsert in batches
            total_upserted = 0
            for i in range(0, len(point_structs), batch_size):
                batch = point_structs[i:i + batch_size]

                await self.client.upsert(
                    collection_name=collection_name,
                    points=batch
                )

                total_upserted += len(batch)
                logger.debug(
                    "batch_upserted",
                    collection=collection_name,
                    batch_size=len(batch),
                    total=total_upserted
                )

            logger.info(
                "points_upserted",
                collection=collection_name,
                count=total_upserted
            )
            return total_upserted

        except Exception as e:
            logger.error(
                "upsert_failed",
                collection=collection_name,
                error=str(e)
            )
            raise

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in collection.

        Args:
            collection_name: Collection to search
            query_vector: Query embedding
            top_k: Number of results to return
            filters: Optional filters (e.g., {"matched": False})
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of results with 'id', 'score', and 'payload'
        """
        try:
            # Build filter if provided
            query_filter = None
            if filters:
                conditions = []
                for key, value in filters.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                if conditions:
                    query_filter = Filter(must=conditions)

            # Search
            results = await self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=query_filter,
                score_threshold=score_threshold
            )

            # Format results
            formatted_results = [
                {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload
                }
                for result in results
            ]

            logger.debug(
                "search_complete",
                collection=collection_name,
                results_count=len(formatted_results),
                top_score=formatted_results[0]["score"] if formatted_results else 0
            )

            return formatted_results

        except Exception as e:
            logger.error(
                "search_failed",
                collection=collection_name,
                error=str(e)
            )
            raise

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        Get information about a collection.

        Returns:
            Dict with 'vectors_count', 'points_count', etc.
        """
        try:
            info = await self.client.get_collection(collection_name=collection_name)

            return {
                "name": collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status,
                "vector_size": info.config.params.vectors.size
            }

        except Exception as e:
            logger.error("get_collection_info_failed", collection=collection_name, error=str(e))
            raise

    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection (use with caution!).

        Returns:
            True if deleted successfully
        """
        try:
            await self.client.delete_collection(collection_name=collection_name)
            logger.warning("collection_deleted", collection=collection_name)
            return True
        except Exception as e:
            logger.error("collection_deletion_failed", collection=collection_name, error=str(e))
            return False

    async def close(self):
        """Close client connection."""
        try:
            await self.client.close()
            logger.info("qdrant_client_closed")
        except Exception as e:
            logger.error("client_close_failed", error=str(e))


# Global instance (lazy initialized)
_qdrant_client: Optional[QdrantClientWrapper] = None


def get_qdrant_client() -> QdrantClientWrapper:
    """Get or create global Qdrant client instance."""
    global _qdrant_client

    if _qdrant_client is None:
        _qdrant_client = QdrantClientWrapper()

    return _qdrant_client
