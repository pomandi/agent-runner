#!/bin/bash
# Scheduled execution wrapper
# Called by cron at scheduled times

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export HOME="/root"

echo "========================================"
echo "[SCHEDULED RUN] $(date)"
echo "Agent: $AGENT_NAME"
echo "Task: $AGENT_TASK"
echo "========================================"

# Run the agent
/app/run-agent.sh

echo "========================================"
echo "[SCHEDULED RUN COMPLETE] $(date)"
echo "========================================"
