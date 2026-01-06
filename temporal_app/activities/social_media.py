"""
Social media activities - wraps MCP tools as Temporal activities.
"""
from temporalio import activity
from typing import Dict, Any
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from temporal_app.monitoring import observe_activity

logger = logging.getLogger(__name__)

@activity.defn
async def get_random_unused_photo(brand: str) -> Dict[str, Any]:
    """
    Get random unused product photo from S3.

    Wraps: mcp__feed-publisher-mcp__get_random_unused_photo
    """
    activity.logger.info(f"Getting random photo for brand: {brand}")

    # Import MCP tool dynamically
    try:
        # Simulate MCP call - in real scenario, you'd call the actual MCP server
        # For now, we'll use a placeholder that calls the HTTP API
        import httpx

        # Assuming MCP server runs as service or we can call it directly
        # This is a simplified version - adjust based on actual MCP setup
        result = {
            "key": "products/example_photo.jpg",
            "url": "https://s3.amazonaws.com/bucket/products/example_photo.jpg",
            "brand": brand
        }

        activity.heartbeat(f"Photo selected: {result.get('key')}")

        return result
    except Exception as e:
        activity.logger.error(f"Failed to get random photo: {e}")
        raise

@activity.defn
async def view_image(s3_key: str) -> Dict[str, Any]:
    """
    View/analyze image from S3.

    Wraps: mcp__feed-publisher-mcp__view_image
    """
    activity.logger.info(f"Viewing image: {s3_key}")

    try:
        # Placeholder - in real scenario, call MCP tool
        result = {
            "description": "Elegant three-piece suit in burgundy color",
            "key": s3_key
        }

        return result
    except Exception as e:
        activity.logger.error(f"Failed to view image: {e}")
        raise

@activity.defn
@observe_activity
async def generate_caption(
    image_description: str,
    brand: str,
    language: str = "nl"
) -> str:
    """
    Generate social media caption using Claude.

    This is an AI task - might take 10-30 seconds.
    """
    activity.logger.info(f"Generating {language} caption for {brand}")

    try:
        from claude_agent_sdk import query, ClaudeAgentOptions

        prompt = f"""Create a compelling {language.upper()} social media caption for this product:

Product: {image_description}
Brand: {brand}
Language: {language}

Requirements:
- Engaging and authentic
- Include product highlights
- Add call-to-action
- Include appointment link: https://pomandi.com/default-channel/appointment?locale={language}
- Max 2200 characters
- Natural and conversational tone

Return ONLY the caption text, no explanations.
"""

        options = ClaudeAgentOptions(
            system_prompt="You are a social media marketing expert specializing in fashion and formal wear.",
            max_turns=1,
        )

        caption = ""
        async for message in query(prompt=prompt, options=options):
            if hasattr(message, 'content'):
                for block in message.content:
                    if hasattr(block, 'text'):
                        caption += block.text

        activity.heartbeat("Caption generated")

        return caption.strip()
    except Exception as e:
        activity.logger.error(f"Failed to generate caption: {e}")
        raise

@activity.defn
async def publish_facebook_photo(
    brand: str,
    image_url: str,
    caption: str
) -> Dict[str, Any]:
    """
    Publish photo to Facebook.

    Wraps: mcp__feed-publisher-mcp__publish_facebook_photo
    """
    activity.logger.info(f"Publishing to Facebook for {brand}")

    try:
        # Placeholder - in real scenario, call MCP tool
        result = {
            "success": True,
            "post_id": f"fb_post_{brand}_123456",
            "brand": brand
        }

        activity.heartbeat(f"FB post created: {result.get('post_id')}")

        return result
    except Exception as e:
        activity.logger.error(f"Failed to publish to Facebook: {e}")
        raise

@activity.defn
async def publish_instagram_photo(
    brand: str,
    image_url: str,
    caption: str
) -> Dict[str, Any]:
    """
    Publish photo to Instagram.

    Wraps: mcp__feed-publisher-mcp__publish_instagram_photo
    """
    activity.logger.info(f"Publishing to Instagram for {brand}")

    try:
        # Placeholder - in real scenario, call MCP tool
        result = {
            "success": True,
            "media_id": f"ig_media_{brand}_789012",
            "brand": brand
        }

        activity.heartbeat(f"IG post created: {result.get('media_id')}")

        return result
    except Exception as e:
        activity.logger.error(f"Failed to publish to Instagram: {e}")
        raise

@activity.defn
async def save_publication_report(
    brand: str,
    photo_key: str,
    facebook_post_id: str,
    instagram_media_id: str,
    caption: str
) -> Dict[str, Any]:
    """
    Save publication report to database.

    Wraps: mcp__agent-outputs-mcp__save_output
    """
    activity.logger.info("Saving publication report")

    try:
        import json
        from datetime import datetime

        content = {
            "brand": brand,
            "photo_key": photo_key,
            "facebook_post_id": facebook_post_id,
            "instagram_media_id": instagram_media_id,
            "caption_preview": caption[:100] + "...",
            "published_at": datetime.utcnow().isoformat()
        }

        # Placeholder - in real scenario, call MCP tool
        result = {
            "success": True,
            "report_id": "report_123",
            "content": content
        }

        return result
    except Exception as e:
        activity.logger.error(f"Failed to save report: {e}")
        raise
