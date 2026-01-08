"""
Feed Publisher Graph
====================

LangGraph implementation for social media feed publishing with memory.

Workflow:
1. Check caption history (avoid duplicates)
2. View image from S3
3. Generate caption (NL for Pomandi, FR for Costume)
4. Quality check (brand consistency)
5. Decision: auto-publish / human-review
6. Publish to Facebook/Instagram
7. Save caption to memory

Quality thresholds:
- Score >= 0.85: Auto-publish
- Score >= 0.70: Human review
- Score < 0.70: Reject (regenerate)
"""

from typing import Dict, Any, Optional
from datetime import datetime
from langgraph.graph import StateGraph, END
import structlog

from .base_graph import BaseAgentGraph
from .state_schemas import FeedPublisherState, init_feed_publisher_state

logger = structlog.get_logger(__name__)


class FeedPublisherGraph(BaseAgentGraph):
    """
    Social media feed publisher with memory-aware duplicate detection.

    Flow:
        START
          ↓
        Check Caption History
          ↓
        View Image (S3)
          ↓
        Generate Caption
          ↓
        Quality Check
          ↓
        Decision Node → auto_publish / human_review / reject
          ↓
        Publish (if approved)
          ↓
        Save to Memory
          ↓
        END
    """

    def build_graph(self) -> StateGraph:
        """Build feed publisher graph."""
        # Create graph with state schema
        graph = StateGraph(FeedPublisherState)

        # Add nodes
        graph.add_node("check_history", self.check_caption_history_node)
        graph.add_node("view_image", self.view_image_node)
        graph.add_node("generate_caption", self.generate_caption_node)
        graph.add_node("quality_check", self.quality_check_node)
        graph.add_node("publish", self.publish_node)
        graph.add_node("save_memory", self.save_memory_node)

        # Define edges
        graph.set_entry_point("check_history")
        graph.add_edge("check_history", "view_image")
        graph.add_edge("view_image", "generate_caption")
        graph.add_edge("generate_caption", "quality_check")

        # Conditional routing based on quality
        graph.add_conditional_edges(
            "quality_check",
            self.decision_router,
            {
                "publish": "publish",
                "human_review": "save_memory",  # Skip publish, save for review
                "reject": END  # End without publishing
            }
        )

        graph.add_edge("publish", "save_memory")
        graph.add_edge("save_memory", END)

        return graph

    async def check_caption_history_node(
        self,
        state: FeedPublisherState
    ) -> FeedPublisherState:
        """
        Node: Check memory for similar captions to avoid duplicates.

        Args:
            state: Current state

        Returns:
            Updated state with similar_captions and duplicate_detected
        """
        brand = state["brand"]
        platform = state["platform"]

        # Build query for similar captions
        query = f"{brand} {platform} social media post"

        # Search memory for similar captions (last 30 days)
        results = await self.search_memory(
            collection="social_posts",
            query=query,
            top_k=10,
            filters={
                "brand": brand,
                "platform": platform
            }
        )

        state["similar_captions"] = results

        # Check for duplicates (similarity > 90%)
        if results and results[0]["score"] > 0.90:
            state["duplicate_detected"] = True
            state["similarity_score"] = results[0]["score"]
            state = self.add_warning(
                state,
                f"Very similar caption found (similarity: {results[0]['score']:.2%})"
            )
        else:
            state["duplicate_detected"] = False
            state["similarity_score"] = results[0]["score"] if results else 0.0

        state = self.add_step(state, "check_history")

        logger.info(
            "caption_history_checked",
            brand=brand,
            platform=platform,
            similar_count=len(results),
            duplicate_detected=state["duplicate_detected"]
        )

        return state

    async def view_image_node(
        self,
        state: FeedPublisherState
    ) -> FeedPublisherState:
        """
        Node: Fetch image from S3 and describe it.

        Args:
            state: Current state

        Returns:
            Updated state with image_description
        """
        photo_s3_key = state["photo_s3_key"]

        # TODO: Implement actual S3 fetch and image description
        # For now, extract product info from S3 key
        # Example: "products/pomandi/blazer-navy-001.jpg"

        image_description = f"Product image from S3: {photo_s3_key}"

        # Store in state (add to schema if needed)
        if "image_description" not in state:
            state["image_description"] = image_description

        state = self.add_step(state, "view_image")

        logger.info(
            "image_viewed",
            s3_key=photo_s3_key,
            description_length=len(image_description)
        )

        return state

    async def generate_caption_node(
        self,
        state: FeedPublisherState
    ) -> FeedPublisherState:
        """
        Node: Generate caption based on brand and language.

        Args:
            state: Current state

        Returns:
            Updated state with caption and caption_language
        """
        brand = state["brand"]
        platform = state["platform"]
        image_desc = state.get("image_description", "")
        similar_captions = state["similar_captions"]

        # Determine language
        language = "nl" if brand == "pomandi" else "fr"
        state["caption_language"] = language

        # Build context from similar captions
        similar_context = "\n".join([
            f"- {cap['payload'].get('caption_text', '')[:100]}"
            for cap in similar_captions[:3]
        ]) if similar_captions else "No similar captions in history"

        # Build prompt for caption generation
        prompt = f"""Generate a {language.upper()} social media caption for {brand}:

Image: {image_desc}
Platform: {platform}
Brand voice: {"Casual, trendy, Dutch audience" if brand == "pomandi" else "Elegant, sophisticated, French audience"}

Similar past captions (avoid duplication):
{similar_context}

Requirements:
1. Language: {language.upper()} only
2. Length: 50-150 characters
3. Include brand personality
4. Add relevant emojis (2-3)
5. Call-to-action if appropriate

Return plain text caption only."""

        # TODO: Use Claude Agent SDK for actual caption generation
        # For now, use simple template
        if brand == "pomandi":
            caption = f"✨ Nieuw binnen! Perfect voor jouw stijl 🛍️ #Pomandi #Fashion"
        else:
            caption = f"✨ Nouveau! L'élégance à la française 🇫🇷 #Costume #Mode"

        state["caption"] = caption

        state = self.add_step(state, "generate_caption")

        logger.info(
            "caption_generated",
            brand=brand,
            language=language,
            caption_length=len(caption),
            caption_preview=caption[:50]
        )

        return state

    async def quality_check_node(
        self,
        state: FeedPublisherState
    ) -> FeedPublisherState:
        """
        Node: Check caption quality and brand consistency.

        Args:
            state: Current state

        Returns:
            Updated state with quality_score and requires_approval
        """
        caption = state["caption"]
        brand = state["brand"]
        language = state["caption_language"]
        duplicate_detected = state["duplicate_detected"]

        # Quality scoring (rule-based for now)
        score = 1.0

        # Check 1: Language consistency
        if language == "nl":
            # Simple Dutch word check
            dutch_words = ["nieuw", "voor", "jouw", "binnen", "naar"]
            if not any(word in caption.lower() for word in dutch_words):
                score -= 0.3
                state = self.add_warning(state, "Caption may not be in Dutch")
        elif language == "fr":
            # Simple French word check
            french_words = ["nouveau", "pour", "votre", "dans", "à"]
            if not any(word in caption.lower() for word in french_words):
                score -= 0.3
                state = self.add_warning(state, "Caption may not be in French")

        # Check 2: Length
        if len(caption) < 30:
            score -= 0.2
            state = self.add_warning(state, "Caption too short")
        elif len(caption) > 200:
            score -= 0.1
            state = self.add_warning(state, "Caption too long")

        # Check 3: Brand mention
        if brand.lower() not in caption.lower():
            score -= 0.2
            state = self.add_warning(state, "Brand name not mentioned")

        # Check 4: Emoji presence
        emoji_count = sum(1 for char in caption if ord(char) > 127)
        if emoji_count == 0:
            score -= 0.1
            state = self.add_warning(state, "No emojis used")

        # Check 5: Duplicate penalty
        if duplicate_detected:
            score -= 0.3
            state = self.add_warning(state, "Caption very similar to recent post")

        state["caption_quality_score"] = max(0.0, score)

        # Determine if requires approval
        if state["caption_quality_score"] >= 0.85:
            state["requires_approval"] = False
        elif state["caption_quality_score"] >= 0.70:
            state["requires_approval"] = True
        else:
            state["requires_approval"] = True
            state["rejection_reason"] = "Quality score too low"

        state = self.add_step(state, "quality_check")

        logger.info(
            "quality_checked",
            brand=brand,
            quality_score=state["caption_quality_score"],
            requires_approval=state["requires_approval"]
        )

        return state

    def decision_router(self, state: FeedPublisherState) -> str:
        """
        Routing function: Decide next node based on quality.

        Args:
            state: Current state

        Returns:
            Next node name ("publish", "human_review", or "reject")
        """
        quality_score = state["caption_quality_score"]
        rejection_reason = state.get("rejection_reason")

        if rejection_reason:
            logger.warning("post_rejected", reason=rejection_reason)
            return "reject"

        if quality_score >= 0.85:
            logger.info("post_approved_auto", quality_score=quality_score)
            return "publish"
        elif quality_score >= 0.70:
            logger.info("post_requires_review", quality_score=quality_score)
            return "human_review"
        else:
            logger.warning("post_quality_too_low", quality_score=quality_score)
            return "reject"

    async def publish_node(
        self,
        state: FeedPublisherState
    ) -> FeedPublisherState:
        """
        Node: Publish caption to Facebook/Instagram.

        Args:
            state: Current state

        Returns:
            Updated state with post IDs
        """
        brand = state["brand"]
        platform = state["platform"]
        caption = state["caption"]
        photo_s3_key = state["photo_s3_key"]

        # TODO: Use MCP social-media-publisher to actually publish
        # For now, simulate publishing
        if platform == "facebook":
            state["facebook_post_id"] = f"fb_{brand}_{datetime.now().timestamp()}"
        elif platform == "instagram":
            state["instagram_post_id"] = f"ig_{brand}_{datetime.now().timestamp()}"

        state["published_at"] = datetime.now()

        state = self.add_step(state, "publish")

        logger.info(
            "post_published",
            brand=brand,
            platform=platform,
            post_id=state.get("facebook_post_id") or state.get("instagram_post_id"),
            caption_preview=caption[:50]
        )

        return state

    async def save_memory_node(
        self,
        state: FeedPublisherState
    ) -> FeedPublisherState:
        """
        Node: Save caption to memory for future reference.

        Args:
            state: Current state

        Returns:
            Updated state
        """
        # Build content for embedding
        content = f"""{state['brand']} {state['platform']} post:
Caption: {state['caption']}
Quality: {state['caption_quality_score']:.2%}
Published: {state.get('published_at', 'Not published')}
"""

        # Save to social_posts collection
        await self.save_to_memory(
            collection="social_posts",
            content=content,
            metadata={
                "brand": state["brand"],
                "platform": state["platform"],
                "caption_text": state["caption"],
                "caption_language": state["caption_language"],
                "quality_score": state["caption_quality_score"],
                "published": state.get("published_at") is not None,
                "facebook_post_id": state.get("facebook_post_id"),
                "instagram_post_id": state.get("instagram_post_id"),
                "photo_s3_key": state["photo_s3_key"]
            }
        )

        state = self.add_step(state, "save_memory")

        logger.info("caption_saved_to_memory", brand=state["brand"])

        return state

    # Public API

    async def publish(
        self,
        brand: str,
        platform: str,
        photo_s3_key: str
    ) -> Dict[str, Any]:
        """
        Publish social media post.

        Args:
            brand: "pomandi" or "costume"
            platform: "facebook" or "instagram"
            photo_s3_key: S3 key for photo

        Returns:
            Publishing result with post IDs
        """
        # Initialize state
        initial_state = init_feed_publisher_state(brand, platform, photo_s3_key)

        # Run graph
        final_state = await self.run(**initial_state)

        # Return result
        return {
            "published": final_state.get("published_at") is not None,
            "facebook_post_id": final_state.get("facebook_post_id"),
            "instagram_post_id": final_state.get("instagram_post_id"),
            "caption": final_state.get("caption", ""),
            "quality_score": final_state.get("caption_quality_score", 0.0),
            "requires_approval": final_state.get("requires_approval", True),
            "rejection_reason": final_state.get("rejection_reason"),
            "duplicate_detected": final_state.get("duplicate_detected", False),
            "warnings": final_state.get("warnings", []),
            "steps_completed": final_state.get("steps_completed", [])
        }
