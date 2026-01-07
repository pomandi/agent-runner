#!/usr/bin/env python3
"""
Create a test schedule that triggers in 2 minutes.
"""
import asyncio
import os
import sys
from dotenv import load_dotenv
from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleState
from datetime import datetime, timedelta

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from temporal_app.workflows.feed_publisher import FeedPublisherWorkflow


async def create_test_schedule():
    """Create a schedule that triggers in 2 minutes."""

    temporal_host = "localhost:7233"
    namespace = "default"
    task_queue = "agent-tasks"

    print("=" * 60)
    print("Creating Test Schedule (triggers in 2 minutes)")
    print("=" * 60)

    client = await Client.connect(temporal_host, namespace=namespace)

    # Calculate trigger time (2 minutes from now)
    now = datetime.utcnow()
    trigger_time = now + timedelta(minutes=2)

    # Format for cron: minute hour day month dayofweek
    cron = f"{trigger_time.minute} {trigger_time.hour} * * *"

    print(f"\nCurrent UTC time: {now.strftime('%H:%M:%S')}")
    print(f"Schedule will trigger at: {trigger_time.strftime('%H:%M:%S')} UTC")
    print(f"Cron expression: {cron}")

    schedule_id = f"test-manual-{int(now.timestamp())}"

    try:
        # Delete if exists
        try:
            handle = client.get_schedule_handle(schedule_id)
            await handle.delete()
            print(f"\n🗑️  Deleted existing schedule")
        except:
            pass

        await client.create_schedule(
            id=schedule_id,
            schedule=Schedule(
                action=ScheduleActionStartWorkflow(
                    workflow=FeedPublisherWorkflow.run,
                    args=["pomandi"],
                    id=f"test-manual-workflow",
                    task_queue=task_queue,
                    execution_timeout=timedelta(minutes=30),
                ),
                spec=ScheduleSpec(
                    cron_expressions=[cron],
                ),
                state=ScheduleState(
                    note=f"Test schedule - triggers at {trigger_time.strftime('%H:%M')} UTC",
                    paused=False,
                ),
            ),
        )

        print(f"\n✅ Schedule '{schedule_id}' created successfully!")
        print(f"\n⏰ Workflow will start in approximately 2 minutes")
        print(f"   Monitor with: docker compose logs -f agent-worker")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Failed: {e}")
        raise

    await client.close()


if __name__ == "__main__":
    asyncio.run(create_test_schedule())
