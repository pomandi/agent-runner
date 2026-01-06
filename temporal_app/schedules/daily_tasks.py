"""
Temporal schedules for daily social media posting.

This module sets up recurring schedules for:
- Pomandi: 09:00 and 18:00 UTC
- Costume: 10:00 and 19:00 UTC
"""
import asyncio
import os
import logging
from datetime import timedelta
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleCalendarSpec,
    ScheduleState,
    SchedulePolicy,
    ScheduleOverlapPolicy,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from temporal_app.workflows.feed_publisher import FeedPublisherWorkflow

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def setup_schedules():
    """
    Set up all daily posting schedules.

    Creates or updates schedules for both brands with their respective posting times.
    """
    # Get configuration from environment
    temporal_host = os.getenv('TEMPORAL_HOST', 'localhost:7233')
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')
    task_queue = os.getenv('TEMPORAL_TASK_QUEUE', 'agent-tasks')

    logger.info("=" * 60)
    logger.info("Setting up Temporal Schedules")
    logger.info("=" * 60)
    logger.info(f"Temporal Host: {temporal_host}")
    logger.info(f"Namespace: {namespace}")
    logger.info(f"Task Queue: {task_queue}")
    logger.info("=" * 60)

    # Connect to Temporal
    logger.info("Connecting to Temporal...")
    client = await Client.connect(temporal_host, namespace=namespace)
    logger.info("✅ Connected to Temporal successfully")

    # Schedule 1: Pomandi daily posts (09:00 and 18:00 UTC)
    schedule_id_pomandi = "pomandi-daily-posts"

    logger.info(f"\n📅 Creating schedule: {schedule_id_pomandi}")
    logger.info("   Posts at: 09:00 UTC and 18:00 UTC")

    try:
        await client.create_schedule(
            id=schedule_id_pomandi,
            schedule=Schedule(
                action=ScheduleActionStartWorkflow(
                    workflow=FeedPublisherWorkflow.run,
                    args=["pomandi"],
                    id=f"pomandi-daily-post",
                    task_queue=task_queue,
                    execution_timeout=timedelta(minutes=30),
                    run_timeout=timedelta(minutes=30),
                ),
                spec=ScheduleSpec(
                    cron_expressions=["0 9,18 * * *"],  # 09:00 and 18:00 UTC daily
                ),
                state=ScheduleState(
                    note="Daily social media posts for Pomandi brand",
                    paused=False,
                ),
                policy=SchedulePolicy(
                    overlap=ScheduleOverlapPolicy.SKIP,  # Skip if previous still running
                    catchup_window=timedelta(minutes=10),  # Catch up if missed by <10min
                ),
            ),
        )
        logger.info(f"✅ Schedule '{schedule_id_pomandi}' created successfully")
    except Exception as e:
        if "already exists" in str(e).lower():
            logger.info(f"⚠️  Schedule '{schedule_id_pomandi}' already exists, skipping")
        else:
            logger.error(f"❌ Failed to create schedule '{schedule_id_pomandi}': {e}")
            raise

    # Schedule 2: Costume daily posts (10:00 and 19:00 UTC)
    schedule_id_costume = "costume-daily-posts"

    logger.info(f"\n📅 Creating schedule: {schedule_id_costume}")
    logger.info("   Posts at: 10:00 UTC and 19:00 UTC")

    try:
        await client.create_schedule(
            id=schedule_id_costume,
            schedule=Schedule(
                action=ScheduleActionStartWorkflow(
                    workflow=FeedPublisherWorkflow.run,
                    args=["costume"],
                    id=f"costume-daily-post",
                    task_queue=task_queue,
                    execution_timeout=timedelta(minutes=30),
                    run_timeout=timedelta(minutes=30),
                ),
                spec=ScheduleSpec(
                    cron_expressions=["0 10,19 * * *"],  # 10:00 and 19:00 UTC daily
                ),
                state=ScheduleState(
                    note="Daily social media posts for Costume brand",
                    paused=False,
                ),
                policy=SchedulePolicy(
                    overlap=ScheduleOverlapPolicy.SKIP,  # Skip if previous still running
                    catchup_window=timedelta(minutes=10),  # Catch up if missed by <10min
                ),
            ),
        )
        logger.info(f"✅ Schedule '{schedule_id_costume}' created successfully")
    except Exception as e:
        if "already exists" in str(e).lower():
            logger.info(f"⚠️  Schedule '{schedule_id_costume}' already exists, skipping")
        else:
            logger.error(f"❌ Failed to create schedule '{schedule_id_costume}': {e}")
            raise

    # List all schedules to verify
    logger.info("\n" + "=" * 60)
    logger.info("Current Schedules:")
    logger.info("=" * 60)

    async for schedule in client.list_schedules():
        logger.info(f"  • {schedule.id}")
        if hasattr(schedule.schedule, 'state') and schedule.schedule.state.note:
            logger.info(f"    Note: {schedule.schedule.state.note}")
        if hasattr(schedule.schedule, 'spec') and schedule.schedule.spec.calendars:
            times = [f"{cal.hour:02d}:{cal.minute:02d}" for cal in schedule.schedule.spec.calendars]
            logger.info(f"    Times: {', '.join(times)} UTC")

    logger.info("=" * 60)
    logger.info("✅ All schedules configured successfully!")
    logger.info("=" * 60)

    await client.close()


async def pause_schedule(schedule_id: str):
    """Pause a schedule (stop it from triggering)."""
    temporal_host = os.getenv('TEMPORAL_HOST', 'localhost:7233')
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')

    client = await Client.connect(temporal_host, namespace=namespace)
    handle = client.get_schedule_handle(schedule_id)
    await handle.pause(note=f"Paused manually at {asyncio.get_event_loop().time()}")
    logger.info(f"✅ Schedule '{schedule_id}' paused")
    await client.close()


async def unpause_schedule(schedule_id: str):
    """Unpause a schedule (resume triggering)."""
    temporal_host = os.getenv('TEMPORAL_HOST', 'localhost:7233')
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')

    client = await Client.connect(temporal_host, namespace=namespace)
    handle = client.get_schedule_handle(schedule_id)
    await handle.unpause(note="Resumed manually")
    logger.info(f"✅ Schedule '{schedule_id}' resumed")
    await client.close()


async def trigger_schedule_now(schedule_id: str):
    """Trigger a schedule immediately (outside of scheduled times)."""
    temporal_host = os.getenv('TEMPORAL_HOST', 'localhost:7233')
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')

    client = await Client.connect(temporal_host, namespace=namespace)
    handle = client.get_schedule_handle(schedule_id)
    await handle.trigger()
    logger.info(f"✅ Schedule '{schedule_id}' triggered manually")
    await client.close()


async def delete_schedule(schedule_id: str):
    """Delete a schedule completely."""
    temporal_host = os.getenv('TEMPORAL_HOST', 'localhost:7233')
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')

    client = await Client.connect(temporal_host, namespace=namespace)
    handle = client.get_schedule_handle(schedule_id)
    await handle.delete()
    logger.info(f"✅ Schedule '{schedule_id}' deleted")
    await client.close()


def main():
    """Entry point for schedule setup."""
    try:
        asyncio.run(setup_schedules())
    except KeyboardInterrupt:
        logger.info("\n👋 Setup interrupted")
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
