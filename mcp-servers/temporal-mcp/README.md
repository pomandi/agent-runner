# Temporal MCP Server

MCP (Model Context Protocol) server for managing Temporal workflows and schedules.

## Features

- 🚀 **Trigger workflows** - Start workflow executions immediately
- 📅 **Manage schedules** - Create, update, delete, pause/unpause schedules
- 📊 **Monitor workflows** - List workflows, get results, check status
- ⏱️ **Quick testing** - Create test schedules that trigger in N minutes
- 🎯 **Manual triggers** - Trigger schedules outside their scheduled times

## Installation

```bash
cd mcp-servers/temporal-mcp
pip install -r requirements.txt
```

## Configuration

Set environment variables in `.env` or export them:

```bash
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=agent-tasks
```

For Coolify deployment, use the deployed Temporal server:
```bash
TEMPORAL_HOST=46.224.117.155:7233
```

## MCP Configuration

Add to your Claude Code MCP settings (`~/.claude/mcp.json`):

```json
{
  "mcpServers": {
    "temporal": {
      "command": "python",
      "args": ["/path/to/agent-runner/mcp-servers/temporal-mcp/server.py"],
      "env": {
        "TEMPORAL_HOST": "46.224.117.155:7233",
        "TEMPORAL_NAMESPACE": "default",
        "TEMPORAL_TASK_QUEUE": "agent-tasks"
      }
    }
  }
}
```

## Available Tools

### Workflow Management

#### `trigger_workflow`
Start a workflow execution immediately.

**Parameters:**
- `workflow_type` (required): Workflow type (`feed-publisher`)
- `brand` (required): Brand name (`pomandi` or `costume`)
- `workflow_id` (optional): Custom workflow ID

**Example:**
```json
{
  "workflow_type": "feed-publisher",
  "brand": "pomandi"
}
```

**Returns:**
```json
{
  "status": "started",
  "workflow_id": "feed-publisher-pomandi-1234567890",
  "run_id": "abc123...",
  "workflow_type": "feed-publisher",
  "brand": "pomandi"
}
```

#### `get_workflow_result`
Get the result of a workflow execution. Waits for completion if still running.

**Parameters:**
- `workflow_id` (required): Workflow ID
- `run_id` (optional): Specific run ID
- `timeout_seconds` (optional): Max wait time (default: 300)

**Example:**
```json
{
  "workflow_id": "feed-publisher-pomandi-1234567890",
  "timeout_seconds": 600
}
```

#### `list_workflows`
List recent workflow executions.

**Parameters:**
- `limit` (optional): Max results (default: 10)
- `status` (optional): Filter by status (`running`, `completed`, `failed`, `all`)

**Example:**
```json
{
  "limit": 20,
  "status": "completed"
}
```

#### `cancel_workflow`
Cancel a running workflow.

**Parameters:**
- `workflow_id` (required): Workflow ID to cancel
- `run_id` (optional): Specific run ID

### Schedule Management

#### `list_schedules`
List all Temporal schedules.

**Example:**
```json
{}
```

**Returns:**
```json
{
  "total": 3,
  "schedules": [
    {
      "schedule_id": "pomandi-daily-posts",
      "paused": false,
      "note": "Daily social media posts for Pomandi",
      "cron_expressions": ["0 9,18 * * *"]
    }
  ]
}
```

#### `create_schedule`
Create a new recurring schedule.

**Parameters:**
- `schedule_id` (required): Unique schedule ID
- `workflow_type` (required): Workflow type (`feed-publisher`)
- `brand` (required): Brand name
- `cron_expression` (required): Cron expression (e.g., `"0 9,18 * * *"`)
- `note` (optional): Description
- `paused` (optional): Create paused (default: false)

**Example:**
```json
{
  "schedule_id": "pomandi-weekend-posts",
  "workflow_type": "feed-publisher",
  "brand": "pomandi",
  "cron_expression": "0 12 * * 0,6",
  "note": "Weekend posts at noon UTC"
}
```

#### `delete_schedule`
Delete a schedule permanently.

**Parameters:**
- `schedule_id` (required): Schedule ID

#### `pause_schedule`
Pause a schedule (stops triggering).

**Parameters:**
- `schedule_id` (required): Schedule ID
- `note` (optional): Pause reason

#### `unpause_schedule`
Resume a paused schedule.

**Parameters:**
- `schedule_id` (required): Schedule ID
- `note` (optional): Resume note

#### `trigger_schedule_now`
Trigger a schedule immediately (outside scheduled times).

**Parameters:**
- `schedule_id` (required): Schedule ID

**Example:**
```json
{
  "schedule_id": "pomandi-daily-posts"
}
```

#### `create_test_schedule`
Create a test schedule that triggers in N minutes.

**Parameters:**
- `workflow_type` (required): Workflow type
- `brand` (required): Brand name
- `minutes_from_now` (optional): Minutes until trigger (default: 2)

**Example:**
```json
{
  "workflow_type": "feed-publisher",
  "brand": "pomandi",
  "minutes_from_now": 5
}
```

## Usage Examples

### Test End-to-End System

```bash
# 1. Create test schedule (triggers in 2 minutes)
mcp__temporal__create_test_schedule({
  "workflow_type": "feed-publisher",
  "brand": "pomandi",
  "minutes_from_now": 2
})

# 2. Wait 2 minutes, then list workflows to see execution
mcp__temporal__list_workflows({
  "limit": 5,
  "status": "all"
})

# 3. Get the workflow result
mcp__temporal__get_workflow_result({
  "workflow_id": "feed-publisher-pomandi-...",
  "timeout_seconds": 300
})
```

### Manual Workflow Trigger

```bash
# Trigger workflow immediately
mcp__temporal__trigger_workflow({
  "workflow_type": "feed-publisher",
  "brand": "costume"
})

# Get the result
mcp__temporal__get_workflow_result({
  "workflow_id": "feed-publisher-costume-1234567890",
  "timeout_seconds": 600
})
```

### Schedule Management

```bash
# List all schedules
mcp__temporal__list_schedules({})

# Pause a schedule
mcp__temporal__pause_schedule({
  "schedule_id": "pomandi-daily-posts",
  "note": "Pausing for maintenance"
})

# Trigger manually instead
mcp__temporal__trigger_schedule_now({
  "schedule_id": "pomandi-daily-posts"
})

# Resume schedule
mcp__temporal__unpause_schedule({
  "schedule_id": "pomandi-daily-posts"
})
```

### Create Custom Schedule

```bash
# Create schedule for 3x daily posts
mcp__temporal__create_schedule({
  "schedule_id": "pomandi-3x-daily",
  "workflow_type": "feed-publisher",
  "brand": "pomandi",
  "cron_expression": "0 9,14,20 * * *",
  "note": "Morning, afternoon, and evening posts"
})
```

## Cron Expression Examples

```
"0 9 * * *"        # Daily at 9:00 UTC
"0 9,18 * * *"     # Daily at 9:00 and 18:00 UTC
"0 12 * * 1-5"     # Weekdays at noon UTC
"0 10 * * 0,6"     # Weekends at 10:00 UTC
"*/30 * * * *"     # Every 30 minutes
"0 */4 * * *"      # Every 4 hours
```

## Troubleshooting

### Connection Issues

If you get connection errors:

1. Check Temporal server is running:
```bash
curl http://46.224.117.155:7233
```

2. Verify environment variables:
```bash
echo $TEMPORAL_HOST
```

3. Test with Temporal UI:
```
http://46.224.117.155:8088
```

### Workflow Failures

Check workflow logs in Temporal UI or use:

```bash
mcp__temporal__get_workflow_result({
  "workflow_id": "your-workflow-id"
})
```

The error will be in the returned JSON.

## Architecture

```
┌─────────────────┐
│  Claude Code    │
│   MCP Client    │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Temporal MCP   │
│     Server      │
└────────┬────────┘
         │
         ↓
┌─────────────────┐       ┌──────────────┐
│ Temporal Server │←──────│   Worker     │
│   (Port 7233)   │       │  Container   │
└─────────────────┘       └──────────────┘
         │
         ↓
┌─────────────────┐
│   PostgreSQL    │
│  (Temporal DB)  │
└─────────────────┘
```

## License

MIT
