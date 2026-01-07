#!/usr/bin/env python3
"""
Test script to trigger AppointmentCollectorWorkflow and show errors.
"""
import asyncio
import os
import sys
from temporalio.client import Client
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import workflow
from temporal_app.workflows.appointment_collector import AppointmentCollectorWorkflow

async def main():
    """Test workflow execution."""

    temporal_host = os.getenv('TEMPORAL_HOST', '46.224.117.155:7233')
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')
    task_queue = os.getenv('TEMPORAL_TASK_QUEUE', 'agent-tasks')

    print(f"🔗 Connecting to Temporal at {temporal_host}")
    print(f"📋 Namespace: {namespace}")
    print(f"🎯 Task Queue: {task_queue}")
    print()

    # Connect
    client = await Client.connect(temporal_host, namespace=namespace)

    # Start workflow
    print("🚀 Starting AppointmentCollectorWorkflow...")
    workflow_id = f"test-appointment-debug-{int(asyncio.get_event_loop().time())}"

    try:
        handle = await client.start_workflow(
            AppointmentCollectorWorkflow.run,
            args=[7],  # last 7 days
            id=workflow_id,
            task_queue=task_queue,
        )

        print(f"✅ Workflow started: {workflow_id}")
        print(f"🔗 Run ID: {handle.result_run_id}")
        print()
        print("⏳ Waiting for result...")

        # Wait for result
        result = await handle.result()

        print()
        print("=" * 60)
        print("✅ WORKFLOW COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"Days: {result['days']}")
        print(f"Total Appointments: {result['total_appointments']}")
        print(f"Conversions: {result['analysis']['total_conversions']}")
        print(f"Report ID: {result['report_id']}")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print("❌ WORKFLOW FAILED!")
        print("=" * 60)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
