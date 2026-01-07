#!/usr/bin/env python3
"""
Test script to trigger AppointmentCollectorWorkflow directly.
"""
import asyncio
import os
import sys
from datetime import timedelta
from temporalio.client import Client

# Add agent-runner to path
sys.path.insert(0, os.path.dirname(__file__))

# Import workflow
from temporal_app.workflows.appointment_collector import AppointmentCollectorWorkflow


async def main():
    """Trigger the workflow."""
    # Get config from env
    temporal_host = os.getenv('TEMPORAL_HOST', '46.224.117.155:7233')
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')
    task_queue = os.getenv('TEMPORAL_TASK_QUEUE', 'agent-tasks')

    print(f"🔗 Connecting to Temporal at {temporal_host}...")

    # Connect to Temporal
    client = await Client.connect(temporal_host, namespace=namespace)

    print(f"✅ Connected!")
    print(f"📋 Task Queue: {task_queue}")
    print()

    # Start workflow
    workflow_id = f"test-appointment-collector-{int(asyncio.get_event_loop().time())}"

    print(f"🚀 Starting AppointmentCollectorWorkflow...")
    print(f"   Workflow ID: {workflow_id}")
    print(f"   Args: days=7")
    print()

    handle = await client.start_workflow(
        AppointmentCollectorWorkflow.run,
        args=[7],  # Last 7 days
        id=workflow_id,
        task_queue=task_queue,
        execution_timeout=timedelta(minutes=10)
    )

    print(f"✅ Workflow started!")
    print(f"   Workflow ID: {handle.id}")
    print(f"   Run ID: {handle.result_run_id}")
    print()
    print(f"⏳ Waiting for result...")

    try:
        result = await handle.result()

        print()
        print("=" * 60)
        print("🎉 WORKFLOW COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print()
        print(f"Days collected: {result['days']}")
        print(f"Total appointments: {result['total_appointments']}")
        print(f"Confirmed: {result['analysis']['total_conversions']}")
        print(f"Pending: {result['analysis']['pending']}")
        print(f"Cancelled: {result['analysis']['cancelled']}")
        print(f"Conversion rate: {result['analysis']['conversion_rate']}")
        print()
        print(f"Top source: {result['analysis']['top_source']}")
        print()
        print(f"Google Ads conversions: {result['analysis']['google_ads_conversions']}")
        print(f"Meta Ads conversions: {result['analysis']['meta_ads_conversions']}")
        print(f"Organic conversions: {result['analysis']['organic_conversions']}")
        print()
        print(f"Report ID: {result['report_id']}")
        print()
        print("=" * 60)

    except Exception as e:
        print(f"❌ Workflow failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
