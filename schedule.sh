#!/bin/bash
# Scheduled execution wrapper
# Called by cron at scheduled times

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export HOME="/home/agent"

# Source environment variables saved during container startup
if [ -f "/app/data/agent-env.sh" ]; then
    source /app/data/agent-env.sh
fi

# Fallback defaults if env vars not set
export AGENT_NAME="${AGENT_NAME:-feed-publisher}"
export AGENT_TASK="${AGENT_TASK:-Run the agent task}"

echo "========================================"
echo "[SCHEDULED RUN] $(date)"
echo "Agent: $AGENT_NAME"
echo "Task: $AGENT_TASK"
echo "========================================"

# Run the agent as 'agent' user
gosu agent /app/run-agent.sh

echo "========================================"
echo "[SCHEDULED RUN COMPLETE] $(date)"
echo "========================================"
