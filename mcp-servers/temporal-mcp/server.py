#!/usr/bin/env python3
"""
Temporal MCP Server - Manage Temporal workflows and schedules via MCP

Features:
- Trigger workflows manually
- Create/update/delete schedules
- List workflows and schedules
- Get workflow results
- Pause/unpause schedules
- Trigger schedules manually

Usage:
    python server.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
import mcp.server.stdio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleState,
    SchedulePolicy,
    ScheduleOverlapPolicy,
    WorkflowExecutionStatus,
)
from dotenv import load_dotenv

load_dotenv()

# Configuration
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "agent-tasks")

# Import workflow classes
from temporal_app.workflows.feed_publisher import FeedPublisherWorkflow


# Global Temporal client
_temporal_client: Optional[Client] = None


async def get_temporal_client() -> Client:
    """Get or create Temporal client."""
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await Client.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)
    return _temporal_client


# Create MCP server
app = Server("temporal-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Temporal tools."""
    return [
        Tool(
            name="trigger_workflow",
            description="Trigger a workflow execution immediately. Returns workflow_id and run_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_type": {
                        "type": "string",
                        "description": "Workflow type (e.g., 'feed-publisher')",
                        "enum": ["feed-publisher"],
                    },
                    "brand": {
                        "type": "string",
                        "description": "Brand name (pomandi or costume)",
                        "enum": ["pomandi", "costume"],
                    },
                    "workflow_id": {
                        "type": "string",
                        "description": "Optional custom workflow ID. Auto-generated if not provided.",
                    },
                },
                "required": ["workflow_type", "brand"],
            },
        ),
        Tool(
            name="get_workflow_result",
            description="Get the result of a workflow execution. Waits for completion if still running.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "Workflow ID to get result for",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Optional run ID. Uses latest run if not provided.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Max seconds to wait for result (default: 300)",
                        "default": 300,
                    },
                },
                "required": ["workflow_id"],
            },
        ),
        Tool(
            name="list_workflows",
            description="List recent workflow executions with their status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max workflows to return (default: 10)",
                        "default": 10,
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status (running, completed, failed, all)",
                        "enum": ["running", "completed", "failed", "all"],
                        "default": "all",
                    },
                },
            },
        ),
        Tool(
            name="cancel_workflow",
            description="Cancel a running workflow execution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "Workflow ID to cancel",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Optional run ID. Cancels latest run if not provided.",
                    },
                },
                "required": ["workflow_id"],
            },
        ),
        Tool(
            name="list_schedules",
            description="List all Temporal schedules with their details.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="create_schedule",
            description="Create a new Temporal schedule for recurring workflow execution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "string",
                        "description": "Unique schedule ID",
                    },
                    "workflow_type": {
                        "type": "string",
                        "description": "Workflow type to run",
                        "enum": ["feed-publisher"],
                    },
                    "brand": {
                        "type": "string",
                        "description": "Brand name for feed-publisher workflow",
                        "enum": ["pomandi", "costume"],
                    },
                    "cron_expression": {
                        "type": "string",
                        "description": "Cron expression (e.g., '0 9,18 * * *' for 9am and 6pm daily)",
                    },
                    "note": {
                        "type": "string",
                        "description": "Optional description of the schedule",
                    },
                    "paused": {
                        "type": "boolean",
                        "description": "Create schedule in paused state (default: false)",
                        "default": False,
                    },
                },
                "required": ["schedule_id", "workflow_type", "brand", "cron_expression"],
            },
        ),
        Tool(
            name="delete_schedule",
            description="Delete a Temporal schedule permanently.",
            inputSchema={
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "string",
                        "description": "Schedule ID to delete",
                    },
                },
                "required": ["schedule_id"],
            },
        ),
        Tool(
            name="pause_schedule",
            description="Pause a schedule (stop it from triggering).",
            inputSchema={
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "string",
                        "description": "Schedule ID to pause",
                    },
                    "note": {
                        "type": "string",
                        "description": "Optional note about why paused",
                    },
                },
                "required": ["schedule_id"],
            },
        ),
        Tool(
            name="unpause_schedule",
            description="Unpause a schedule (resume triggering).",
            inputSchema={
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "string",
                        "description": "Schedule ID to unpause",
                    },
                    "note": {
                        "type": "string",
                        "description": "Optional note",
                    },
                },
                "required": ["schedule_id"],
            },
        ),
        Tool(
            name="trigger_schedule_now",
            description="Trigger a schedule immediately (outside of scheduled times).",
            inputSchema={
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "string",
                        "description": "Schedule ID to trigger",
                    },
                },
                "required": ["schedule_id"],
            },
        ),
        Tool(
            name="create_test_schedule",
            description="Create a test schedule that triggers in N minutes from now.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_type": {
                        "type": "string",
                        "description": "Workflow type",
                        "enum": ["feed-publisher"],
                    },
                    "brand": {
                        "type": "string",
                        "description": "Brand name",
                        "enum": ["pomandi", "costume"],
                    },
                    "minutes_from_now": {
                        "type": "integer",
                        "description": "Minutes from now to trigger (default: 2)",
                        "default": 2,
                    },
                },
                "required": ["workflow_type", "brand"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls."""
    try:
        if name == "trigger_workflow":
            return await trigger_workflow(arguments)
        elif name == "get_workflow_result":
            return await get_workflow_result(arguments)
        elif name == "list_workflows":
            return await list_workflows(arguments)
        elif name == "cancel_workflow":
            return await cancel_workflow(arguments)
        elif name == "list_schedules":
            return await list_schedules(arguments)
        elif name == "create_schedule":
            return await create_schedule(arguments)
        elif name == "delete_schedule":
            return await delete_schedule(arguments)
        elif name == "pause_schedule":
            return await pause_schedule(arguments)
        elif name == "unpause_schedule":
            return await unpause_schedule(arguments)
        elif name == "trigger_schedule_now":
            return await trigger_schedule_now(arguments)
        elif name == "create_test_schedule":
            return await create_test_schedule(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def trigger_workflow(args: Dict[str, Any]) -> list[TextContent]:
    """Trigger a workflow execution."""
    client = await get_temporal_client()

    workflow_type = args["workflow_type"]
    brand = args["brand"]
    workflow_id = args.get("workflow_id", f"{workflow_type}-{brand}-{int(datetime.utcnow().timestamp())}")

    # Map workflow type to class
    workflow_map = {
        "feed-publisher": FeedPublisherWorkflow,
    }

    workflow_class = workflow_map.get(workflow_type)
    if not workflow_class:
        return [TextContent(type="text", text=f"Unknown workflow type: {workflow_type}")]

    # Start workflow
    handle = await client.start_workflow(
        workflow=workflow_class.run,
        args=[brand],
        id=workflow_id,
        task_queue=TASK_QUEUE,
        execution_timeout=timedelta(minutes=30),
        run_timeout=timedelta(minutes=30),
    )

    result = {
        "status": "started",
        "workflow_id": handle.id,
        "run_id": handle.result_run_id,
        "workflow_type": workflow_type,
        "brand": brand,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def get_workflow_result(args: Dict[str, Any]) -> list[TextContent]:
    """Get workflow execution result."""
    client = await get_temporal_client()

    workflow_id = args["workflow_id"]
    run_id = args.get("run_id")
    timeout_seconds = args.get("timeout_seconds", 300)

    # Get workflow handle
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)

    try:
        # Wait for result with timeout
        result = await asyncio.wait_for(
            handle.result(),
            timeout=timeout_seconds
        )

        return [TextContent(type="text", text=json.dumps({
            "status": "completed",
            "workflow_id": workflow_id,
            "result": result,
        }, indent=2))]

    except asyncio.TimeoutError:
        # Get current status without waiting
        describe = await handle.describe()
        return [TextContent(type="text", text=json.dumps({
            "status": "timeout",
            "workflow_id": workflow_id,
            "current_status": str(describe.status),
            "message": f"Workflow still running after {timeout_seconds}s",
        }, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "status": "error",
            "workflow_id": workflow_id,
            "error": str(e),
        }, indent=2))]


async def list_workflows(args: Dict[str, Any]) -> list[TextContent]:
    """List workflow executions."""
    client = await get_temporal_client()

    limit = args.get("limit", 10)
    status_filter = args.get("status", "all")

    # Build query
    query = ""
    if status_filter == "running":
        query = "ExecutionStatus = 'Running'"
    elif status_filter == "completed":
        query = "ExecutionStatus = 'Completed'"
    elif status_filter == "failed":
        query = "ExecutionStatus = 'Failed'"

    # List workflows
    workflows = []
    async for workflow in client.list_workflows(query=query):
        workflows.append({
            "workflow_id": workflow.id,
            "run_id": workflow.run_id,
            "workflow_type": workflow.workflow_type,
            "status": str(workflow.status),
            "start_time": workflow.start_time.isoformat() if workflow.start_time else None,
            "close_time": workflow.close_time.isoformat() if workflow.close_time else None,
        })

        if len(workflows) >= limit:
            break

    return [TextContent(type="text", text=json.dumps({
        "total": len(workflows),
        "workflows": workflows,
    }, indent=2))]


async def cancel_workflow(args: Dict[str, Any]) -> list[TextContent]:
    """Cancel a workflow execution."""
    client = await get_temporal_client()

    workflow_id = args["workflow_id"]
    run_id = args.get("run_id")

    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    await handle.cancel()

    return [TextContent(type="text", text=json.dumps({
        "status": "cancelled",
        "workflow_id": workflow_id,
    }, indent=2))]


async def list_schedules(args: Dict[str, Any]) -> list[TextContent]:
    """List all schedules."""
    client = await get_temporal_client()

    schedules = []
    async for schedule in client.list_schedules():
        schedule_info = {
            "schedule_id": schedule.id,
            "paused": schedule.schedule.state.paused if schedule.schedule.state else None,
            "note": schedule.schedule.state.note if schedule.schedule.state else None,
        }

        # Get cron expressions if available
        if schedule.schedule.spec and schedule.schedule.spec.cron_expressions:
            schedule_info["cron_expressions"] = schedule.schedule.spec.cron_expressions

        schedules.append(schedule_info)

    return [TextContent(type="text", text=json.dumps({
        "total": len(schedules),
        "schedules": schedules,
    }, indent=2))]


async def create_schedule(args: Dict[str, Any]) -> list[TextContent]:
    """Create a new schedule."""
    client = await get_temporal_client()

    schedule_id = args["schedule_id"]
    workflow_type = args["workflow_type"]
    brand = args["brand"]
    cron_expression = args["cron_expression"]
    note = args.get("note", "")
    paused = args.get("paused", False)

    # Map workflow type
    workflow_map = {
        "feed-publisher": FeedPublisherWorkflow,
    }

    workflow_class = workflow_map.get(workflow_type)
    if not workflow_class:
        return [TextContent(type="text", text=f"Unknown workflow type: {workflow_type}")]

    # Create schedule
    await client.create_schedule(
        id=schedule_id,
        schedule=Schedule(
            action=ScheduleActionStartWorkflow(
                workflow=workflow_class.run,
                args=[brand],
                id=f"{workflow_type}-{brand}-scheduled",
                task_queue=TASK_QUEUE,
                execution_timeout=timedelta(minutes=30),
                run_timeout=timedelta(minutes=30),
            ),
            spec=ScheduleSpec(
                cron_expressions=[cron_expression],
            ),
            state=ScheduleState(
                note=note,
                paused=paused,
            ),
            policy=SchedulePolicy(
                overlap=ScheduleOverlapPolicy.SKIP,
                catchup_window=timedelta(minutes=10),
            ),
        ),
    )

    return [TextContent(type="text", text=json.dumps({
        "status": "created",
        "schedule_id": schedule_id,
        "cron_expression": cron_expression,
        "paused": paused,
    }, indent=2))]


async def delete_schedule(args: Dict[str, Any]) -> list[TextContent]:
    """Delete a schedule."""
    client = await get_temporal_client()

    schedule_id = args["schedule_id"]
    handle = client.get_schedule_handle(schedule_id)
    await handle.delete()

    return [TextContent(type="text", text=json.dumps({
        "status": "deleted",
        "schedule_id": schedule_id,
    }, indent=2))]


async def pause_schedule(args: Dict[str, Any]) -> list[TextContent]:
    """Pause a schedule."""
    client = await get_temporal_client()

    schedule_id = args["schedule_id"]
    note = args.get("note", "Paused via MCP")

    handle = client.get_schedule_handle(schedule_id)
    await handle.pause(note=note)

    return [TextContent(type="text", text=json.dumps({
        "status": "paused",
        "schedule_id": schedule_id,
    }, indent=2))]


async def unpause_schedule(args: Dict[str, Any]) -> list[TextContent]:
    """Unpause a schedule."""
    client = await get_temporal_client()

    schedule_id = args["schedule_id"]
    note = args.get("note", "Unpaused via MCP")

    handle = client.get_schedule_handle(schedule_id)
    await handle.unpause(note=note)

    return [TextContent(type="text", text=json.dumps({
        "status": "unpaused",
        "schedule_id": schedule_id,
    }, indent=2))]


async def trigger_schedule_now(args: Dict[str, Any]) -> list[TextContent]:
    """Trigger a schedule immediately."""
    client = await get_temporal_client()

    schedule_id = args["schedule_id"]
    handle = client.get_schedule_handle(schedule_id)
    await handle.trigger()

    return [TextContent(type="text", text=json.dumps({
        "status": "triggered",
        "schedule_id": schedule_id,
        "message": "Schedule triggered manually",
    }, indent=2))]


async def create_test_schedule(args: Dict[str, Any]) -> list[TextContent]:
    """Create a test schedule that triggers in N minutes."""
    workflow_type = args["workflow_type"]
    brand = args["brand"]
    minutes = args.get("minutes_from_now", 2)

    # Calculate trigger time
    now = datetime.utcnow()
    trigger = now + timedelta(minutes=minutes)
    cron = f"{trigger.minute} {trigger.hour} * * *"

    # Create schedule
    schedule_id = f"test-{brand}-{int(now.timestamp())}"
    note = f"Test schedule - triggers at {trigger.strftime('%H:%M')} UTC"

    result = await create_schedule({
        "schedule_id": schedule_id,
        "workflow_type": workflow_type,
        "brand": brand,
        "cron_expression": cron,
        "note": note,
        "paused": False,
    })

    # Parse the result and add trigger time info
    result_data = json.loads(result[0].text)
    result_data["trigger_time"] = trigger.strftime("%H:%M:%S UTC")
    result_data["minutes_from_now"] = minutes

    return [TextContent(type="text", text=json.dumps(result_data, indent=2))]


async def main():
    """Run the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
