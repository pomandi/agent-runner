# Agent Runner Container

Docker container for running Claude Code agents with **full visibility** into:
- Tool calls (which tool, parameters, results)
- Thinking process
- API requests/responses
- Token usage and timing

## Architecture

```
+------------------------------------------+
|           AGENT RUNNER CONTAINER         |
|                                          |
|  +----------------+   +---------------+  |
|  | claude-code-   |<--| Claude CLI    |  |
|  | logger (proxy) |   |               |  |
|  | :8000          |   | claude -p ... |  |
|  +-------+--------+   +---------------+  |
|          |                               |
|          v                               |
|  +------------------------------------+  |
|  |         VISIBLE OUTPUT             |  |
|  | - Tool calls with parameters       |  |
|  | - Thinking content                 |  |
|  | - API traffic                      |  |
|  | - Token usage                      |  |
|  +------------------------------------+  |
+------------------------------------------+
```

## Prerequisites

- Claude Max subscription (login required)
- Docker
- Claude credentials at `~/.claude/`

## Quick Start

### With Coolify

1. Create new application from this repo: `https://github.com/pomandi/agent-runner`
2. Set environment variables
3. Add volume mounts for credentials
4. Deploy

## Environment Variables

| Variable | Description | Default |
|----------|-------------|--------|
| `AGENT_NAME` | Name of agent to run | `feed-publisher` |
| `AGENT_TASK` | Task/prompt for the agent | `Run the agent task` |
| `KEEP_ALIVE` | Keep container running after task | `false` |
