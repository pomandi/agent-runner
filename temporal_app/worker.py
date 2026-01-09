"""
Temporal worker - runs activities and workflows.
"""
import asyncio
import os
import logging
import sys
from temporalio.client import Client
from temporalio.worker import Worker

# Environment variables will be read from system environment (Coolify injection)
# No need for load_dotenv() - os.getenv() reads from container environment

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import workflows
from temporal_app.workflows.feed_publisher import FeedPublisherWorkflow
from temporal_app.workflows.appointment_collector import AppointmentCollectorWorkflow
from temporal_app.workflows.daily_analytics import DailyAnalyticsWorkflow, WeeklyAnalyticsWorkflow
from temporal_app.workflows.email_assistant_workflow import EmailAssistantWorkflow, DailyEmailSummaryWorkflow

# Import activities
from temporal_app.activities.social_media import (
    get_random_unused_photo,
    view_image,
    generate_caption,
    publish_facebook_photo,
    publish_instagram_photo,
    save_publication_report,
)
from temporal_app.activities.appointment_activities import (
    collect_appointments,
    analyze_appointments,
    save_appointment_report,
)
from temporal_app.activities.langgraph_wrapper import (
    run_langgraph_feed_publisher,
    check_caption_quality,
    check_caption_duplicate,
)
from temporal_app.activities.langgraph_activities import (
    run_daily_analytics_graph,
)
from temporal_app.activities.email_activities import (
    send_daily_email_summary,
    run_email_assistant_check,
    process_pending_approvals,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def run_worker():
    """Start Temporal worker."""

    # Get configuration from environment
    temporal_host = os.getenv('TEMPORAL_HOST', 'localhost:7233')
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')
    task_queue = os.getenv('TEMPORAL_TASK_QUEUE', 'agent-tasks')

    logger.info("=" * 60)
    logger.info("Temporal Worker Starting")
    logger.info("=" * 60)
    logger.info(f"Temporal Host: {temporal_host}")
    logger.info(f"Namespace: {namespace}")
    logger.info(f"Task Queue: {task_queue}")
    logger.info("=" * 60)

    # Connect to Temporal
    logger.info("Connecting to Temporal...")
    client = await Client.connect(temporal_host, namespace=namespace)
    logger.info("✅ Connected to Temporal successfully")

    # Build workflow and activity lists
    workflows = [
        FeedPublisherWorkflow,
        AppointmentCollectorWorkflow,
        DailyAnalyticsWorkflow,
        WeeklyAnalyticsWorkflow,
        EmailAssistantWorkflow,
        DailyEmailSummaryWorkflow,
    ]

    activities = [
        # Core social media activities
        get_random_unused_photo,
        view_image,
        generate_caption,
        publish_facebook_photo,
        publish_instagram_photo,
        save_publication_report,
        # Appointment activities
        collect_appointments,
        analyze_appointments,
        save_appointment_report,
        # LangGraph wrapper activities (quality checks, memory)
        run_langgraph_feed_publisher,
        check_caption_quality,
        check_caption_duplicate,
        # LangGraph activities (full graph execution)
        run_daily_analytics_graph,
        # Email assistant activities
        send_daily_email_summary,
        run_email_assistant_check,
        process_pending_approvals,
    ]

    # Create worker
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=workflows,
        activities=activities,
        max_concurrent_activities=10,
        max_concurrent_workflow_tasks=10,
    )

    logger.info("=" * 60)
    logger.info(f"✅ Worker initialized on task queue: {task_queue}")
    logger.info("Registered workflows:")
    for wf in workflows:
        logger.info(f"  - {wf.__name__}")
    logger.info(f"Registered activities: {len(activities)} total")
    logger.info("  Core activities:")
    logger.info("    - get_random_unused_photo")
    logger.info("    - view_image")
    logger.info("    - generate_caption")
    logger.info("    - publish_facebook_photo")
    logger.info("    - publish_instagram_photo")
    logger.info("    - save_publication_report")
    logger.info("    - collect_appointments")
    logger.info("    - analyze_appointments")
    logger.info("    - save_appointment_report")
    logger.info("  LangGraph wrapper activities:")
    logger.info("    - run_langgraph_feed_publisher")
    logger.info("    - check_caption_quality")
    logger.info("    - check_caption_duplicate")
    logger.info("  LangGraph activities:")
    logger.info("    - run_daily_analytics_graph")
    logger.info("=" * 60)
    logger.info("🎧 Listening for workflow tasks...")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    # Run worker (blocks until stopped)
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("\n👋 Worker shutting down...")
    except Exception as e:
        logger.error(f"❌ Worker error: {e}", exc_info=True)
        raise
    finally:
        await client.close()
        logger.info("✅ Worker stopped")

def main():
    """Entry point."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
