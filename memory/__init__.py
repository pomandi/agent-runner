"""
Memory Layer for Agent System
=============================

Provides three-tier memory architecture:
- Tier 1: Redis (working memory, 24h TTL)
- Tier 2: Qdrant (semantic memory, vector search)
- Tier 3: PostgreSQL (structured data, existing databases)

Usage:
    from memory import MemoryManager

    manager = MemoryManager()
    await manager.save("invoices", "Invoice from SNCB €22.70", metadata={"vendor": "SNCB"})
    results = await manager.search("invoices", "SNCB train ticket")
"""

from .memory_manager import MemoryManager, get_memory_manager
from .collections import CollectionName, COLLECTION_CONFIGS

__all__ = ["MemoryManager", "get_memory_manager", "CollectionName", "COLLECTION_CONFIGS"]
__version__ = "1.0.0"
