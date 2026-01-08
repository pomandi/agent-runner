"""
Qdrant Collection Schemas
=========================

Defines vector database collections for different data types.
Each collection stores embeddings + metadata for semantic search.
"""

from enum import Enum
from typing import Dict, Any
from qdrant_client.models import Distance, VectorParams


class CollectionName(str, Enum):
    """Memory collection names."""

    INVOICES = "invoices"
    SOCIAL_POSTS = "social_posts"
    AD_REPORTS = "ad_reports"
    AGENT_CONTEXT = "agent_context"


# Collection configurations with vector params and schema
COLLECTION_CONFIGS: Dict[CollectionName, Dict[str, Any]] = {
    CollectionName.INVOICES: {
        "vectors_config": VectorParams(
            size=1536,  # text-embedding-3-small dimensions
            distance=Distance.COSINE
        ),
        "schema": {
            "invoice_id": "int",
            "vendor_name": "str",
            "amount": "float",
            "date": "str",
            "description": "str",
            "file_path": "str",
            "matched": "bool",
            "created_at": "str"
        },
        "description": "Invoice content for semantic matching against bank transactions"
    },

    CollectionName.SOCIAL_POSTS: {
        "vectors_config": VectorParams(
            size=1536,
            distance=Distance.COSINE
        ),
        "schema": {
            "post_id": "str",
            "brand": "str",  # pomandi, costume
            "platform": "str",  # facebook, instagram
            "caption": "str",
            "published_at": "str",
            "engagement_rate": "float",
            "photo_key": "str",
            "created_at": "str"
        },
        "description": "Social media post history for avoiding duplicate content"
    },

    CollectionName.AD_REPORTS: {
        "vectors_config": VectorParams(
            size=1536,
            distance=Distance.COSINE
        ),
        "schema": {
            "campaign_id": "str",
            "campaign_name": "str",
            "date": "str",
            "spend": "float",
            "conversions": "int",
            "roas": "float",
            "insights": "str",
            "created_at": "str"
        },
        "description": "Google Ads performance data for trend analysis"
    },

    CollectionName.AGENT_CONTEXT: {
        "vectors_config": VectorParams(
            size=1536,
            distance=Distance.COSINE
        ),
        "schema": {
            "agent_name": "str",
            "context_type": "str",  # decision, error, success
            "content": "str",
            "timestamp": "str",
            "metadata": "json"
        },
        "description": "General agent execution context for learning from past runs"
    }
}


def get_collection_config(collection_name: str) -> Dict[str, Any]:
    """
    Get configuration for a specific collection.

    Args:
        collection_name: Name of the collection

    Returns:
        Configuration dictionary

    Raises:
        ValueError: If collection name is not defined
    """
    try:
        collection = CollectionName(collection_name)
        return COLLECTION_CONFIGS[collection]
    except ValueError:
        valid_collections = [c.value for c in CollectionName]
        raise ValueError(
            f"Unknown collection '{collection_name}'. "
            f"Valid collections: {', '.join(valid_collections)}"
        )


def get_all_collection_names() -> list[str]:
    """Get list of all defined collection names."""
    return [c.value for c in CollectionName]
