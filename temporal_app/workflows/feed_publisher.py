"""
Feed Publisher Workflow - Main daily posting workflow.
"""
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any
import logging
import asyncio

# Import activities
with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.social_media import (
        get_random_unused_photo,
        view_image,
        generate_caption,
        publish_facebook_photo,
        publish_instagram_photo,
        save_publication_report,
    )
    from temporal_app.monitoring import observe_workflow

logger = logging.getLogger(__name__)

@workflow.defn
class FeedPublisherWorkflow:
    """
    Daily social media post publisher workflow.

    Steps:
    1. Get random unused photo from S3
    2. View/analyze the image
    3. Generate AI caption
    4. Publish to Facebook
    5. Publish to Instagram
    6. Save report

    Features:
    - Automatic retry on failures
    - Activity timeout management
    - Parallel publishing to both platforms
    - State persistence (crash recovery)
    """

    @workflow.run
    async def run(self, brand: str = "pomandi") -> Dict[str, Any]:
        """
        Execute the feed publishing workflow.

        Args:
            brand: Brand name (pomandi or costume)

        Returns:
            Publication results with status and IDs
        """
        workflow.logger.info(f"🚀 Starting feed publisher workflow for {brand}")

        # Determine language based on brand
        language = "nl" if brand == "pomandi" else "fr"

        try:
            # Step 1: Get random unused photo
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
            image_url = photo_data["url"]
            workflow.logger.info(f"✅ Selected photo: {photo_key}")

            # Step 2: View/analyze image
            workflow.logger.info("🔍 Step 2: Analyzing image...")
            image_analysis = await workflow.execute_activity(
                view_image,
                args=[photo_key],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                ),
            )

            image_description = image_analysis.get("description", "Product image")
            workflow.logger.info(f"✅ Image analyzed: {image_description[:50]}...")

            # Step 3: Generate caption using AI
            workflow.logger.info("✍️  Step 3: Generating caption with AI...")
            caption = await workflow.execute_activity(
                generate_caption,
                args=[image_description, brand, language, image_url],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,  # AI calls can be expensive, limit retries
                    initial_interval=timedelta(seconds=30),
                ),
            )

            workflow.logger.info(f"✅ Caption generated: {caption[:50]}...")

            # Step 4 & 5: Publish to both platforms in parallel
            workflow.logger.info("📱 Step 4-5: Publishing to social media (parallel)...")

            # Create both tasks
            facebook_task = workflow.execute_activity(
                publish_facebook_photo,
                args=[brand, image_url, caption],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                ),
            )

            instagram_task = workflow.execute_activity(
                publish_instagram_photo,
                args=[brand, image_url, caption],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                ),
            )

            # Wait for both to complete
            facebook_result, instagram_result = await asyncio.gather(
                facebook_task, instagram_task
            )

            workflow.logger.info(
                f"✅ Published - FB: {facebook_result['post_id']}, "
                f"IG: {instagram_result['media_id']}"
            )

            # Step 6: Save report
            workflow.logger.info("💾 Step 6: Saving publication report...")
            report = await workflow.execute_activity(
                save_publication_report,
                args=[
                    brand,
                    photo_key,
                    facebook_result["post_id"],
                    instagram_result["media_id"],
                    caption,
                ],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                ),
            )

            # Build final result
            result = {
                "success": True,
                "brand": brand,
                "language": language,
                "photo_key": photo_key,
                "facebook_post_id": facebook_result["post_id"],
                "instagram_media_id": instagram_result["media_id"],
                "caption_preview": caption[:100] + "...",
                "published_at": workflow.now().isoformat(),
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
            }

            workflow.logger.info("🎉 Feed publisher workflow completed successfully!")

            return result

        except Exception as e:
            workflow.logger.error(f"❌ Workflow failed: {e}")
            raise
