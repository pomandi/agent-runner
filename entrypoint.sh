#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================="
echo -e "       AGENT RUNNER CONTAINER"
echo -e "==========================================${NC}"
echo -e "${GREEN}Agent:${NC} $AGENT_NAME"
echo -e "${GREEN}Task:${NC} $AGENT_TASK"
echo -e "${GREEN}Time:${NC} $(date)"
echo -e "${GREEN}Log Level:${NC} $LOG_LEVEL"
echo -e "${BLUE}==========================================${NC}"

# Check if Claude credentials exist
if [ -f "/root/.claude/.credentials.json" ]; then
    echo -e "${GREEN}[OK]${NC} Claude credentials found"
else
    echo -e "${YELLOW}[WARN]${NC} Claude credentials not found at /root/.claude/.credentials.json"
    echo -e "${YELLOW}[WARN]${NC} Make sure to mount your credentials volume"
fi

# Check if agent file exists
AGENT_PATH="/app/agents/${AGENT_NAME}/agent.md"
if [ -f "$AGENT_PATH" ]; then
    echo -e "${GREEN}[OK]${NC} Agent file found: $AGENT_PATH"
else
    echo -e "${RED}[ERROR]${NC} Agent file not found: $AGENT_PATH"
    echo -e "${YELLOW}Available agents:${NC}"
    ls -la /app/agents/ 2>/dev/null || echo "No agents directory"
fi

# Create log file path
LOG_FILE="/app/logs/${AGENT_NAME}-$(date +%Y%m%d-%H%M%S).log"
echo -e "${GREEN}[LOG]${NC} Output will be saved to: $LOG_FILE"

echo -e "${BLUE}==========================================${NC}"
echo -e "${YELLOW}[STARTING]${NC} claude-code-logger proxy on :8000..."
echo -e "${BLUE}==========================================${NC}"

# Start claude-code-logger in background
npx claude-code-logger start -v &
LOGGER_PID=$!
sleep 3

# Check if logger started
if kill -0 $LOGGER_PID 2>/dev/null; then
    echo -e "${GREEN}[OK]${NC} Logger proxy running (PID: $LOGGER_PID)"
else
    echo -e "${YELLOW}[WARN]${NC} Logger proxy may not have started, continuing anyway..."
fi

echo -e "${BLUE}==========================================${NC}"
echo -e "${YELLOW}[EXECUTING]${NC} Agent: $AGENT_NAME"
echo -e "${BLUE}==========================================${NC}"
echo ""

# Run Claude CLI through the proxy for full visibility
# --verbose: Show timing and token usage
# --debug: Enable debug mode
# --allowedTools "*": Allow all tools
ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://localhost:8000/}" \
claude -p "$AGENT_NAME" \
    --verbose \
    --debug \
    --allowedTools "*" \
    "$AGENT_TASK" 2>&1 | tee "$LOG_FILE"

EXIT_CODE=$?

echo ""
echo -e "${BLUE}==========================================${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}[COMPLETED]${NC} Agent finished successfully"
else
    echo -e "${RED}[FAILED]${NC} Agent exited with code: $EXIT_CODE"
fi
echo -e "${GREEN}Time:${NC} $(date)"
echo -e "${GREEN}Log File:${NC} $LOG_FILE"
echo -e "${BLUE}==========================================${NC}"

# Keep container running if needed (for debugging)
if [ "$KEEP_ALIVE" = "true" ]; then
    echo -e "${YELLOW}[KEEP_ALIVE]${NC} Container will stay running..."
    tail -f /dev/null
fi

exit $EXIT_CODE
