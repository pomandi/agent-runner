#!/usr/bin/env python3
"""
Task Orchestrator MCP Server
============================
Unified MCP for managing the complete agentic task system:

1. **Temporal** - Workflow & schedule management (task orchestration)
2. **Storage** - Task outputs & execution logs (PostgreSQL)
3. **Langfuse** - LLM tracing, cost tracking, observability

This MCP combines three specialized modules into a single interface
for complete task lifecycle management.

Usage:
    python server.py
"""
import asyncio
import json
import os
import sys
from typing import Any, Dict

# Add parent directories to path
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_servers_dir = os.path.dirname(current_dir)
agent_runner_root = os.path.dirname(mcp_servers_dir)

sys.path.insert(0, current_dir)  # task-orchestrator-mcp
sys.path.insert(0, mcp_servers_dir)  # mcp-servers
sys.path.insert(0, agent_runner_root)  # agent-runner root (contains temporal_app)

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import submodules
from langfuse_module import (
    tool_list_traces,
    tool_get_trace_details,
    tool_get_costs,
    tool_get_recent_executions
)

# Import temporal functions from existing temporal-mcp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'temporal-mcp'))
from temporalio.client import Client as TemporalClient
from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec, ScheduleState, WorkflowHistoryEventFilterType
from temporalio.api.history.v1 import HistoryEvent
from temporalio.api.enums.v1 import EventType
from temporalio.service import RPCError
from datetime import timedelta, datetime

# Import storage functions from existing agent-outputs-mcp
import asyncpg

# Server instance
server = Server("task-orchestrator")

# Global state
_temporal_client = None
_storage_pool = None

# ============================================================================
# TEMPORAL MODULE - Workflow & Schedule Management
# ============================================================================

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "46.224.117.155:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.getenv("TASK_QUEUE", "agent-tasks")


async def get_temporal_client() -> TemporalClient:
    """Get or create Temporal client singleton."""
    global _temporal_client

    if _temporal_client is None:
        _temporal_client = await TemporalClient.connect(
            TEMPORAL_HOST,
            namespace=TEMPORAL_NAMESPACE
        )

    return _temporal_client


async def tool_trigger_workflow(args: Dict[str, Any]) -> str:
    """
    Trigger a workflow execution immediately.

    Args:
        workflow_type: Workflow class name (e.g., "FeedPublisherWorkflow")
        workflow_args: List of arguments for workflow
        workflow_id: Optional custom workflow ID
        timeout_minutes: Execution timeout (default: 30)
    """
    client = await get_temporal_client()

    workflow_type = args.get('workflow_type')
    workflow_args = args.get('workflow_args', [])
    workflow_id = args.get('workflow_id')
    timeout_minutes = args.get('timeout_minutes', 30)

    if not workflow_type:
        return "❌ workflow_type required"

    # Dynamic workflow import - try different modules
    workflow_class = None

    # Map workflow classes to their modules
    workflow_map = {
        'FeedPublisherWorkflow': 'temporal_app.workflows.feed_publisher',
        'AppointmentCollectorWorkflow': 'temporal_app.workflows.appointment_collector',
        'DailyAnalyticsWorkflow': 'temporal_app.workflows.daily_analytics',
        'WeeklyAnalyticsWorkflow': 'temporal_app.workflows.daily_analytics',
        'EmailAssistantWorkflow': 'temporal_app.workflows.email_assistant_workflow',
        'DailyEmailSummaryWorkflow': 'temporal_app.workflows.email_assistant_workflow',
    }

    module_name = workflow_map.get(workflow_type)

    if module_name:
        try:
            # Import the module
            import importlib
            module = importlib.import_module(module_name)
            workflow_class = getattr(module, workflow_type, None)
        except (ImportError, AttributeError) as e:
            return f"❌ Failed to import workflow '{workflow_type}': {e}"

    if not workflow_class:
        available = ', '.join(workflow_map.keys())
        return f"❌ Workflow '{workflow_type}' not found. Available: {available}"

    # Generate ID if not provided
    if not workflow_id:
        workflow_id = f"manual-{workflow_type}-{int(datetime.utcnow().timestamp())}"

    handle = await client.start_workflow(
        workflow=workflow_class.run,
        args=workflow_args,
        id=workflow_id,
        task_queue=TASK_QUEUE,
        execution_timeout=timedelta(minutes=timeout_minutes)
    )

    output = f"✅ **Workflow Started**\n\n"
    output += f"**Type:** {workflow_type}\n"
    output += f"**ID:** `{handle.id}`\n"
    output += f"**Run ID:** `{handle.result_run_id}`\n"
    output += f"**Args:** {workflow_args}\n"
    output += f"**Timeout:** {timeout_minutes} minutes\n"

    return output


async def tool_list_workflows(args: Dict[str, Any]) -> str:
    """
    List recent workflow executions.

    Args:
        limit: Max workflows to return (default: 10)
    """
    client = await get_temporal_client()
    limit = args.get('limit', 10)

    workflows = []

    async for workflow in client.list_workflows():
        workflows.append(workflow)

        if len(workflows) >= limit:
            break

    output = f"🔄 **Recent Workflows** ({len(workflows)})\n\n"

    for wf in workflows:
        status_emoji = {
            "RUNNING": "🏃",
            "COMPLETED": "✅",
            "FAILED": "❌",
            "CANCELED": "⛔",
            "TERMINATED": "🛑"
        }.get(wf.status.name, "❓")

        output += f"{status_emoji} **{wf.id}**\n"
        output += f"  Type: {wf.workflow_type}\n"
        output += f"  Status: {wf.status.name}\n"
        output += f"  Start: {wf.start_time}\n"

        if wf.close_time:
            duration = (wf.close_time - wf.start_time).total_seconds()
            output += f"  Duration: {duration:.1f}s\n"

        output += "\n"

    return output


async def tool_list_schedules(args: Dict[str, Any]) -> str:
    """List all Temporal schedules."""
    client = await get_temporal_client()

    schedules = []
    schedule_iterator = await client.list_schedules()

    async for schedule in schedule_iterator:
        schedules.append(schedule)

    output = f"📅 **Temporal Schedules** ({len(schedules)})\n\n"

    for schedule in schedules:
        output += f"**{schedule.id}**\n"

        if schedule.schedule.state:
            paused = schedule.schedule.state.paused
            status = "⏸️ PAUSED" if paused else "▶️ ACTIVE"
            output += f"  Status: {status}\n"

            if schedule.schedule.state.note:
                output += f"  Note: {schedule.schedule.state.note}\n"

        if schedule.schedule.spec and schedule.schedule.spec.cron_expressions:
            output += f"  Cron: {schedule.schedule.spec.cron_expressions}\n"

        output += "\n"

    return output


async def tool_pause_schedule(args: Dict[str, Any]) -> str:
    """
    Pause a schedule.

    Args:
        schedule_id: Schedule ID to pause
        note: Optional note explaining why paused
    """
    client = await get_temporal_client()

    schedule_id = args.get('schedule_id')
    note = args.get('note', 'Paused via MCP')

    if not schedule_id:
        return "❌ schedule_id required"

    handle = client.get_schedule_handle(schedule_id)
    await handle.pause(note=note)

    return f"✅ Schedule **{schedule_id}** paused\n\nNote: {note}"


async def tool_unpause_schedule(args: Dict[str, Any]) -> str:
    """
    Unpause a schedule.

    Args:
        schedule_id: Schedule ID to unpause
        note: Optional note
    """
    client = await get_temporal_client()

    schedule_id = args.get('schedule_id')
    note = args.get('note', 'Unpaused via MCP')

    if not schedule_id:
        return "❌ schedule_id required"

    handle = client.get_schedule_handle(schedule_id)
    await handle.unpause(note=note)

    return f"✅ Schedule **{schedule_id}** unpaused\n\nNote: {note}"


def format_history_event(event: HistoryEvent) -> str:
    """Format a single history event for display."""
    try:
        event_type_name = EventType.Name(event.event_type)
        # Remove EVENT_TYPE_ prefix for readability
        event_type_display = event_type_name.replace("EVENT_TYPE_", "")
    except:
        event_type_display = f"UNKNOWN_EVENT_TYPE_{event.event_type}"

    output = f"**[{event.event_id}]** {event_type_display}\n"
    output += f"  Time: {event.event_time}\n"

    # Add type-specific details
    try:
        if event.event_type == 1:  # WORKFLOW_EXECUTION_STARTED
            if hasattr(event, 'workflow_execution_started_event_attributes'):
                attrs = event.workflow_execution_started_event_attributes
                if hasattr(attrs, 'task_queue') and attrs.task_queue:
                    output += f"  Task Queue: {attrs.task_queue.name}\n"

        elif event.event_type == 2:  # WORKFLOW_EXECUTION_COMPLETED
            if hasattr(event, 'workflow_execution_completed_event_attributes'):
                attrs = event.workflow_execution_completed_event_attributes
                if hasattr(attrs, 'result') and attrs.result:
                    result_str = str(attrs.result)[:200]
                    output += f"  Result: {result_str}\n"

        elif event.event_type == 3:  # WORKFLOW_EXECUTION_FAILED
            if hasattr(event, 'workflow_execution_failed_event_attributes'):
                attrs = event.workflow_execution_failed_event_attributes
                if hasattr(attrs, 'failure') and attrs.failure:
                    output += f"  ❌ Failure: {attrs.failure.message if hasattr(attrs.failure, 'message') else 'Unknown'}\n"

        elif event.event_type == 4:  # WORKFLOW_EXECUTION_TIMED_OUT
            if hasattr(event, 'workflow_execution_timed_out_event_attributes'):
                output += f"  ⏱️ Workflow timed out\n"

        elif event.event_type == 9:  # WORKFLOW_TASK_FAILED
            if hasattr(event, 'workflow_task_failed_event_attributes'):
                attrs = event.workflow_task_failed_event_attributes
                if hasattr(attrs, 'cause'):
                    output += f"  ❌ Cause: {attrs.cause}\n"
                if hasattr(attrs, 'failure') and attrs.failure and hasattr(attrs.failure, 'message'):
                    output += f"  Failure: {attrs.failure.message}\n"

        elif event.event_type == 10:  # ACTIVITY_TASK_SCHEDULED
            if hasattr(event, 'activity_task_scheduled_event_attributes'):
                attrs = event.activity_task_scheduled_event_attributes
                if hasattr(attrs, 'activity_type') and attrs.activity_type:
                    output += f"  Activity: {attrs.activity_type.name}\n"
                if hasattr(attrs, 'task_queue') and attrs.task_queue:
                    output += f"  Task Queue: {attrs.task_queue.name}\n"

        elif event.event_type == 11:  # ACTIVITY_TASK_STARTED
            if hasattr(event, 'activity_task_started_event_attributes'):
                attrs = event.activity_task_started_event_attributes
                if hasattr(attrs, 'attempt'):
                    output += f"  Attempt: {attrs.attempt}\n"

        elif event.event_type == 12:  # ACTIVITY_TASK_COMPLETED
            if hasattr(event, 'activity_task_completed_event_attributes'):
                attrs = event.activity_task_completed_event_attributes
                if hasattr(attrs, 'result') and attrs.result:
                    result_str = str(attrs.result)[:200]
                    output += f"  Result: {result_str}\n"

        elif event.event_type == 13:  # ACTIVITY_TASK_FAILED
            if hasattr(event, 'activity_task_failed_event_attributes'):
                attrs = event.activity_task_failed_event_attributes
                if hasattr(attrs, 'failure') and attrs.failure and hasattr(attrs.failure, 'message'):
                    output += f"  ❌ Failure: {attrs.failure.message}\n"
                if hasattr(attrs, 'retry_state'):
                    output += f"  Retry State: {attrs.retry_state}\n"

        elif event.event_type == 14:  # ACTIVITY_TASK_TIMED_OUT
            if hasattr(event, 'activity_task_timed_out_event_attributes'):
                attrs = event.activity_task_timed_out_event_attributes
                if hasattr(attrs, 'failure') and attrs.failure and hasattr(attrs.failure, 'message'):
                    output += f"  ⏱️ Timeout: {attrs.failure.message}\n"
                if hasattr(attrs, 'retry_state'):
                    output += f"  Retry State: {attrs.retry_state}\n"

        elif event.event_type == 15:  # TIMER_STARTED
            if hasattr(event, 'timer_started_event_attributes'):
                attrs = event.timer_started_event_attributes
                if hasattr(attrs, 'start_to_fire_timeout'):
                    output += f"  Duration: {attrs.start_to_fire_timeout}\n"

        elif event.event_type == 16:  # TIMER_FIRED
            if hasattr(event, 'timer_fired_event_attributes'):
                output += f"  Timer completed\n"

    except Exception as e:
        output += f"  (Could not parse event details: {str(e)})\n"

    return output


def format_failure_event(event: HistoryEvent) -> str:
    """Format failure event with detailed error information."""
    try:
        event_type_name = EventType.Name(event.event_type).replace("EVENT_TYPE_", "")
    except:
        event_type_name = f"UNKNOWN_{event.event_type}"

    output = f"### {event_type_name} (Event #{event.event_id})\n"
    output += f"**Time:** {event.event_time}\n"

    # Get failure details based on event type
    failure = None
    try:
        if event.event_type == 3:  # WORKFLOW_EXECUTION_FAILED
            if hasattr(event, 'workflow_execution_failed_event_attributes'):
                attrs = event.workflow_execution_failed_event_attributes
                if hasattr(attrs, 'failure'):
                    failure = attrs.failure

        elif event.event_type == 9:  # WORKFLOW_TASK_FAILED
            if hasattr(event, 'workflow_task_failed_event_attributes'):
                attrs = event.workflow_task_failed_event_attributes
                if hasattr(attrs, 'failure'):
                    failure = attrs.failure
                if hasattr(attrs, 'cause'):
                    output += f"**Cause:** {attrs.cause}\n"

        elif event.event_type == 13:  # ACTIVITY_TASK_FAILED
            if hasattr(event, 'activity_task_failed_event_attributes'):
                attrs = event.activity_task_failed_event_attributes
                if hasattr(attrs, 'failure'):
                    failure = attrs.failure
                if hasattr(attrs, 'retry_state'):
                    output += f"**Retry State:** {attrs.retry_state}\n"

        elif event.event_type == 14:  # ACTIVITY_TASK_TIMED_OUT
            if hasattr(event, 'activity_task_timed_out_event_attributes'):
                attrs = event.activity_task_timed_out_event_attributes
                if hasattr(attrs, 'failure'):
                    failure = attrs.failure
                if hasattr(attrs, 'retry_state'):
                    output += f"**Retry State:** {attrs.retry_state}\n"

        if failure:
            if hasattr(failure, 'message'):
                output += f"**Error Message:** {failure.message}\n"

            if hasattr(failure, 'stack_trace') and failure.stack_trace:
                stack_trace = failure.stack_trace
                if len(stack_trace) > 2000:
                    stack_trace = stack_trace[:2000] + "\n... (truncated)"
                output += f"**Stack Trace:**\n```\n{stack_trace}\n```\n"

            if hasattr(failure, 'cause') and failure.cause:
                output += f"**Cause:** {failure.cause}\n"

    except Exception as e:
        output += f"(Could not parse failure details: {str(e)})\n"

    return output


async def tool_get_workflow_execution_details(args: Dict[str, Any]) -> str:
    """
    Get comprehensive workflow execution details including full event history.

    Args:
        workflow_id: The workflow ID to query
        run_id: Specific run ID (optional, defaults to latest)
        include_full_history: Include complete event timeline (default: True)
    """
    workflow_id = args.get('workflow_id')
    run_id = args.get('run_id')
    include_full_history = args.get('include_full_history', True)

    # Validation
    if not workflow_id:
        return "❌ Error: workflow_id parameter is required\n\nUsage: get_workflow_execution_details(workflow_id='your-workflow-id')"

    # Get workflow handle
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        description = await handle.describe()
    except RPCError as e:
        error_str = str(e).lower()
        if "not found" in error_str:
            return f"❌ Workflow not found: {workflow_id}\n\nThis workflow does not exist or may have been deleted."
        elif run_id and "run" in error_str:
            return f"❌ Invalid run ID: {run_id}\n\nRun ID not found for workflow {workflow_id}"
        else:
            return f"❌ Failed to query workflow: {str(e)}"
    except Exception as e:
        return f"❌ Failed to connect or query workflow: {str(e)}\n\nCheck Temporal server at {TEMPORAL_HOST}"

    # Build output - Section 1: Summary
    output = "🔍 **Workflow Execution Details**\n\n"
    output += "## Summary\n"
    output += f"**Workflow ID:** `{description.id}`\n"
    output += f"**Run ID:** `{description.run_id}`\n"
    output += f"**Type:** {description.workflow_type}\n"

    # Status with emoji
    status_emoji_map = {
        "RUNNING": "🏃",
        "COMPLETED": "✅",
        "FAILED": "❌",
        "CANCELED": "⛔",
        "CANCELLED": "⛔",
        "TERMINATED": "🛑",
        "TIMED_OUT": "⏱️",
        "CONTINUED_AS_NEW": "🔄"
    }

    status_name = description.status.name if hasattr(description.status, 'name') else str(description.status)
    status_emoji = status_emoji_map.get(status_name, "❓")

    output += f"**Status:** {status_emoji} {status_name}\n"
    output += f"**Start Time:** {description.start_time}\n"

    if description.close_time:
        duration = (description.close_time - description.start_time).total_seconds()
        output += f"**End Time:** {description.close_time}\n"
        output += f"**Duration:** {duration:.2f}s\n"
    else:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        running_time = (now - description.start_time).total_seconds()
        output += f"**Running Time:** {running_time:.2f}s\n"

    output += f"**History Length:** {description.history_length} events\n"
    output += "\n"

    # Fetch history if requested
    events = []
    if include_full_history:
        try:
            history = await handle.fetch_history(
                event_filter_type=WorkflowHistoryEventFilterType.ALL_EVENT
            )
            events = list(history.events)

            # Warn if history is large
            if len(events) > 500:
                output += f"⚠️ Large history detected ({len(events)} events). Showing all events.\n\n"
        except Exception as e:
            output += f"\n⚠️ Could not fetch full history: {str(e)}\n"
            output += "Showing workflow summary only.\n\n"

    # Build output - Section 2: Event Timeline
    if events:
        output += "## Event Timeline\n\n"
        for event in events:
            output += format_history_event(event)
            output += "\n"

    # Build output - Section 3: Error Analysis
    failures = [e for e in events if e.event_type in [3, 9, 13, 14]]
    if failures:
        output += "## ⚠️ Error Analysis\n\n"
        output += f"Found {len(failures)} failure event(s)\n\n"
        for failure_event in failures:
            output += format_failure_event(failure_event)
            output += "\n"

    return output


# ============================================================================
# STORAGE MODULE - Task Outputs & Execution Logs
# ============================================================================

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "dXn0xUUpebj1ooW9nI0gJMQJMrJloLaVexQkDm8XvWN6CYNwd3JMXiVUuBcgqr4m")
DB_NAME = os.getenv("DB_NAME", "postgres")


async def get_storage_pool() -> asyncpg.Pool:
    """Get or create PostgreSQL connection pool."""
    global _storage_pool

    if _storage_pool is None:
        _storage_pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_size=1,
            max_size=5
        )

    return _storage_pool


async def tool_save_output(args: Dict[str, Any]) -> str:
    """
    Save task output to storage.

    Args:
        agent_name: Agent that produced output
        output_type: Type (report, analysis, data, error, summary, recommendation)
        content: The actual output content
        title: Optional title
        tags: Optional list of tags
        metadata: Optional metadata dict
    """
    pool = await get_storage_pool()

    agent_name = args.get('agent_name')
    output_type = args.get('output_type')
    content = args.get('content')
    title = args.get('title')
    tags = args.get('tags', [])
    metadata = args.get('metadata', {})

    if not all([agent_name, output_type, content]):
        return "❌ agent_name, output_type, and content required"

    query = """
        INSERT INTO agent_outputs
        (agent_name, output_type, content, title, tags, metadata)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
    """

    async with pool.acquire() as conn:
        output_id = await conn.fetchval(
            query,
            agent_name,
            output_type,
            content,
            title,
            tags,
            json.dumps(metadata) if metadata else None
        )

    output = f"✅ **Output Saved**\n\n"
    output += f"**ID:** {output_id}\n"
    output += f"**Agent:** {agent_name}\n"
    output += f"**Type:** {output_type}\n"

    if title:
        output += f"**Title:** {title}\n"

    if tags:
        output += f"**Tags:** {', '.join(tags)}\n"

    return output


async def tool_get_outputs(args: Dict[str, Any]) -> str:
    """
    Get recent task outputs.

    Args:
        agent_name: Filter by agent name
        output_type: Filter by type
        limit: Max results (default: 10)
    """
    pool = await get_storage_pool()

    agent_name = args.get('agent_name')
    output_type = args.get('output_type')
    limit = args.get('limit', 10)

    query = """
        SELECT id, agent_name, output_type, title, tags, created_at,
               LEFT(content, 200) as content_preview
        FROM agent_outputs
        WHERE 1=1
    """

    params = []

    if agent_name:
        params.append(agent_name)
        query += f" AND agent_name = ${len(params)}"

    if output_type:
        params.append(output_type)
        query += f" AND output_type = ${len(params)}"

    query += f" ORDER BY created_at DESC LIMIT ${len(params) + 1}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    output = f"📝 **Task Outputs** ({len(rows)})\n\n"

    for row in rows:
        output += f"**[{row['id']}] {row['title'] or row['agent_name']}**\n"
        output += f"  Agent: {row['agent_name']}\n"
        output += f"  Type: {row['output_type']}\n"
        output += f"  Time: {row['created_at']}\n"

        if row['tags']:
            output += f"  Tags: {', '.join(row['tags'])}\n"

        if row['content_preview']:
            preview = row['content_preview'].replace('\n', ' ')
            output += f"  Preview: {preview}...\n"

        output += "\n"

    return output


# ============================================================================
# MCP SERVER SETUP
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools from all modules."""
    return [
        # TEMPORAL - Workflow Management
        Tool(
            name="trigger_workflow",
            description="Start a workflow execution immediately",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_type": {
                        "type": "string",
                        "description": "Workflow class name (e.g., 'FeedPublisherWorkflow')"
                    },
                    "workflow_args": {
                        "type": "array",
                        "description": "List of arguments for workflow"
                    },
                    "workflow_id": {
                        "type": "string",
                        "description": "Optional custom workflow ID"
                    },
                    "timeout_minutes": {
                        "type": "number",
                        "description": "Execution timeout (default: 30)"
                    }
                },
                "required": ["workflow_type"]
            }
        ),
        Tool(
            name="list_workflows",
            description="List recent workflow executions",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "Max workflows (default: 10)"
                    }
                }
            }
        ),
        Tool(
            name="list_schedules",
            description="List all Temporal schedules",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="pause_schedule",
            description="Pause a schedule",
            inputSchema={
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "string"},
                    "note": {"type": "string"}
                },
                "required": ["schedule_id"]
            }
        ),
        Tool(
            name="unpause_schedule",
            description="Unpause a schedule",
            inputSchema={
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "string"},
                    "note": {"type": "string"}
                },
                "required": ["schedule_id"]
            }
        ),
        Tool(
            name="get_workflow_execution_details",
            description="Get comprehensive workflow execution details including full event history (like Temporal UI)",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "Workflow ID to query"
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Specific run ID (optional, defaults to latest run)"
                    },
                    "include_full_history": {
                        "type": "boolean",
                        "description": "Include complete event timeline (default: true)"
                    }
                },
                "required": ["workflow_id"]
            }
        ),

        # STORAGE - Task Outputs
        Tool(
            name="save_output",
            description="Save task output to storage",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "output_type": {"type": "string"},
                    "content": {"type": "string"},
                    "title": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"}
                },
                "required": ["agent_name", "output_type", "content"]
            }
        ),
        Tool(
            name="get_outputs",
            description="Get recent task outputs",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "output_type": {"type": "string"},
                    "limit": {"type": "number"}
                }
            }
        ),

        # LANGFUSE - LLM Tracing & Costs
        Tool(
            name="list_traces",
            description="List recent workflow traces from Langfuse",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Max traces (default: 20)"},
                    "hours": {"type": "number", "description": "Only last N hours"},
                    "workflow_name": {"type": "string", "description": "Filter by name"}
                }
            }
        ),
        Tool(
            name="get_trace_details",
            description="Get detailed trace by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string"}
                },
                "required": ["trace_id"]
            }
        ),
        Tool(
            name="get_costs",
            description="Get cost summary from Langfuse",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {"type": "number", "description": "Last N hours (default: 24)"}
                }
            }
        ),
        Tool(
            name="get_recent_executions",
            description="Get recent workflow executions from Langfuse",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number"}
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Route tool calls to appropriate module."""
    try:
        args = arguments if isinstance(arguments, dict) else {}

        # TEMPORAL tools
        if name == "trigger_workflow":
            result = await tool_trigger_workflow(args)
        elif name == "list_workflows":
            result = await tool_list_workflows(args)
        elif name == "list_schedules":
            result = await tool_list_schedules(args)
        elif name == "pause_schedule":
            result = await tool_pause_schedule(args)
        elif name == "unpause_schedule":
            result = await tool_unpause_schedule(args)
        elif name == "get_workflow_execution_details":
            result = await tool_get_workflow_execution_details(args)

        # STORAGE tools
        elif name == "save_output":
            result = await tool_save_output(args)
        elif name == "get_outputs":
            result = await tool_get_outputs(args)

        # LANGFUSE tools
        elif name == "list_traces":
            result = await tool_list_traces(args)
        elif name == "get_trace_details":
            result = await tool_get_trace_details(args)
        elif name == "get_costs":
            result = await tool_get_costs(args)
        elif name == "get_recent_executions":
            result = await tool_get_recent_executions(args)

        else:
            result = f"❌ Unknown tool: {name}"

        return [TextContent(type="text", text=result)]

    except Exception as e:
        error_msg = f"❌ Tool execution failed: {str(e)}"
        return [TextContent(type="text", text=error_msg)]


async def main():
    """Run MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
