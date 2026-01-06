# Task Orchestrator MCP

**Unified MCP for complete agentic task lifecycle management.**

Combines 3 specialized modules into a single interface:

## 🎯 Modules

### 1. **Temporal** - Workflow & Schedule Management
- Trigger workflows manually
- List workflow executions
- Manage schedules (list, pause, unpause)
- Monitor workflow status

### 2. **Storage** - Task Outputs & Logs
- Save task outputs to PostgreSQL
- Query recent outputs by agent/type
- Track execution history
- Store metadata and tags

### 3. **Langfuse** - LLM Tracing & Cost Tracking
- List workflow traces
- Get detailed trace information
- Calculate cost summaries
- Monitor recent executions

## 📦 Installation

### 1. Add to Claude Code MCP Settings

**File:** `~/.config/claude-code/mcp.json` (or equivalent)

```json
{
  "mcpServers": {
    "task-orchestrator": {
      "command": "python3",
      "args": [
        "/home/claude/.claude/agents/agent-runner/mcp-servers/task-orchestrator-mcp/server.py"
      ]
    }
  }
}
```

### 2. Restart Claude Code

## 🔧 Configuration

Environment variables (from .env in agent-runner):

```bash
# Temporal
TEMPORAL_HOST=46.224.117.155:7233
TEMPORAL_NAMESPACE=default
TASK_QUEUE=agent-tasks

# PostgreSQL (Storage)
DB_HOST=127.0.0.1
DB_PORT=5433
DB_USER=postgres
DB_PASSWORD=...
DB_NAME=postgres

# Langfuse
LANGFUSE_HOST=https://leng.pomandi.com
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

## 🛠️ Available Tools (13)

### Temporal Tools (5)

#### `trigger_workflow`
Start a workflow execution immediately.

```json
{
  "workflow_type": "FeedPublisherWorkflow",
  "workflow_args": ["pomandi"],
  "workflow_id": "manual-test-123",
  "timeout_minutes": 30
}
```

#### `list_workflows`
List recent workflow executions.

```json
{
  "limit": 10
}
```

#### `list_schedules`
List all Temporal schedules.

#### `pause_schedule`
Pause a schedule.

```json
{
  "schedule_id": "pomandi-daily-posts",
  "note": "Maintenance"
}
```

#### `unpause_schedule`
Unpause a schedule.

```json
{
  "schedule_id": "pomandi-daily-posts",
  "note": "Maintenance complete"
}
```

### Storage Tools (2)

#### `save_output`
Save task output to storage.

```json
{
  "agent_name": "feed-publisher",
  "output_type": "report",
  "content": "Published successfully...",
  "title": "Daily post - Pomandi",
  "tags": ["pomandi", "facebook", "instagram"],
  "metadata": {"post_id": "123456"}
}
```

#### `get_outputs`
Get recent task outputs.

```json
{
  "agent_name": "feed-publisher",
  "output_type": "report",
  "limit": 10
}
```

### Langfuse Tools (4)

#### `list_traces`
List recent workflow traces.

```json
{
  "limit": 20,
  "hours": 24,
  "workflow_name": "workflow:FeedPublisherWorkflow"
}
```

#### `get_trace_details`
Get detailed trace by ID.

```json
{
  "trace_id": "trace-abc-123"
}
```

#### `get_costs`
Get cost summary.

```json
{
  "hours": 24
}
```

#### `get_recent_executions`
Get recent executions from Langfuse.

```json
{
  "limit": 10
}
```

## 📊 Usage Examples

### Example 1: Trigger Feed Publisher Workflow

```
User: Trigger the feed publisher for Pomandi

Claude (using MCP):
- Calls: trigger_workflow
- Args: {workflow_type: "FeedPublisherWorkflow", workflow_args: ["pomandi"]}
- Result: Workflow started with ID manual-FeedPublisherWorkflow-1234567890
```

### Example 2: Check Recent Costs

```
User: Show me AI costs from the last 24 hours

Claude (using MCP):
- Calls: get_costs
- Args: {hours: 24}
- Result: Total: $0.45, 12 executions
```

### Example 3: Monitor Workflow Status

```
User: What workflows are currently running?

Claude (using MCP):
- Calls: list_workflows
- Args: {limit: 5}
- Result: 2 workflows running, 3 completed
```

## 🔍 Troubleshooting

### Connection Issues

**Temporal connection failed:**
- Check TEMPORAL_HOST is accessible
- Verify worker container is running
- Check task queue name matches

**Storage connection failed:**
- Verify PostgreSQL is running on DB_PORT
- Check DB credentials
- Ensure agent_outputs table exists

**Langfuse connection failed:**
- Verify LANGFUSE_HOST is accessible (https://leng.pomandi.com)
- Check API keys are correct
- Test: `curl -u $PUBLIC_KEY:$SECRET_KEY https://leng.pomandi.com/api/public/traces`

### Testing

Test MCP directly:

```bash
cd /home/claude/.claude/agents/agent-runner/mcp-servers/task-orchestrator-mcp
python3 server.py
```

Should start without errors and wait for stdin.

## 🎯 Benefits

### Before (3 Separate MCPs):
- ❌ temporal-mcp
- ❌ agent-outputs-mcp
- ❌ No Langfuse MCP

### After (1 Unified MCP):
- ✅ Single interface for complete task lifecycle
- ✅ Trigger → Monitor → Store → Analyze
- ✅ Langfuse tracing & cost tracking integrated
- ✅ Easier to maintain and extend

## 📈 Architecture

```
Task Orchestrator MCP
│
├─ temporal_module.py (Workflow management)
│  ├─ Connect to Temporal Server (46.224.117.155:7233)
│  ├─ Trigger workflows
│  ├─ Manage schedules
│  └─ Monitor executions
│
├─ storage_module.py (Output storage)
│  ├─ Connect to PostgreSQL (localhost:5433)
│  ├─ Save task outputs
│  └─ Query execution history
│
├─ langfuse_module.py (LLM tracing)
│  ├─ Connect to Langfuse (https://leng.pomandi.com)
│  ├─ Query traces
│  ├─ Calculate costs
│  └─ Monitor AI execution
│
└─ server.py (Main MCP server)
   └─ Routes tool calls to modules
```

## 🚀 Next Steps

1. Add to Claude Code MCP config
2. Restart Claude Code
3. Test with: "List recent workflows"
4. Verify all 13 tools are available

## 📝 Notes

- All modules share the same environment variables
- Langfuse integration is read-only (query only, no writes)
- Storage uses existing agent_outputs table
- Temporal connects to production server (read-write)
