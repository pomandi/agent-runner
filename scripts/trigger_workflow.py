#!/usr/bin/env python3
"""
Trigger Temporal Workflow
Triggers any workflow via Temporal client
"""
import asyncio
import os
import sys
from datetime import timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from temporalio.client import Client
from temporal_app.workflows.feed_publisher import FeedPublisherWorkflow


async def trigger_feed_publisher(brand: str = "pomandi"):
    """Trigger Feed Publisher workflow"""

    # Get Temporal host from environment
    temporal_host = os.getenv("TEMPORAL_HOST", "temporal:7233")

    print(f"🔗 Connecting to Temporal at {temporal_host}...")

    try:
        # Connect to Temporal
        client = await Client.connect(temporal_host)
        print("✅ Connected to Temporal")

        # Trigger workflow
        workflow_id = f"feed-publisher-test-{brand}"

        print(f"\n🚀 Starting Feed Publisher workflow...")
        print(f"   Brand: {brand}")
        print(f"   Workflow ID: {workflow_id}")
        print(f"   Task Queue: agent-tasks")

        handle = await client.start_workflow(
            FeedPublisherWorkflow.run,
            brand,
            id=workflow_id,
            task_queue="agent-tasks",
            execution_timeout=timedelta(minutes=5),
        )

        print(f"\n✅ Workflow started successfully!")
        print(f"   Run ID: {handle.result_run_id}")
        print(f"\n⏳ Waiting for workflow to complete (max 5 minutes)...")

        # Wait for result
        result = await handle.result()

        print(f"\n🎉 Workflow completed!")
        print(f"\n📊 Results:")
        print(f"{result}")

        return result

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    brand = sys.argv[1] if len(sys.argv) > 1 else "pomandi"
    result = asyncio.run(trigger_feed_publisher(brand))
    sys.exit(0 if result else 1)
