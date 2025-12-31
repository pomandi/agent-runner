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

# Auto-create Claude credentials from environment variable (base64 encoded)
if [ -n "$CLAUDE_CREDENTIALS_B64" ]; then
    echo -e "${GREEN}[OK]${NC} Creating credentials from CLAUDE_CREDENTIALS_B64 env var"
    mkdir -p /root/.claude
    echo "$CLAUDE_CREDENTIALS_B64" | base64 -d > /root/.claude/.credentials.json
    chmod 600 /root/.claude/.credentials.json
    echo -e "${GREEN}[OK]${NC} Claude credentials created successfully"
elif [ -n "$CLAUDE_CREDENTIALS" ]; then
    echo -e "${GREEN}[OK]${NC} Creating credentials from CLAUDE_CREDENTIALS env var"
    mkdir -p /root/.claude
    echo "$CLAUDE_CREDENTIALS" > /root/.claude/.credentials.json
    chmod 600 /root/.claude/.credentials.json
    echo -e "${GREEN}[OK]${NC} Claude credentials created successfully"
elif [ -f "/root/.claude/.credentials.json" ]; then
    echo -e "${GREEN}[OK]${NC} Claude credentials found (mounted)"
else
    echo -e "${YELLOW}[WARN]${NC} Claude credentials not found"
    echo -e "${YELLOW}[WARN]${NC} Set CLAUDE_CREDENTIALS_B64 env var with base64 encoded JSON"
fi

# Claude Code OAuth client_id (official)
# Source: https://github.com/RavenStorm-bit/claude-token-refresh
CLAUDE_CLIENT_ID="9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Token refresh function
refresh_oauth_token() {
    echo -e "${YELLOW}[TOKEN]${NC} Attempting to refresh OAuth token..."

    # Read current credentials
    if [ ! -f "/root/.claude/.credentials.json" ]; then
        echo -e "${RED}[ERROR]${NC} No credentials file found"
        return 1
    fi

    # Extract refresh token using Python (more reliable than jq for nested JSON)
    REFRESH_TOKEN=$(python3 -c "
import json
import sys
try:
    with open('/root/.claude/.credentials.json') as f:
        data = json.load(f)
    oauth = data.get('claudeAiOauth', {})
    print(oauth.get('refreshToken', ''))
except Exception as e:
    print('', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)

    if [ -z "$REFRESH_TOKEN" ]; then
        echo -e "${RED}[ERROR]${NC} No refresh token found in credentials"
        return 1
    fi

    echo -e "${YELLOW}[TOKEN]${NC} Found refresh token, calling Anthropic API..."

    # Call Anthropic OAuth refresh endpoint
    RESPONSE=$(curl -s -X POST "https://console.anthropic.com/v1/oauth/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "grant_type=refresh_token" \
        -d "refresh_token=$REFRESH_TOKEN" \
        -d "client_id=$CLAUDE_CLIENT_ID" 2>/dev/null)
    
    # Check if response contains access_token
    if echo "$RESPONSE" | grep -q "access_token"; then
        echo -e "${GREEN}[TOKEN]${NC} Token refresh successful!"
        
        # Update credentials file with new tokens using Python
        python3 -c "
import json
import sys

response = '''$RESPONSE'''
try:
    new_tokens = json.loads(response)
    
    with open('/root/.claude/.credentials.json') as f:
        creds = json.load(f)
    
    # Update OAuth tokens
    if 'claudeAiOauth' in creds:
        creds['claudeAiOauth']['accessToken'] = new_tokens.get('access_token', creds['claudeAiOauth'].get('accessToken'))
        if 'refresh_token' in new_tokens:
            creds['claudeAiOauth']['refreshToken'] = new_tokens['refresh_token']
        if 'expires_in' in new_tokens:
            import time
            creds['claudeAiOauth']['expiresAt'] = int(time.time() * 1000) + (new_tokens['expires_in'] * 1000)
    
    with open('/root/.claude/.credentials.json', 'w') as f:
        json.dump(creds, f)
    
    print('Credentials updated successfully')
except Exception as e:
    print(f'Error updating credentials: {e}', file=sys.stderr)
    sys.exit(1)
"
        return 0
    else
        echo -e "${RED}[ERROR]${NC} Token refresh failed"
        echo -e "${RED}[ERROR]${NC} Response: $RESPONSE"
        return 1
    fi
}

# Check token expiry and refresh if needed
check_and_refresh_token() {
    if [ ! -f "/root/.claude/.credentials.json" ]; then
        return 0
    fi
    
    echo -e "${YELLOW}[TOKEN]${NC} Checking OAuth token expiry..."
    
    # Check if token is expired using Python
    EXPIRED=$(python3 -c "
import json
import time
import sys

try:
    with open('/root/.claude/.credentials.json') as f:
        data = json.load(f)
    
    oauth = data.get('claudeAiOauth', {})
    expires_at = oauth.get('expiresAt', 0)
    
    # Current time in milliseconds
    now = int(time.time() * 1000)
    
    # Add 5 minute buffer
    buffer = 5 * 60 * 1000
    
    if expires_at > 0 and (expires_at - buffer) < now:
        print('true')
    else:
        print('false')
        remaining = (expires_at - now) / 1000 / 60
        print(f'Token valid for {remaining:.0f} more minutes', file=sys.stderr)
except Exception as e:
    print('false')
    print(f'Error checking token: {e}', file=sys.stderr)
" 2>&1)
    
    if echo "$EXPIRED" | head -1 | grep -q "true"; then
        echo -e "${YELLOW}[TOKEN]${NC} Token expired or expiring soon, refreshing..."
        refresh_oauth_token
    else
        REMAINING=$(echo "$EXPIRED" | tail -1)
        echo -e "${GREEN}[TOKEN]${NC} $REMAINING"
    fi
}

# Run token check and refresh
check_and_refresh_token

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
