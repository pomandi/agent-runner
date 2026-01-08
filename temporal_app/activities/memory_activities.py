"""
Memory activities - wraps memory layer as Temporal activities.

Provides CRUD operations for vector memory (Qdrant), session cache (Redis),
and embedding generation for Temporal workflows.
"""
from temporalio import activity
from typing import Dict, Any, List, Optional
import logging
import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from temporal_app.monitoring import observe_activity

# Import monitoring metrics
try:
    from monitoring.metrics import record_memory_operation, MemoryMetrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Global memory manager instance (initialized by worker)
_memory_manager = None


async def get_memory_manager():
    """Get or create memory manager singleton."""
    global _memory_manager

    if _memory_manager is None:
        from memory import MemoryManager
        _memory_manager = MemoryManager()
        await _memory_manager.initialize()
        activity.logger.info("Memory manager initialized")

    return _memory_manager


@activity.defn
async def search_memory(
    collection: str,
    query: str,
    top_k: int = 10,
    filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Search vector memory for similar documents.

    Args:
        collection: Collection name (invoices, social_posts, ad_reports, agent_context)
        query: Search query text
        top_k: Number of results to return
        filters: Optional metadata filters

    Returns:
        List of search results with score and payload
    """
    activity.logger.info(
        f"Searching memory: collection={collection}, query_len={len(query)}, top_k={top_k}"
    )

    start_time = time.time()
    status = "success"
    cache_hit = False

    try:
        manager = await get_memory_manager()

        results = await manager.search(
            collection=collection,
            query=query,
            top_k=top_k,
            filters=filters
        )

        duration = time.time() - start_time

        activity.logger.info(
            f"Memory search complete: found {len(results)} results, "
            f"top_score={results[0]['score']:.2%}" if results else "no results"
        )

        # Record metrics
        if METRICS_AVAILABLE and results:
            record_memory_operation(
                operation="search",
                collection=collection,
                duration_seconds=duration,
                status=status,
                cache_hit=cache_hit,
                similarity_score=results[0]["score"] if results else None
            )

        return results

    except Exception as e:
        status = "failure"
        duration = time.time() - start_time

        activity.logger.error(f"Memory search failed: {str(e)}")

        # Record failure metrics
        if METRICS_AVAILABLE:
            record_memory_operation(
                operation="search",
                collection=collection,
                duration_seconds=duration,
                status=status
            )

        # Return empty results instead of failing the activity
        return []


@activity.defn
async def save_to_memory(
    collection: str,
    content: str,
    metadata: Dict[str, Any]
) -> int:
    """
    Save document to vector memory.

    Args:
        collection: Collection name
        content: Text content to embed and save
        metadata: Document metadata

    Returns:
        Document ID
    """
    activity.logger.info(
        f"Saving to memory: collection={collection}, content_len={len(content)}, "
        f"metadata_keys={list(metadata.keys())}"
    )

    start_time = time.time()
    status = "success"

    try:
        manager = await get_memory_manager()

        doc_id = await manager.save(
            collection=collection,
            content=content,
            metadata=metadata
        )

        duration = time.time() - start_time

        activity.logger.info(f"Saved to memory: doc_id={doc_id}")

        # Record metrics
        if METRICS_AVAILABLE:
            record_memory_operation(
                operation="save",
                collection=collection,
                duration_seconds=duration,
                status=status
            )

        return doc_id

    except Exception as e:
        status = "failure"
        duration = time.time() - start_time

        activity.logger.error(f"Memory save failed: {str(e)}")

        # Record failure metrics
        if METRICS_AVAILABLE:
            record_memory_operation(
                operation="save",
                collection=collection,
                duration_seconds=duration,
                status=status
            )

        raise


@activity.defn
async def batch_save_to_memory(
    collection: str,
    items: List[Dict[str, Any]]
) -> int:
    """
    Batch save multiple documents to memory.

    Args:
        collection: Collection name
        items: List of dicts with 'content' and 'metadata' keys

    Returns:
        Number of documents saved
    """
    activity.logger.info(
        f"Batch saving to memory: collection={collection}, count={len(items)}"
    )

    try:
        manager = await get_memory_manager()

        count = await manager.batch_save(collection, items)

        activity.logger.info(f"Batch save complete: {count} documents saved")

        return count

    except Exception as e:
        activity.logger.error(f"Batch save failed: {str(e)}")
        raise


@activity.defn
async def update_memory_metadata(
    collection: str,
    doc_id: int,
    metadata_updates: Dict[str, Any]
) -> bool:
    """
    Update metadata for a document in memory.

    Args:
        collection: Collection name
        doc_id: Document ID
        metadata_updates: Metadata fields to update

    Returns:
        Success boolean
    """
    activity.logger.info(
        f"Updating memory metadata: collection={collection}, doc_id={doc_id}, "
        f"updates={list(metadata_updates.keys())}"
    )

    try:
        manager = await get_memory_manager()

        success = await manager.update_metadata(
            collection=collection,
            doc_id=doc_id,
            metadata_updates=metadata_updates
        )

        activity.logger.info(f"Metadata update: {'success' if success else 'failed'}")

        return success

    except Exception as e:
        activity.logger.error(f"Metadata update failed: {str(e)}")
        return False


@activity.defn
async def delete_from_memory(
    collection: str,
    doc_id: int
) -> bool:
    """
    Delete document from memory.

    Args:
        collection: Collection name
        doc_id: Document ID to delete

    Returns:
        Success boolean
    """
    activity.logger.info(
        f"Deleting from memory: collection={collection}, doc_id={doc_id}"
    )

    try:
        manager = await get_memory_manager()

        success = await manager.delete(collection=collection, doc_id=doc_id)

        activity.logger.info(f"Delete: {'success' if success else 'failed'}")

        return success

    except Exception as e:
        activity.logger.error(f"Delete failed: {str(e)}")
        return False


@activity.defn
async def get_memory_stats() -> Dict[str, Any]:
    """
    Get memory system statistics.

    Returns:
        Stats dict with cache hit rate, collection counts, etc.
    """
    activity.logger.info("Getting memory system stats")

    try:
        manager = await get_memory_manager()

        stats = await manager.get_system_stats()

        activity.logger.info(
            f"Memory stats: cache_hit_rate={stats['cache']['hit_rate_percent']:.1f}%, "
            f"collections={len(stats['collections'])}"
        )

        return stats

    except Exception as e:
        activity.logger.error(f"Get stats failed: {str(e)}")
        return {
            "error": str(e),
            "cache": {"hit_rate_percent": 0.0},
            "collections": {}
        }


@activity.defn
async def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding vector for text.

    Args:
        text: Text to embed

    Returns:
        Embedding vector (1536 dimensions)
    """
    activity.logger.info(f"Generating embedding: text_len={len(text)}")

    try:
        manager = await get_memory_manager()

        vector = await manager.embedding_generator.generate_single(text)

        activity.logger.info(f"Embedding generated: dimensions={len(vector)}")

        return vector

    except Exception as e:
        activity.logger.error(f"Embedding generation failed: {str(e)}")
        raise


@activity.defn
async def check_duplicate_in_memory(
    collection: str,
    content: str,
    similarity_threshold: float = 0.90,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Check if content is duplicate (high similarity) in memory.

    Args:
        collection: Collection name
        content: Content to check
        similarity_threshold: Threshold for duplicate detection (default 0.90)
        filters: Optional metadata filters

    Returns:
        Dict with is_duplicate, similarity_score, similar_doc
    """
    activity.logger.info(
        f"Checking duplicate: collection={collection}, threshold={similarity_threshold}"
    )

    try:
        manager = await get_memory_manager()

        # Search for similar documents
        results = await manager.search(
            collection=collection,
            query=content,
            top_k=1,
            filters=filters
        )

        if results and results[0]["score"] >= similarity_threshold:
            activity.logger.warning(
                f"Duplicate detected: similarity={results[0]['score']:.2%}"
            )
            return {
                "is_duplicate": True,
                "similarity_score": results[0]["score"],
                "similar_doc": results[0]
            }
        else:
            activity.logger.info(
                f"No duplicate: best_score={results[0]['score']:.2%}" if results else "no similar docs"
            )
            return {
                "is_duplicate": False,
                "similarity_score": results[0]["score"] if results else 0.0,
                "similar_doc": None
            }

    except Exception as e:
        activity.logger.error(f"Duplicate check failed: {str(e)}")
        return {
            "is_duplicate": False,
            "similarity_score": 0.0,
            "similar_doc": None,
            "error": str(e)
        }


@activity.defn
async def clear_memory_cache(collection: Optional[str] = None) -> bool:
    """
    Clear Redis cache for memory queries.

    Args:
        collection: Optional collection name (clear all if None)

    Returns:
        Success boolean
    """
    activity.logger.info(
        f"Clearing memory cache: collection={collection or 'all'}"
    )

    try:
        manager = await get_memory_manager()

        if collection:
            await manager.redis_cache.clear_collection(collection)
        else:
            await manager.redis_cache.clear_all()

        activity.logger.info("Cache cleared successfully")

        return True

    except Exception as e:
        activity.logger.error(f"Cache clear failed: {str(e)}")
        return False


# Activity list for worker registration
MEMORY_ACTIVITIES = [
    search_memory,
    save_to_memory,
    batch_save_to_memory,
    update_memory_metadata,
    delete_from_memory,
    get_memory_stats,
    generate_embedding,
    check_duplicate_in_memory,
    clear_memory_cache
]
