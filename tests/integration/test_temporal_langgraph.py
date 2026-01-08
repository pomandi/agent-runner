"""
Integration tests for Temporal + LangGraph workflows.

Tests:
1. Memory layer initialization
2. LangGraph execution via Temporal activities
3. End-to-end workflow execution
4. Error handling and retries
"""
import pytest
import asyncio
import os
from datetime import datetime

# Test configurations
pytestmark = pytest.mark.asyncio


class TestMemoryLayerIntegration:
    """Test memory layer initialization and operations."""

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
    async def test_memory_save_and_search(self):
        """Test saving and searching in memory."""
        from memory import MemoryManager

        manager = MemoryManager()
        await manager.initialize()

        # Save test document
        doc_id = await manager.save(
            collection="agent_context",
            content="Test integration document for LangGraph workflow",
            metadata={
                "test": True,
                "agent_name": "test_agent",
                "timestamp": datetime.now().isoformat()
            }
        )

        assert doc_id > 0

        # Search for document
        results = await manager.search(
            collection="agent_context",
            query="LangGraph workflow test",
            top_k=5
        )

        assert len(results) > 0
        assert results[0]["score"] > 0.5

        await manager.close()


class TestLangGraphActivities:
    """Test LangGraph activities can be called."""

    @pytest.mark.skipif(
        os.getenv('ENABLE_LANGGRAPH') != 'true',
        reason="LangGraph not enabled"
    )
    async def test_invoice_matcher_graph_activity(self):
        """Test invoice matcher graph activity."""
        from temporal_app.activities.langgraph_activities import run_invoice_matcher_graph

        # Test data
        transaction = {
            "id": 1,
            "vendorName": "Test Vendor",
            "amount": 100.00,
            "date": "2024-01-08",
            "communication": "Test transaction"
        }

        invoices = [
            {
                "id": 101,
                "vendorName": "Test Vendor",
                "amount": 100.00,
                "date": "2024-01-05"
            },
            {
                "id": 102,
                "vendorName": "Other Vendor",
                "amount": 50.00,
                "date": "2024-01-06"
            }
        ]

        # Run activity (without Temporal context for unit test)
        # Note: This would normally be called through Temporal
        result = await run_invoice_matcher_graph(transaction, invoices)

        assert "matched" in result
        assert "confidence" in result
        assert "decision_type" in result
        assert result["decision_type"] in ["auto_match", "human_review", "no_match"]

    @pytest.mark.skipif(
        os.getenv('ENABLE_LANGGRAPH') != 'true',
        reason="LangGraph not enabled"
    )
    async def test_feed_publisher_graph_activity(self):
        """Test feed publisher graph activity."""
        from temporal_app.activities.langgraph_activities import run_feed_publisher_graph

        # Test data
        brand = "pomandi"
        platform = "facebook"
        photo_s3_key = "products/test-product.jpg"

        # Run activity (without Temporal context for unit test)
        result = await run_feed_publisher_graph(brand, platform, photo_s3_key)

        assert "published" in result
        assert "caption" in result
        assert "quality_score" in result
        assert "requires_approval" in result
        assert "duplicate_detected" in result


class TestLangGraphDirectExecution:
    """Test LangGraph workflows directly (without Temporal)."""

    @pytest.mark.skipif(
        os.getenv('ENABLE_LANGGRAPH') != 'true',
        reason="LangGraph not enabled"
    )
    async def test_invoice_matcher_graph_direct(self):
        """Test invoice matcher graph direct execution."""
        from langgraph_agents import InvoiceMatcherGraph

        # Test data
        transaction = {
            "id": 1,
            "vendorName": "SNCB",
            "amount": 22.70,
            "date": "2024-01-08",
            "communication": "Train ticket Brussels-Antwerp"
        }

        invoices = [
            {
                "id": 201,
                "vendorName": "SNCB",
                "amount": 22.70,
                "date": "2024-01-08"
            }
        ]

        # Create and run graph
        graph = InvoiceMatcherGraph()
        await graph.initialize()

        result = await graph.match(transaction, invoices)

        assert result["matched"] is True
        assert result["confidence"] > 0.8  # Should be high match
        assert result["decision_type"] in ["auto_match", "human_review"]
        assert "steps_completed" in result
        assert len(result["steps_completed"]) > 0

        await graph.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_LANGGRAPH') != 'true',
        reason="LangGraph not enabled"
    )
    async def test_feed_publisher_graph_direct(self):
        """Test feed publisher graph direct execution."""
        from langgraph_agents import FeedPublisherGraph

        # Test data
        brand = "pomandi"
        platform = "facebook"
        photo_s3_key = "products/blazer-navy-001.jpg"

        # Create and run graph
        graph = FeedPublisherGraph()
        await graph.initialize()

        result = await graph.publish(brand, platform, photo_s3_key)

        assert "caption" in result
        assert len(result["caption"]) > 0
        assert result["quality_score"] >= 0.0
        assert result["quality_score"] <= 1.0
        assert "duplicate_detected" in result
        assert "steps_completed" in result
        assert len(result["steps_completed"]) > 0

        await graph.close()


class TestMemoryActivities:
    """Test memory activities."""

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_search_memory_activity(self):
        """Test search_memory activity."""
        from temporal_app.activities.memory_activities import search_memory

        results = await search_memory(
            collection="agent_context",
            query="test document",
            top_k=5
        )

        assert isinstance(results, list)

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_save_to_memory_activity(self):
        """Test save_to_memory activity."""
        from temporal_app.activities.memory_activities import save_to_memory

        doc_id = await save_to_memory(
            collection="agent_context",
            content="Integration test document",
            metadata={
                "test": True,
                "timestamp": datetime.now().isoformat()
            }
        )

        assert doc_id > 0

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_get_memory_stats_activity(self):
        """Test get_memory_stats activity."""
        from temporal_app.activities.memory_activities import get_memory_stats

        stats = await get_memory_stats()

        assert "cache" in stats
        assert "collections" in stats
        assert "cache_hit_rate_percent" in stats["cache"] or "hit_rate_percent" in stats["cache"]

    @pytest.mark.skipif(
        os.getenv('ENABLE_MEMORY') != 'true',
        reason="Memory layer not enabled"
    )
    async def test_check_duplicate_activity(self):
        """Test check_duplicate_in_memory activity."""
        from temporal_app.activities.memory_activities import check_duplicate_in_memory

        result = await check_duplicate_in_memory(
            collection="agent_context",
            content="Unique test content for duplicate check",
            similarity_threshold=0.90
        )

        assert "is_duplicate" in result
        assert "similarity_score" in result
        assert isinstance(result["is_duplicate"], bool)


# Pytest configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
