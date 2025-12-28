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
echo -e "${GREEN}Schedule:${NC} ${AGENT_SCHEDULE:-None (manual/API only)}"
echo -e "${GREEN}API:${NC} http://localhost:8080"
echo -e "${GREEN}Time:${NC} $(date)"
echo -e "${BLUE}==========================================${NC}"

# Auto-create Claude credentials from environment variable
if [ -n "$CLAUDE_CREDENTIALS" ]; then
    echo -e "${GREEN}[OK]${NC} Creating credentials from CLAUDE_CREDENTIALS env var"
    mkdir -p /root/.claude
    echo "$CLAUDE_CREDENTIALS" > /root/.claude/.credentials.json
    chmod 600 /root/.claude/.credentials.json
    echo -e "${GREEN}[OK]${NC} Claude credentials created successfully"
elif [ -f "/root/.claude/.credentials.json" ]; then
    echo -e "${GREEN}[OK]${NC} Claude credentials found (mounted)"
else
    echo -e "${YELLOW}[WARN]${NC} Claude credentials not found"
    echo -e "${YELLOW}[WARN]${NC} Set CLAUDE_CREDENTIALS env var with JSON content"
fi

# Copy MCP config
if [ -f "/app/.mcp.json" ]; then
    cp /app/.mcp.json /root/.claude/.mcp.json
    echo -e "${GREEN}[OK]${NC} MCP config copied"
fi

# Setup cron schedule if provided
if [ -n "$AGENT_SCHEDULE" ]; then
    echo -e "${YELLOW}[CRON]${NC} Setting up schedule: $AGENT_SCHEDULE"
    crontab -r 2>/dev/null || true
    
    if [[ "$AGENT_SCHEDULE" == *"*"* ]]; then
        echo "$AGENT_SCHEDULE /app/schedule.sh >> /app/logs/cron.log 2>&1" | crontab -
    else
        CRON_LINES=""
        IFS=',' read -ra TIMES <<< "$AGENT_SCHEDULE"
        for TIME in "${TIMES[@]}"; do
            HOUR=$(echo $TIME | cut -d: -f1)
            MINUTE=$(echo $TIME | cut -d: -f2)
            CRON_LINES="$CRON_LINES$MINUTE $HOUR * * * /app/schedule.sh >> /app/logs/cron.log 2>&1\n"
            echo -e "${GREEN}[OK]${NC} Scheduled at $TIME"
        done
        echo -e "$CRON_LINES" | crontab -
    fi
    service cron start
    echo -e "${GREEN}[OK]${NC} Cron daemon started"
fi

echo -e "${BLUE}==========================================${NC}"
echo -e "${GREEN}[API]${NC} Starting API server on port 8080..."
echo -e "${BLUE}==========================================${NC}"

# Start API server (this keeps the container running)
exec python3 /app/api.py
