"""
Feed Publisher Workflow (LangGraph Version) - Memory-aware posting with duplicate detection.

This workflow uses LangGraph for:
- Caption history checking (avoid duplicates)
- Quality assessment (brand consistency)
- Decision routing (auto-publish vs human review)
- Memory persistence (save captions for future reference)
"""
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any
import logging

# Import activities
with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.social_media import get_random_unused_photo
    from temporal_app.activities.langgraph_activities import run_feed_publisher_graph
    from temporal_app.monitoring import observe_workflow

logger = logging.getLogger(__name__)


@workflow.defn
class FeedPublisherLangGraphWorkflow:
    """
    LangGraph-powered feed publisher workflow with memory.

    Flow:
    1. Get random unused photo from S3 (existing activity)
    2. Run FeedPublisherGraph (LangGraph):
       - Check caption history
       - View image
       - Generate caption
       - Quality check
       - Decision routing
       - Publish (if approved)
       - Save to memory
    3. Return result

    Features:
    - Memory-aware duplicate detection
    - Quality-based decision routing
    - Human review queue for low-quality posts
    - Caption history persistence
    """

    @workflow.run
    async def run(self, brand: str = "pomandi", platform: str = "facebook") -> Dict[str, Any]:
        """
        Execute the LangGraph-powered feed publishing workflow.

        Args:
            brand: Brand name (pomandi or costume)
            platform: Platform to publish to (facebook or instagram)

        Returns:
            Publication results with status and IDs
        """
        workflow.logger.info(f"🚀 Starting LangGraph feed publisher for {brand} on {platform}")

        try:
            # Step 1: Get random unused photo (reuse existing activity)
            workflow.logger.info("📸 Step 1: Getting random photo...")
            photo_data = await workflow.execute_activity(
                get_random_unused_photo,
                args=[brand],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=10),
                    maximum_interval=timedelta(seconds=60),
                    backoff_coefficient=2.0,
                ),
            )

            photo_key = photo_data["key"]
            workflow.logger.info(f"✅ Selected photo: {photo_key}")

            # Step 2: Run LangGraph workflow
            workflow.logger.info("🤖 Step 2: Running LangGraph feed publisher...")
            graph_result = await workflow.execute_activity(
                run_feed_publisher_graph,
                args=[brand, platform, photo_key],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(seconds=30),
                ),
            )

            workflow.logger.info(
                f"✅ LangGraph complete - "
                f"Published: {graph_result['published']}, "
                f"Quality: {graph_result['quality_score']:.2%}, "
                f"Requires approval: {graph_result['requires_approval']}"
            )

            # Build final result
            result = {
                "success": graph_result["published"],
                "brand": brand,
                "platform": platform,
                "photo_key": photo_key,
                "caption": graph_result["caption"],
                "caption_preview": graph_result["caption"][:100] + "..." if len(graph_result["caption"]) > 100 else graph_result["caption"],
                "quality_score": graph_result["quality_score"],
                "requires_approval": graph_result["requires_approval"],
                "rejection_reason": graph_result.get("rejection_reason"),
                "duplicate_detected": graph_result["duplicate_detected"],
                "warnings": graph_result["warnings"],
                "facebook_post_id": graph_result.get("facebook_post_id"),
                "instagram_post_id": graph_result.get("instagram_post_id"),
                "published_at": workflow.now().isoformat() if graph_result["published"] else None,
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
                "steps_completed": graph_result["steps_completed"]
            }

            # Log different outcomes
            if result["success"]:
                workflow.logger.info("🎉 Feed publisher workflow completed - Post published!")
            elif result["requires_approval"]:
                workflow.logger.warning("⚠️  Feed publisher workflow completed - Post requires human review")
            else:
                workflow.logger.error(f"❌ Feed publisher workflow completed - Post rejected: {result['rejection_reason']}")

            return result

        except Exception as e:
            workflow.logger.error(f"❌ LangGraph workflow failed: {e}")
            raise
