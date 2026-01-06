#!/bin/bash
# Claude Agent SDK Runner - Docker Entrypoint
#
# Environment Variables:
#   CLAUDE_CODE_OAUTH_TOKEN - Required: OAuth token from 'claude setup-token'
#   AGENT_NAME              - Required: Agent to run (feed-publisher, invoice-finder, etc.)
#   AGENT_TASK              - Optional: Task/prompt for the agent
#   LOG_LEVEL               - Optional: Logging level (default: INFO)
#   KEEP_ALIVE              - Optional: Keep container running after task (default: false)

set -e

echo "=============================================="
echo "Claude Agent SDK Runner"
echo "=============================================="
echo ""

# Check required environment
if [ -z "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
    echo "ERROR: CLAUDE_CODE_OAUTH_TOKEN is required"
    echo ""
    echo "To get a token (valid for 1 year):"
    echo "  1. Run: claude setup-token"
    echo "  2. Copy the token"
    echo "  3. Set: CLAUDE_CODE_OAUTH_TOKEN=<token>"
    exit 1
fi

if [ -z "$AGENT_NAME" ]; then
    echo "ERROR: AGENT_NAME is required"
    echo ""
    echo "Available agents:"
    python3 sdk_runner.py list
    exit 1
fi

# Default values
AGENT_TASK="${AGENT_TASK:-Run the default agent task}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
KEEP_ALIVE="${KEEP_ALIVE:-false}"

# Check run mode
RUN_MODE="${RUN_MODE:-sdk}"
API_PORT="${API_PORT:-8080}"
TEMPORAL_HOST="${TEMPORAL_HOST:-localhost:7233}"

if [ "$RUN_MODE" = "api" ]; then
    echo "Mode: API Server"
    echo "Port: $API_PORT"
    echo ""
    echo "----------------------------------------------"
    echo ""

    # Start FastAPI server
    exec python3 api.py

elif [ "$RUN_MODE" = "worker" ]; then
    echo "Mode: Temporal Worker"
    echo "Temporal Host: $TEMPORAL_HOST"
    echo "Namespace: ${TEMPORAL_NAMESPACE:-default}"
    echo "Task Queue: ${TEMPORAL_TASK_QUEUE:-agent-tasks}"
    echo ""
    echo "----------------------------------------------"
    echo ""

    # Start Temporal worker
    exec python3 -m temporal_app.worker

elif [ "$RUN_MODE" = "scheduler" ]; then
    echo "Mode: Schedule Setup"
    echo "Temporal Host: $TEMPORAL_HOST"
    echo ""
    echo "----------------------------------------------"
    echo ""

    # Setup Temporal schedules (one-time operation)
    exec python3 -m temporal_app.schedules.daily_tasks

elif [ "$RUN_MODE" = "sdk" ]; then
    echo "Mode: SDK Runner"
    echo "Agent: $AGENT_NAME"
    echo "Task: $AGENT_TASK"
    echo "Log Level: $LOG_LEVEL"
    echo ""
    echo "----------------------------------------------"
    echo ""

    # Run the agent
    python3 sdk_runner.py "$AGENT_NAME" "$AGENT_TASK"
    EXIT_CODE=$?

    echo ""
    echo "----------------------------------------------"
    echo "Agent finished with exit code: $EXIT_CODE"

    # Keep alive if requested
    if [ "$KEEP_ALIVE" = "true" ]; then
        echo ""
        echo "KEEP_ALIVE=true, container will stay running..."
        echo "Use 'docker exec' to run more agents"
        tail -f /dev/null
    fi

    exit $EXIT_CODE
else
    echo "ERROR: Invalid RUN_MODE: $RUN_MODE"
    echo "Valid modes: api, sdk, worker, scheduler"
    exit 1
fi
