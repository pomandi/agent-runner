"""
Pytest configuration for agent-runner tests.
"""
import pytest
import os
import sys
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_env():
    """Test environment variables."""
    return {
        "ENABLE_MEMORY": os.getenv("ENABLE_MEMORY", "false"),
        "ENABLE_LANGGRAPH": os.getenv("ENABLE_LANGGRAPH", "false"),
        "QDRANT_HOST": os.getenv("QDRANT_HOST", "localhost"),
        "REDIS_HOST": os.getenv("REDIS_HOST", "localhost"),
    }


@pytest.fixture
async def memory_manager():
    """Fixture for memory manager."""
    if os.getenv("ENABLE_MEMORY") != "true":
        pytest.skip("Memory layer not enabled")

    from memory import MemoryManager

    manager = MemoryManager()
    await manager.initialize()

    yield manager

    await manager.close()


@pytest.fixture
async def invoice_matcher_graph():
    """Fixture for invoice matcher graph."""
    if os.getenv("ENABLE_LANGGRAPH") != "true":
        pytest.skip("LangGraph not enabled")

    from langgraph_agents import InvoiceMatcherGraph

    graph = InvoiceMatcherGraph()
    await graph.initialize()

    yield graph

    await graph.close()


@pytest.fixture
async def feed_publisher_graph():
    """Fixture for feed publisher graph."""
    if os.getenv("ENABLE_LANGGRAPH") != "true":
        pytest.skip("LangGraph not enabled")

    from langgraph_agents import FeedPublisherGraph

    graph = FeedPublisherGraph()
    await graph.initialize()

    yield graph

    await graph.close()


# Pytest markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
