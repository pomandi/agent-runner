# Claude Agent SDK Runner

Docker container for running Claude agents using **Claude Agent SDK**.

## Key Features

- **Pure Python SDK** - No CLI, no markdown files
- **1-Year OAuth Token** - `claude setup-token` generates long-lived token
- **Custom Tools** - Python `@tool` decorator for custom tools
- **Safety Hooks** - PreToolUse/PostToolUse callbacks
- **MCP Integration** - Access to all configured MCP servers

## Architecture

```
+------------------------------------------+
|        AGENT SDK RUNNER CONTAINER        |
|                                          |
|  +------------------------------------+  |
|  |       agents.py (Python)           |  |
|  |  - AgentConfig dataclass           |  |
|  |  - FEED_PUBLISHER, INVOICE_*       |  |
|  +----------------+-------------------+  |
|                   |                      |
|                   v                      |
|  +------------------------------------+  |
|  |     Claude Agent SDK (Python)      |  |
|  |     - query() simple mode          |  |
|  |     - ClaudeSDKClient full mode    |  |
|  +----------------+-------------------+  |
|                   |                      |
|                   v                      |
|  +------------------------------------+  |
|  |          MCP Servers               |  |
|  | - feed-publisher-mcp               |  |
|  | - expense-tracker-mcp              |  |
|  | - godaddy-mail, outlook, etc.      |  |
|  +------------------------------------+  |
+------------------------------------------+
```

## Available Agents

| Agent | Description |
|-------|-------------|
| `feed-publisher` | Publishes posts to Facebook/Instagram |
| `invoice-finder` | Finds invoices from email |
| `invoice-extractor` | Extracts data from invoice PDFs |

## Quick Start

### 1. Get OAuth Token (Valid 1 Year)

```bash
claude setup-token
# Copy the generated token
```

### 2. Deploy with Coolify

Environment variables:
```
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-xxxxx
AGENT_NAME=feed-publisher
AGENT_TASK=Publish post to Pomandi
```

### 3. Run Locally (Docker)

```bash
docker build -t agent-runner .

docker run -e CLAUDE_CODE_OAUTH_TOKEN=xxx \
           -e AGENT_NAME=feed-publisher \
           -e AGENT_TASK="Publish post to Pomandi" \
           agent-runner
```

### 4. Run Locally (Python)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run agent (simple mode)
python sdk_runner.py feed-publisher "Publish post to Pomandi"

# Run agent (full mode with custom tools + hooks)
python sdk_runner.py --full feed-publisher "Publish post to Pomandi"

# List agents
python sdk_runner.py list

# Show agent details
python sdk_runner.py info feed-publisher

# Test SDK connection
python sdk_runner.py test
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLAUDE_CODE_OAUTH_TOKEN` | **Required** - OAuth token from `claude setup-token` | - |
| `AGENT_NAME` | Agent to run | `feed-publisher` |
| `AGENT_TASK` | Task/prompt for the agent | `Run the default agent task` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `KEEP_ALIVE` | Keep container running after task | `false` |

## Project Structure

```
agent-runner/
├── agents.py           # Agent definitions (Python dataclasses)
├── sdk_runner.py       # Main runner script
├── hooks.py            # Pre/Post tool hooks
├── tools/              # Custom Python tools
│   ├── __init__.py
│   └── example_tools.py
├── mcp-servers/        # External MCP server configs
├── Dockerfile
├── entrypoint.sh
├── requirements.txt
└── README.md
```

## Adding New Agents

Edit `agents.py` and add a new AgentConfig:

```python
MY_AGENT = AgentConfig(
    name="my-agent",
    description="What the agent does",
    system_prompt="""# My Agent

Instructions for Claude here...
""",
    tools=[
        "mcp__some-mcp__*",
        "Read",
        "Write",
    ],
    max_turns=20,
)

# Register in AGENTS dict
AGENTS = {
    ...
    "my-agent": MY_AGENT,
}
```

## Adding Custom Tools

Create Python tools in `tools/` using `@tool` decorator:

```python
from claude_agent_sdk import tool

@tool(
    name="my_tool",
    description="What the tool does",
    input_schema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Parameter 1"}
        },
        "required": ["param1"]
    }
)
async def my_tool(args: dict) -> dict:
    result = do_something(args["param1"])
    return {
        "content": [{"type": "text", "text": result}]
    }

# Add to ALL_TOOLS list
ALL_TOOLS = [..., my_tool]
```

Run with `--full` flag to enable custom tools:
```bash
python sdk_runner.py --full my-agent "do something"
```

## Adding Hooks

Edit `hooks.py` to add safety or logging hooks:

```python
async def my_hook(tool_input: dict, tool_name: str) -> dict:
    if dangerous_condition:
        return {"decision": "deny", "reason": "Blocked for safety"}
    return {"decision": "allow"}

SAFETY_HOOKS = {
    "PreToolUse": [
        HookMatcher(matcher="Bash", hooks=[my_hook]),
    ],
}
```

## SDK Modes

| Mode | Function | Features |
|------|----------|----------|
| Simple | `query()` | Basic agent execution, streaming |
| Full | `ClaudeSDKClient` | Custom tools, hooks, sessions |

Simple mode (default):
```python
async for message in query(prompt=task, options=options):
    process(message)
```

Full mode (`--full` flag):
```python
async with ClaudeSDKClient(options=options) as client:
    async for message in client.process_query(task):
        process(message)
```

## Token Management

### Get Token (1 Year Validity)

```bash
claude setup-token
```

### Check Token Status

Tokens can be managed at: https://claude.ai/settings/claude-code

### Token Expired?

```bash
# Generate new token
claude setup-token

# Update in Coolify environment variables
```
