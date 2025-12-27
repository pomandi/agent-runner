#!/bin/bash
# Run agent with full MCP support
# Can be called manually or by scheduler

set -e

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export HOME="/root"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

AGENT_NAME="${AGENT_NAME:-feed-publisher}"
AGENT_TASK="${AGENT_TASK:-Run the agent task}"

LOG_FILE="/app/logs/${AGENT_NAME}-$(date +%Y%m%d-%H%M%S).log"

echo -e "${BLUE}[RUN]${NC} Starting agent: $AGENT_NAME"
echo -e "${BLUE}[RUN]${NC} Task: $AGENT_TASK"
echo -e "${BLUE}[RUN]${NC} Log: $LOG_FILE"
echo ""

# Ensure MCP config is in place
if [ -f "/app/.mcp.json" ]; then
    cp /app/.mcp.json /root/.claude/.mcp.json
fi

# Check credentials
if [ ! -f "/root/.claude/.credentials.json" ]; then
    echo -e "${RED}[ERROR]${NC} Claude credentials not found!"
    echo -e "${YELLOW}[FIX]${NC} Run: docker cp /root/.claude/.credentials.json <container>:/root/.claude/"
    exit 1
fi

# Determine MCP tools to allow based on agent
case "$AGENT_NAME" in
    feed-publisher)
        ALLOWED_TOOLS="mcp__feed-publisher-mcp__*"
        ;;
    caption-generator)
        ALLOWED_TOOLS="mcp__caption-generator-mcp__*"
        ;;
    *)
        ALLOWED_TOOLS="*"
        ;;
esac

# Run Claude CLI with MCP
cd /app
claude \
    --mcp-config /root/.claude/.mcp.json \
    --allowedTools "$ALLOWED_TOOLS" \
    --verbose \
    --print "$AGENT_TASK" 2>&1 | tee "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}[SUCCESS]${NC} Agent completed successfully"
else
    echo -e "${RED}[FAILED]${NC} Agent exited with code: $EXIT_CODE"
fi

echo -e "${BLUE}[RUN]${NC} Finished at: $(date)"
echo -e "${BLUE}[RUN]${NC} Log saved to: $LOG_FILE"

exit $EXIT_CODE
