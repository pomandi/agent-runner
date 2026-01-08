#!/usr/bin/env python3
"""
Bootstrap Memory System
======================

Initialize Qdrant collections and verify memory system health.

Usage:
    python scripts/bootstrap_memory.py

Features:
- Creates all required Qdrant collections
- Verifies Redis connectivity
- Tests embedding generation
- Runs health checks
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from memory import MemoryManager
from memory.collections import get_all_collection_names
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger(__name__)


async def main():
    """Bootstrap memory system."""
    print("=" * 60)
    print("Memory System Bootstrap")
    print("=" * 60)
    print()

    # Step 1: Check environment variables
    print("Step 1: Checking environment variables...")
    required_vars = [
        "QDRANT_HOST",
        "REDIS_HOST",
        "OPENAI_API_KEY",
        "EMBEDDING_MODEL"
    ]

    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask API keys
            display_value = value if "KEY" not in var else f"{value[:10]}..."
            print(f"  ✓ {var} = {display_value}")
        else:
            print(f"  ✗ {var} = NOT SET")
            missing_vars.append(var)

    if missing_vars:
        print(f"\nError: Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set them in .env file or export them.")
        sys.exit(1)

    print()

    # Step 2: Initialize memory manager
    print("Step 2: Initializing memory manager...")
    try:
        manager = MemoryManager()
        await manager.initialize()
        print("  ✓ Memory manager initialized")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        sys.exit(1)

    print()

    # Step 3: Create collections
    print("Step 3: Creating Qdrant collections...")
    collections = get_all_collection_names()

    for collection_name in collections:
        try:
            created = await manager.qdrant_client.create_collection_if_not_exists(collection_name)
            if created:
                print(f"  ✓ Created collection: {collection_name}")
            else:
                print(f"  ℹ Collection already exists: {collection_name}")
        except Exception as e:
            print(f"  ✗ Failed to create {collection_name}: {e}")

    print()

    # Step 4: Test embedding generation
    print("Step 4: Testing embedding generation...")
    try:
        test_text = "This is a test invoice from SNCB for €22.70"
        embedding = await manager.embedding_generator.generate_single(test_text)

        expected_dims = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
        actual_dims = len(embedding)

        if actual_dims == expected_dims:
            print(f"  ✓ Generated {actual_dims}D embedding")
        else:
            print(f"  ⚠ Warning: Expected {expected_dims}D, got {actual_dims}D")

    except Exception as e:
        print(f"  ✗ Embedding generation failed: {e}")

    print()

    # Step 5: Test memory save/search
    print("Step 5: Testing memory operations...")
    try:
        # Save test document
        doc_id = await manager.save(
            collection="agent_context",
            content="Bootstrap test document - Memory system initialized successfully",
            metadata={
                "type": "test",
                "timestamp": "2024-01-08T00:00:00Z"
            }
        )
        print(f"  ✓ Saved test document (ID: {doc_id})")

        # Search for it
        results = await manager.search(
            collection="agent_context",
            query="memory system initialized",
            top_k=1
        )

        if results and results[0]["score"] > 0.8:
            print(f"  ✓ Search working (similarity: {results[0]['score']:.2%})")
        else:
            print(f"  ⚠ Warning: Low search similarity or no results")

    except Exception as e:
        print(f"  ✗ Memory operations failed: {e}")

    print()

    # Step 6: Get system stats
    print("Step 6: Memory system statistics...")
    try:
        stats = await manager.get_system_stats()

        print(f"  Redis cache:")
        cache_stats = stats.get("cache", {})
        print(f"    - Hit rate: {cache_stats.get('hit_rate_percent', 0):.1f}%")
        print(f"    - Total requests: {cache_stats.get('total_requests', 0)}")

        print(f"  Collections:")
        for coll_name, coll_info in stats.get("collections", {}).items():
            if "error" in coll_info:
                print(f"    - {coll_name}: Error")
            else:
                points = coll_info.get("points_count", 0)
                print(f"    - {coll_name}: {points} documents")

    except Exception as e:
        print(f"  ✗ Failed to get stats: {e}")

    print()

    # Step 7: Health check summary
    print("Step 7: Final health check...")
    try:
        qdrant_healthy = await manager.qdrant_client.health_check()
        redis_healthy = await manager.redis_cache.health_check()

        print(f"  Qdrant: {'✓ Healthy' if qdrant_healthy else '✗ Unhealthy'}")
        print(f"  Redis:  {'✓ Healthy' if redis_healthy else '✗ Unhealthy'}")

        if qdrant_healthy and redis_healthy:
            print()
            print("=" * 60)
            print("SUCCESS: Memory system is fully operational!")
            print("=" * 60)
            print()
            print("Next steps:")
            print("1. Run 'docker compose up -d' to start services")
            print("2. Use scripts/backfill_embeddings.py to import existing data")
            print("3. Start using memory in your agents!")
        else:
            print()
            print("⚠ WARNING: Some components are unhealthy")
            print("Check logs and configuration")

    except Exception as e:
        print(f"  ✗ Health check failed: {e}")

    # Cleanup
    await manager.close()


if __name__ == "__main__":
    asyncio.run(main())
