#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=========================================="
echo -e "       AGENT RUNNER CONTAINER"
echo -e "==========================================${NC}"
echo -e "${GREEN}Agent:${NC} $AGENT_NAME"
echo -e "${GREEN}Task:${NC} $AGENT_TASK"
echo -e "${GREEN}Schedule:${NC} ${AGENT_SCHEDULE:-None (manual only)}"
echo -e "${GREEN}Time:${NC} $(date)"
echo -e "${BLUE}==========================================${NC}"

# Check if Claude credentials exist
if [ -f "/root/.claude/.credentials.json" ]; then
    echo -e "${GREEN}[OK]${NC} Claude credentials found"
else
    echo -e "${YELLOW}[WARN]${NC} Claude credentials not found at /root/.claude/.credentials.json"
    echo -e "${YELLOW}[WARN]${NC} Run: docker cp /root/.claude/.credentials.json <container>:/root/.claude/"
fi

# Copy MCP config
if [ -f "/app/.mcp.json" ]; then
    cp /app/.mcp.json /root/.claude/.mcp.json
    echo -e "${GREEN}[OK]${NC} MCP config copied"
fi

# Check if agent file exists
AGENT_PATH="/app/agents/${AGENT_NAME}/agent.md"
if [ -f "$AGENT_PATH" ]; then
    echo -e "${GREEN}[OK]${NC} Agent file found: $AGENT_PATH"
else
    echo -e "${YELLOW}[WARN]${NC} Agent file not found: $AGENT_PATH"
fi

# Setup cron schedule if provided
if [ -n "$AGENT_SCHEDULE" ]; then
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${YELLOW}[CRON]${NC} Setting up schedule: $AGENT_SCHEDULE"
    
    # Clear existing crontab
    crontab -r 2>/dev/null || true
    
    # Check if it's a cron expression (contains *)
    if [[ "$AGENT_SCHEDULE" == *"*"* ]]; then
        # Direct cron expression
        CRON_EXPR="$AGENT_SCHEDULE"
        echo "$CRON_EXPR /app/schedule.sh >> /app/logs/cron.log 2>&1" | crontab -
        echo -e "${GREEN}[OK]${NC} Cron schedule set: $CRON_EXPR"
    else
        # Time format: "09:00,18:00" or "09:00"
        CRON_LINES=""
        IFS=',' read -ra TIMES <<< "$AGENT_SCHEDULE"
        for TIME in "${TIMES[@]}"; do
            HOUR=$(echo $TIME | cut -d: -f1)
            MINUTE=$(echo $TIME | cut -d: -f2)
            CRON_LINE="$MINUTE $HOUR * * * /app/schedule.sh >> /app/logs/cron.log 2>&1"
            CRON_LINES="$CRON_LINES$CRON_LINE\n"
            echo -e "${GREEN}[OK]${NC} Scheduled at $TIME (cron: $MINUTE $HOUR * * *)"
        done
        echo -e "$CRON_LINES" | crontab -
    fi
    
    # Start cron daemon
    service cron start
    echo -e "${GREEN}[OK]${NC} Cron daemon started"
else
    echo -e "${YELLOW}[INFO]${NC} No schedule set. Agent runs manually only."
    echo -e "${YELLOW}[INFO]${NC} Set AGENT_SCHEDULE=\"09:00,18:00\" for scheduled runs"
fi

echo -e "${BLUE}==========================================${NC}"

# Run once on startup if RUN_ON_START is set
if [ "$RUN_ON_START" = "true" ]; then
    echo -e "${YELLOW}[STARTING]${NC} Running agent on startup..."
    /app/run-agent.sh
fi

# Keep container running
echo -e "${GREEN}[READY]${NC} Container is running. Waiting for scheduled runs..."
echo -e "${GREEN}[INFO]${NC} To run manually: docker exec <container> /app/run-agent.sh"
echo -e "${BLUE}==========================================${NC}"

# Tail logs to keep container alive and show output
tail -f /app/logs/cron.log 2>/dev/null || tail -f /dev/null
