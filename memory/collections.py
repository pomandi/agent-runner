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
    EMAIL_PATTERNS = "email_patterns"
    EMAIL_CONVERSATIONS = "email_conversations"
    SEO_STRATEGIES = "seo_strategies"
    ANALYTICS_DATA = "analytics_data"
    ACTION_HISTORY = "action_history"


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
    },

    CollectionName.EMAIL_PATTERNS: {
        "vectors_config": VectorParams(
            size=1536,
            distance=Distance.COSINE
        ),
        "schema": {
            "sender_email": "str",
            "sender_domain": "str",
            "subject_pattern": "str",
            "response_template": "str",
            "response_tone": "str",  # "formal", "casual", "professional"
            "avg_response_time_minutes": "int",
            "usage_count": "int",
            "success_rate": "float",  # 0-1
            "last_used": "str",  # ISO datetime
            "created_at": "str"  # ISO datetime
        },
        "description": "Learned email response patterns for auto-reply"
    },

    CollectionName.EMAIL_CONVERSATIONS: {
        "vectors_config": VectorParams(
            size=1536,
            distance=Distance.COSINE
        ),
        "schema": {
            "thread_id": "str",
            "sender_email": "str",
            "subject": "str",
            "conversation_summary": "str",
            "last_response": "str",
            "response_date": "str",  # ISO datetime
            "sentiment": "str",  # "positive", "negative", "neutral"
            "context_tags": "list[str]",  # ["work", "urgent", "meeting"]
            "created_at": "str"  # ISO datetime
        },
        "description": "Email conversation history for context-aware responses"
    },

    CollectionName.SEO_STRATEGIES: {
        "vectors_config": VectorParams(
            size=1536,
            distance=Distance.COSINE
        ),
        "schema": {
            "keyword": "str",  # Target keyword
            "slug": "str",  # Generated page slug
            "template": "str",  # location, style, promo
            "generated_date": "str",  # ISO date
            "search_console_position": "float",  # Position at generation time
            "search_console_impressions": "int",  # Impressions at generation time
            "current_position": "float",  # Latest position (updated weekly)
            "current_clicks": "int",  # Latest weekly clicks
            "performance_trend": "str",  # "improving", "stable", "declining"
            "optimization_notes": "str",  # Recommendations
            "created_at": "str"  # ISO datetime
        },
        "description": "SEO landing page strategies and performance tracking"
    },

    CollectionName.ANALYTICS_DATA: {
        "vectors_config": VectorParams(
            size=1536,
            distance=Distance.COSINE
        ),
        "schema": {
            "brand": "str",  # pomandi, costume
            "date": "str",  # YYYY-MM-DD
            "total_spend": "float",
            "total_revenue": "float",
            "roas": "float",
            "quality_score": "float",  # 0-1 validation score
            "sources_count": "int",  # Number of data sources
            "data_hash": "str",  # Deduplication hash
            "summary": "str",  # Human-readable summary
            "created_at": "str"  # ISO datetime
        },
        "description": "Daily analytics summaries for semantic search and trend analysis"
    },

    CollectionName.ACTION_HISTORY: {
        "vectors_config": VectorParams(
            size=1536,
            distance=Distance.COSINE
        ),
        "schema": {
            "action_type": "str",  # budget_change, bid_adjustment, pause_campaign, etc.
            "platform": "str",  # google_ads, meta_ads, shopify, etc.
            "brand": "str",  # pomandi, costume
            "plan_id": "str",  # Unique plan identifier
            "result": "str",  # success, failed, pending, approved, rejected
            "impact_value": "float",  # Numeric impact (spend change, ROAS change)
            "date": "str",  # YYYY-MM-DD
            "reasoning": "str",  # Why this action was taken
            "created_at": "str"  # ISO datetime
        },
        "description": "Action plan history for learning from past decisions and outcomes"
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
