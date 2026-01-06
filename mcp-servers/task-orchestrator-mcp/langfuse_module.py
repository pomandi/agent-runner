"""
Langfuse Module for Task Orchestrator MCP
==========================================
Query Langfuse traces, costs, and execution history via API.
"""
import os
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

# Langfuse Configuration
LANGFUSE_HOST = os.getenv('LANGFUSE_HOST', 'https://leng.pomandi.com')
LANGFUSE_PUBLIC_KEY = os.getenv('LANGFUSE_PUBLIC_KEY', '')
LANGFUSE_SECRET_KEY = os.getenv('LANGFUSE_SECRET_KEY', '')


class LangfuseClient:
    """Client for Langfuse Public API"""

    def __init__(self):
        self.base_url = f"{LANGFUSE_HOST}/api/public"
        self.auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
        self.timeout = 30.0

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to Langfuse API"""
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                auth=self.auth,
                timeout=self.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response.json()

    async def list_traces(
        self,
        limit: int = 20,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        List workflow traces from Langfuse.

        Args:
            limit: Max traces to return (default: 20)
            from_timestamp: ISO timestamp start filter
            to_timestamp: ISO timestamp end filter
            name: Filter by trace name (e.g., "workflow:FeedPublisherWorkflow")
            tags: Filter by tags

        Returns:
            {
                "data": [trace objects],
                "meta": {"page": 1, "limit": 20, "totalItems": 50}
            }
        """
        params = {"limit": limit}

        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        if name:
            params["name"] = name
        if tags:
            params["tags"] = tags

        return await self._request("GET", "/traces", params=params)

    async def get_trace(self, trace_id: str) -> Dict[str, Any]:
        """
        Get detailed trace by ID.

        Returns full trace with all observations (spans, generations).
        """
        return await self._request("GET", f"/traces/{trace_id}")

    async def list_observations(
        self,
        trace_id: Optional[str] = None,
        limit: int = 20,
        observation_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List observations (spans, generations, events).

        Args:
            trace_id: Filter by trace ID
            limit: Max observations to return
            observation_type: Filter by type (SPAN, GENERATION, EVENT)

        Returns:
            {
                "data": [observation objects],
                "meta": {...}
            }
        """
        params = {"limit": limit}

        if trace_id:
            params["traceId"] = trace_id
        if observation_type:
            params["type"] = observation_type

        return await self._request("GET", "/observations", params=params)

    async def get_costs_summary(
        self,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate total costs from traces.

        Aggregates cost_usd from all traces in time range.
        """
        # Get traces with cost metadata
        traces_response = await self.list_traces(
            limit=100,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp
        )

        traces = traces_response.get('data', [])

        total_cost = 0.0
        cost_by_workflow = {}
        trace_count = 0

        for trace in traces:
            trace_count += 1

            # Extract cost from metadata
            metadata = trace.get('metadata', {})
            cost = metadata.get('cost_usd', 0.0)

            if isinstance(cost, (int, float)):
                total_cost += cost

                # Group by workflow name
                name = trace.get('name', 'unknown')
                if name not in cost_by_workflow:
                    cost_by_workflow[name] = {'count': 0, 'total_cost': 0.0}

                cost_by_workflow[name]['count'] += 1
                cost_by_workflow[name]['total_cost'] += cost

        return {
            "total_cost_usd": round(total_cost, 4),
            "trace_count": trace_count,
            "by_workflow": cost_by_workflow,
            "period": {
                "from": from_timestamp,
                "to": to_timestamp
            }
        }

    async def get_recent_executions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent workflow executions with status and duration.

        Returns simplified execution list.
        """
        traces_response = await self.list_traces(limit=limit)
        traces = traces_response.get('data', [])

        executions = []

        for trace in traces:
            metadata = trace.get('metadata', {})

            execution = {
                "trace_id": trace.get('id'),
                "name": trace.get('name', 'unknown'),
                "workflow_id": metadata.get('workflow_id'),
                "status": metadata.get('status', 'unknown'),
                "timestamp": trace.get('timestamp'),
                "duration_ms": metadata.get('duration_ms', 0),
                "cost_usd": metadata.get('cost_usd', 0.0),
                "tags": trace.get('tags', [])
            }

            executions.append(execution)

        return executions


# MCP Tool Functions
async def tool_list_traces(args: Dict[str, Any]) -> str:
    """
    List recent workflow traces from Langfuse.

    Args (in args dict):
        limit: Max traces (default: 20)
        hours: Only traces from last N hours
        workflow_name: Filter by workflow name
    """
    client = LangfuseClient()

    limit = args.get('limit', 20)
    hours = args.get('hours')
    workflow_name = args.get('workflow_name')

    # Calculate time filter
    from_timestamp = None
    if hours:
        past = datetime.utcnow() - timedelta(hours=hours)
        from_timestamp = past.isoformat() + 'Z'

    result = await client.list_traces(
        limit=limit,
        from_timestamp=from_timestamp,
        name=workflow_name
    )

    traces = result.get('data', [])

    output = f"📊 **Langfuse Traces** ({len(traces)} found)\n\n"

    for trace in traces:
        metadata = trace.get('metadata', {})

        output += f"**{trace.get('name', 'unknown')}**\n"
        output += f"  ID: `{trace.get('id')}`\n"
        output += f"  Workflow ID: `{metadata.get('workflow_id', 'N/A')}`\n"
        output += f"  Status: {metadata.get('status', 'unknown')}\n"
        output += f"  Time: {trace.get('timestamp', 'N/A')}\n"

        if 'duration_ms' in metadata:
            duration = metadata['duration_ms'] / 1000
            output += f"  Duration: {duration:.1f}s\n"

        if 'cost_usd' in metadata:
            output += f"  Cost: ${metadata['cost_usd']:.4f}\n"

        output += "\n"

    return output


async def tool_get_trace_details(args: Dict[str, Any]) -> str:
    """
    Get detailed trace information by ID.

    Args:
        trace_id: Langfuse trace ID
    """
    client = LangfuseClient()
    trace_id = args.get('trace_id')

    if not trace_id:
        return "❌ trace_id required"

    trace = await client.get_trace(trace_id)

    metadata = trace.get('metadata', {})

    output = f"📊 **Trace Details**\n\n"
    output += f"**Name:** {trace.get('name', 'unknown')}\n"
    output += f"**ID:** `{trace.get('id')}`\n"
    output += f"**Workflow ID:** `{metadata.get('workflow_id', 'N/A')}`\n"
    output += f"**Run ID:** `{metadata.get('run_id', 'N/A')}`\n"
    output += f"**Status:** {metadata.get('status', 'unknown')}\n"
    output += f"**Timestamp:** {trace.get('timestamp')}\n"

    if 'duration_ms' in metadata:
        duration = metadata['duration_ms'] / 1000
        output += f"**Duration:** {duration:.2f}s\n"

    if 'cost_usd' in metadata:
        output += f"**Cost:** ${metadata['cost_usd']:.4f}\n"

    # List observations (activities/spans)
    observations = trace.get('observations', [])

    if observations:
        output += f"\n**Activities** ({len(observations)}):\n\n"

        for obs in observations[:10]:  # Limit to 10
            obs_name = obs.get('name', 'unknown')
            obs_type = obs.get('type', 'unknown')
            obs_metadata = obs.get('metadata', {})

            output += f"  - **{obs_name}** ({obs_type})\n"

            if 'duration_ms' in obs_metadata:
                obs_duration = obs_metadata['duration_ms'] / 1000
                output += f"    Duration: {obs_duration:.2f}s\n"

            if 'status' in obs_metadata:
                output += f"    Status: {obs_metadata['status']}\n"

    return output


async def tool_get_costs(args: Dict[str, Any]) -> str:
    """
    Get cost summary from Langfuse traces.

    Args:
        hours: Only costs from last N hours (default: 24)
    """
    client = LangfuseClient()

    hours = args.get('hours', 24)

    # Calculate time range
    now = datetime.utcnow()
    past = now - timedelta(hours=hours)

    from_timestamp = past.isoformat() + 'Z'
    to_timestamp = now.isoformat() + 'Z'

    summary = await client.get_costs_summary(
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp
    )

    output = f"💰 **Cost Summary** (Last {hours}h)\n\n"
    output += f"**Total Cost:** ${summary['total_cost_usd']:.4f}\n"
    output += f"**Executions:** {summary['trace_count']}\n\n"

    if summary['by_workflow']:
        output += "**By Workflow:**\n\n"

        for workflow_name, data in summary['by_workflow'].items():
            avg_cost = data['total_cost'] / data['count'] if data['count'] > 0 else 0

            output += f"  - **{workflow_name}**\n"
            output += f"    Executions: {data['count']}\n"
            output += f"    Total: ${data['total_cost']:.4f}\n"
            output += f"    Avg: ${avg_cost:.4f}\n\n"

    return output


async def tool_get_recent_executions(args: Dict[str, Any]) -> str:
    """
    Get recent workflow executions from Langfuse.

    Args:
        limit: Max executions (default: 10)
    """
    client = LangfuseClient()
    limit = args.get('limit', 10)

    executions = await client.get_recent_executions(limit=limit)

    output = f"🔄 **Recent Executions** ({len(executions)})\n\n"

    for exec in executions:
        status_emoji = {
            'completed': '✅',
            'failed': '❌',
            'running': '🏃'
        }.get(exec['status'], '❓')

        output += f"{status_emoji} **{exec['name']}**\n"
        output += f"  Workflow ID: `{exec['workflow_id']}`\n"
        output += f"  Status: {exec['status']}\n"
        output += f"  Time: {exec['timestamp']}\n"

        if exec['duration_ms']:
            duration = exec['duration_ms'] / 1000
            output += f"  Duration: {duration:.1f}s\n"

        if exec['cost_usd']:
            output += f"  Cost: ${exec['cost_usd']:.4f}\n"

        output += "\n"

    return output
