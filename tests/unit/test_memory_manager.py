"""
Unit tests for Memory Manager
==============================

Tests core functionality of memory layer without requiring full services.
"""

import pytest
import os
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime


pytestmark = pytest.mark.asyncio


class TestMemoryManager:
    """Unit tests for MemoryManager class."""

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_memory_manager_initialization(self):
        """Test memory manager can be initialized."""
        from memory import MemoryManager

        manager = MemoryManager()
        await manager.initialize()

        assert manager.qdrant_client is not None
        assert manager.redis_cache is not None
        assert manager.embedding_generator is not None

        await manager.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_save_and_retrieve_document(self):
        """Test saving and retrieving a document."""
        from memory import MemoryManager

        manager = MemoryManager()
        await manager.initialize()

        # Save document
        doc_id = await manager.save(
            collection="agent_context",
            content="Test document for unit testing",
            metadata={
                "test": True,
                "timestamp": datetime.now().isoformat()
            }
        )

        assert doc_id > 0

        # Search for document
        results = await manager.search(
            collection="agent_context",
            query="unit testing document",
            top_k=5
        )

        assert len(results) > 0
        assert results[0]["score"] > 0.5

        await manager.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_search_with_filters(self):
        """Test searching with metadata filters."""
        from memory import MemoryManager

        manager = MemoryManager()
        await manager.initialize()

        # Save test documents with different metadata
        await manager.save(
            collection="agent_context",
            content="Document A for testing filters",
            metadata={"category": "A", "test": True}
        )

        await manager.save(
            collection="agent_context",
            content="Document B for testing filters",
            metadata={"category": "B", "test": True}
        )

        # Search with filter
        results = await manager.search(
            collection="agent_context",
            query="testing filters",
            top_k=10,
            filters={"category": "A"}
        )

        # Should only return category A documents
        for result in results:
            if "category" in result.get("payload", {}):
                assert result["payload"]["category"] == "A"

        await manager.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_batch_save(self):
        """Test batch saving multiple documents."""
        from memory import MemoryManager

        manager = MemoryManager()
        await manager.initialize()

        # Prepare batch items
        items = [
            {
                "content": f"Batch document {i}",
                "metadata": {"batch_id": 1, "index": i}
            }
            for i in range(5)
        ]

        # Batch save
        count = await manager.batch_save("agent_context", items)

        assert count == 5

        # Verify saved
        results = await manager.search(
            collection="agent_context",
            query="batch document",
            top_k=10,
            filters={"batch_id": 1}
        )

        assert len(results) >= 5

        await manager.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_cache_functionality(self):
        """Test Redis cache is working."""
        from memory import MemoryManager

        manager = MemoryManager()
        await manager.initialize()

        # First search (cache miss)
        results1 = await manager.search(
            collection="agent_context",
            query="cache test query",
            top_k=5
        )

        # Second search (cache hit)
        results2 = await manager.search(
            collection="agent_context",
            query="cache test query",
            top_k=5
        )

        # Results should be identical
        assert len(results1) == len(results2)

        # Cache stats should show hits
        stats = await manager.get_system_stats()
        cache_stats = stats.get("cache", {})

        # We should have at least one cache request
        assert cache_stats.get("total_requests", 0) >= 2

        await manager.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_get_system_stats(self):
        """Test getting system statistics."""
        from memory import MemoryManager

        manager = MemoryManager()
        await manager.initialize()

        stats = await manager.get_system_stats()

        assert "cache" in stats
        assert "collections" in stats
        assert isinstance(stats["collections"], dict)

        await manager.close()


class TestEmbeddingGenerator:
    """Unit tests for EmbeddingGenerator."""

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_generate_single_embedding(self):
        """Test generating single embedding."""
        from memory.embeddings import EmbeddingGenerator

        generator = EmbeddingGenerator()

        vector = await generator.generate_single("Test text for embedding")

        assert len(vector) == 1536  # text-embedding-3-small dimensions
        assert all(isinstance(v, float) for v in vector)

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_generate_batch_embeddings(self):
        """Test generating batch embeddings."""
        from memory.embeddings import EmbeddingGenerator

        generator = EmbeddingGenerator()

        texts = [
            "First test text",
            "Second test text",
            "Third test text"
        ]

        vectors = await generator.generate_batch(texts)

        assert len(vectors) == 3
        assert all(len(v) == 1536 for v in vectors)

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_embedding_cost_estimation(self):
        """Test cost estimation for embeddings."""
        from memory.embeddings import EmbeddingGenerator

        generator = EmbeddingGenerator()

        texts = ["Test text " * 100 for _ in range(10)]  # ~10K tokens

        cost_estimate = await generator.estimate_cost(texts)

        assert "total_tokens" in cost_estimate
        assert "estimated_usd" in cost_estimate
        assert cost_estimate["total_tokens"] > 0
        assert cost_estimate["estimated_usd"] > 0


class TestCollections:
    """Unit tests for collection schemas."""

    def test_collection_names(self):
        """Test collection name enum."""
        from memory.collections import CollectionName

        assert CollectionName.INVOICES == "invoices"
        assert CollectionName.SOCIAL_POSTS == "social_posts"
        assert CollectionName.AD_REPORTS == "ad_reports"
        assert CollectionName.AGENT_CONTEXT == "agent_context"

    def test_collection_configs(self):
        """Test collection configurations."""
        from memory.collections import COLLECTION_CONFIGS, CollectionName

        assert CollectionName.INVOICES in COLLECTION_CONFIGS
        assert CollectionName.SOCIAL_POSTS in COLLECTION_CONFIGS

        invoice_config = COLLECTION_CONFIGS[CollectionName.INVOICES]
        assert "vectors_config" in invoice_config
        assert "schema" in invoice_config


class TestRedisCache:
    """Unit tests for Redis cache."""

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_redis_get_set(self):
        """Test Redis get/set operations."""
        from memory.redis_cache import RedisCache

        cache = RedisCache()
        await cache.initialize()

        # Set value
        await cache.set("test_collection", "test_query", [{"test": "data"}])

        # Get value
        result = await cache.get("test_collection", "test_query")

        assert result is not None
        assert result[0]["test"] == "data"

        await cache.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_redis_clear_collection(self):
        """Test clearing collection cache."""
        from memory.redis_cache import RedisCache

        cache = RedisCache()
        await cache.initialize()

        # Set value
        await cache.set("test_collection", "query1", [{"test": "data1"}])
        await cache.set("test_collection", "query2", [{"test": "data2"}])

        # Clear collection
        await cache.clear_collection("test_collection")

        # Values should be gone
        result1 = await cache.get("test_collection", "query1")
        result2 = await cache.get("test_collection", "query2")

        assert result1 is None
        assert result2 is None

        await cache.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_redis_hit_rate_tracking(self):
        """Test cache hit rate tracking."""
        from memory.redis_cache import RedisCache

        cache = RedisCache()
        await cache.initialize()

        # Miss
        await cache.get("test_collection", "nonexistent")

        # Set
        await cache.set("test_collection", "exists", [{"test": "data"}])

        # Hit
        await cache.get("test_collection", "exists")

        # Check stats
        stats = cache.get_stats()

        assert stats["total_requests"] >= 2
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1

        await cache.close()
