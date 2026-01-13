"""
Memory-Hub Test Workflow
========================

Simple workflow to test Memory-Hub connectivity.
Run with: trigger_workflow(workflow_type="MemoryHubTestWorkflow")
"""

from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.memory_hub_test import test_memory_hub_save


@workflow.defn
class MemoryHubTestWorkflow:
    """
    Simple test workflow for Memory-Hub connectivity.

    Usage:
        mcp__task-orchestrator__trigger_workflow(
            workflow_type="MemoryHubTestWorkflow"
        )
    """

    @workflow.run
    async def run(self) -> dict:
        """Run Memory-Hub test."""
        workflow.logger.info("Starting Memory-Hub test workflow")

        # Run the test activity
        result = await workflow.execute_activity(
            test_memory_hub_save,
            start_to_close_timeout=timedelta(seconds=60)
        )

        workflow.logger.info(f"Memory-Hub test complete: {result}")

        return {
            "workflow": "MemoryHubTestWorkflow",
            "success": result.get("card_created") is not None and result.get("error") is None,
            "result": result
        }
