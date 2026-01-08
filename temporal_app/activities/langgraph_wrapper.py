"""
LangGraph Wrapper Activity
==========================

Wraps LangGraph FeedPublisherGraph as a Temporal activity.
This allows Temporal to handle scheduling, retries, persistence
while LangGraph handles complex decision-making and memory.
"""

from temporalio import activity
from typing import Dict, Any, Optional
import structlog
import os

logger = structlog.get_logger(__name__)

# Lazy imports for LangGraph to avoid import issues in worker
_feed_publisher_graph = None


async def get_feed_publisher_graph():
    """Lazy load FeedPublisherGraph."""
    global _feed_publisher_graph

    if _feed_publisher_graph is None:
        from langgraph_agents.feed_publisher_graph import FeedPublisherGraph
        _feed_publisher_graph = FeedPublisherGraph(enable_memory=True)
        await _feed_publisher_graph.initialize()
        logger.info("langgraph_feed_publisher_initialized")

    return _feed_publisher_graph


@activity.defn
async def run_langgraph_feed_publisher(
    brand: str,
    platform: str,
    photo_s3_key: str,
    image_url: str,
    image_description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run LangGraph feed publisher with memory-aware duplicate detection.

    This activity wraps the LangGraph FeedPublisherGraph which provides:
    - Caption history checking (avoid duplicates)
    - Quality scoring (language, length, brand, emoji)
    - Decision routing (auto-publish / human-review / reject)
    - Memory persistence for future reference

    Args:
        brand: "pomandi" or "costume"
        platform: "facebook" or "instagram"
        photo_s3_key: S3 key for the photo
        image_url: Public URL for the photo
        image_description: Optional pre-analyzed image description

    Returns:
        Dict with:
            - published: bool
            - caption: str
            - quality_score: float
            - decision: "auto_publish" | "human_review" | "reject"
            - facebook_post_id: Optional[str]
            - instagram_post_id: Optional[str]
            - warnings: List[str]
    """
    activity.logger.info(
        f"Starting LangGraph feed publisher for {brand}/{platform}"
    )

    try:
        # Check if memory is enabled
        memory_enabled = os.getenv("ENABLE_MEMORY", "false").lower() == "true"

        if not memory_enabled:
            activity.logger.warning(
                "Memory disabled - LangGraph will work without duplicate detection"
            )

        # Get the graph instance
        graph = await get_feed_publisher_graph()

        # Run the graph
        result = await graph.publish(
            brand=brand,
            platform=platform,
            photo_s3_key=photo_s3_key
        )

        # Determine decision type
        if result.get("rejection_reason"):
            decision = "reject"
        elif result.get("requires_approval"):
            decision = "human_review"
        else:
            decision = "auto_publish"

        activity.logger.info(
            f"LangGraph completed: decision={decision}, "
            f"quality={result.get('quality_score', 0):.2f}, "
            f"duplicate={result.get('duplicate_detected', False)}"
        )

        return {
            "published": result.get("published", False),
            "caption": result.get("caption", ""),
            "quality_score": result.get("quality_score", 0.0),
            "decision": decision,
            "facebook_post_id": result.get("facebook_post_id"),
            "instagram_post_id": result.get("instagram_post_id"),
            "duplicate_detected": result.get("duplicate_detected", False),
            "warnings": result.get("warnings", []),
            "steps_completed": result.get("steps_completed", [])
        }

    except Exception as e:
        activity.logger.error(f"LangGraph feed publisher failed: {e}")
        raise


@activity.defn
async def check_caption_quality(
    caption: str,
    brand: str,
    language: str
) -> Dict[str, Any]:
    """
    Standalone quality check activity (can be used without full LangGraph).

    Quality criteria:
    - Language consistency (Dutch/French words present)
    - Caption length (30-200 chars optimal)
    - Brand mention
    - Emoji presence

    Args:
        caption: The caption to check
        brand: Brand name
        language: "nl" or "fr"

    Returns:
        Dict with quality_score, passed, warnings
    """
    score = 1.0
    warnings = []

    # Check 1: Language consistency
    if language == "nl":
        dutch_words = ["nieuw", "voor", "jouw", "binnen", "naar", "de", "het", "een"]
        if not any(word in caption.lower() for word in dutch_words):
            score -= 0.3
            warnings.append("Caption may not be in Dutch")
    elif language == "fr":
        french_words = ["nouveau", "pour", "votre", "dans", "à", "la", "le", "un"]
        if not any(word in caption.lower() for word in french_words):
            score -= 0.3
            warnings.append("Caption may not be in French")

    # Check 2: Length
    if len(caption) < 30:
        score -= 0.2
        warnings.append("Caption too short")
    elif len(caption) > 200:
        score -= 0.1
        warnings.append("Caption too long")

    # Check 3: Brand mention
    if brand.lower() not in caption.lower():
        score -= 0.2
        warnings.append("Brand name not mentioned")

    # Check 4: Emoji presence
    emoji_count = sum(1 for char in caption if ord(char) > 127)
    if emoji_count == 0:
        score -= 0.1
        warnings.append("No emojis used")

    final_score = max(0.0, score)

    return {
        "quality_score": final_score,
        "passed": final_score >= 0.70,
        "auto_approved": final_score >= 0.85,
        "warnings": warnings
    }


@activity.defn
async def check_caption_duplicate(
    brand: str,
    platform: str,
    caption: str
) -> Dict[str, Any]:
    """
    Check if caption is too similar to recent posts using memory.

    Args:
        brand: Brand name
        platform: Platform name
        caption: Caption to check

    Returns:
        Dict with is_duplicate, similarity_score, similar_caption
    """
    memory_enabled = os.getenv("ENABLE_MEMORY", "false").lower() == "true"

    if not memory_enabled:
        return {
            "is_duplicate": False,
            "similarity_score": 0.0,
            "similar_caption": None,
            "memory_enabled": False
        }

    try:
        from memory import get_memory_manager

        manager = await get_memory_manager()

        # Search for similar captions
        results = await manager.search(
            collection="social_posts",
            query=caption,
            top_k=5,
            filters={
                "brand": brand,
                "platform": platform
            }
        )

        if results and results[0]["score"] > 0.90:
            return {
                "is_duplicate": True,
                "similarity_score": results[0]["score"],
                "similar_caption": results[0]["payload"].get("caption_text", ""),
                "memory_enabled": True
            }

        return {
            "is_duplicate": False,
            "similarity_score": results[0]["score"] if results else 0.0,
            "similar_caption": None,
            "memory_enabled": True
        }

    except Exception as e:
        logger.error(f"Duplicate check failed: {e}")
        return {
            "is_duplicate": False,
            "similarity_score": 0.0,
            "similar_caption": None,
            "memory_enabled": True,
            "error": str(e)
        }
