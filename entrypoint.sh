#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Claude home directory (non-root user required for Claude Code CLI)
CLAUDE_HOME="/home/agent/.claude"

echo -e "${BLUE}=========================================="
echo -e "       AGENT RUNNER CONTAINER"
echo -e "==========================================${NC}"
echo -e "${GREEN}Agent:${NC} $AGENT_NAME"
echo -e "${GREEN}Task:${NC} $AGENT_TASK"
echo -e "${GREEN}Schedule:${NC} ${AGENT_SCHEDULE:-None (manual/API only)}"
echo -e "${GREEN}API:${NC} http://localhost:8080"
echo -e "${GREEN}User:${NC} agent (non-root for Claude Code CLI)"
echo -e "${GREEN}Time:${NC} $(date)"
echo -e "${BLUE}==========================================${NC}"

# Auto-create Claude credentials from environment variable (base64 encoded)
if [ -n "$CLAUDE_CREDENTIALS_B64" ]; then
    echo -e "${GREEN}[OK]${NC} Creating credentials from CLAUDE_CREDENTIALS_B64 env var"
    mkdir -p $CLAUDE_HOME
    echo "$CLAUDE_CREDENTIALS_B64" | base64 -d > $CLAUDE_HOME/.credentials.json
    chown -R agent:agent $CLAUDE_HOME
    chmod 600 $CLAUDE_HOME/.credentials.json
    echo -e "${GREEN}[OK]${NC} Claude credentials created successfully"
elif [ -n "$CLAUDE_CREDENTIALS" ]; then
    echo -e "${GREEN}[OK]${NC} Creating credentials from CLAUDE_CREDENTIALS env var"
    mkdir -p $CLAUDE_HOME
    echo "$CLAUDE_CREDENTIALS" > $CLAUDE_HOME/.credentials.json
    chown -R agent:agent $CLAUDE_HOME
    chmod 600 $CLAUDE_HOME/.credentials.json
    echo -e "${GREEN}[OK]${NC} Claude credentials created successfully"
elif [ -f "$CLAUDE_HOME/.credentials.json" ]; then
    echo -e "${GREEN}[OK]${NC} Claude credentials found (mounted)"
else
    echo -e "${YELLOW}[WARN]${NC} Claude credentials not found"
    echo -e "${YELLOW}[WARN]${NC} Set CLAUDE_CREDENTIALS_B64 env var with base64 encoded JSON"
fi

# Create settings.json with bypassPermissions mode (required for SDK execution)
mkdir -p $CLAUDE_HOME
cat > $CLAUDE_HOME/settings.json << 'SETTINGS_EOF'
{
  "permissions": {
    "allow": ["*"],
    "deny": [],
    "ask": [],
    "defaultMode": "bypassPermissions"
  },
  "sandbox": {
    "autoAllowBashIfSandboxed": true
  }
}
SETTINGS_EOF
chown -R agent:agent $CLAUDE_HOME
chmod 600 $CLAUDE_HOME/settings.json
echo -e "${GREEN}[OK]${NC} Claude settings.json created (bypassPermissions mode)"

# Claude Code OAuth client_id (official)
# Source: https://github.com/RavenStorm-bit/claude-token-refresh
CLAUDE_CLIENT_ID="9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Token refresh function
refresh_oauth_token() {
    echo -e "${YELLOW}[TOKEN]${NC} Attempting to refresh OAuth token..."

    # Read current credentials
    if [ ! -f "$CLAUDE_HOME/.credentials.json" ]; then
        echo -e "${RED}[ERROR]${NC} No credentials file found"
        return 1
    fi

    # Extract refresh token using Python (more reliable than jq for nested JSON)
    REFRESH_TOKEN=$(python3 -c "
import json
import sys
try:
    with open('$CLAUDE_HOME/.credentials.json') as f:
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

    with open('$CLAUDE_HOME/.credentials.json') as f:
        creds = json.load(f)

    # Update OAuth tokens
    if 'claudeAiOauth' in creds:
        creds['claudeAiOauth']['accessToken'] = new_tokens.get('access_token', creds['claudeAiOauth'].get('accessToken'))
        if 'refresh_token' in new_tokens:
            creds['claudeAiOauth']['refreshToken'] = new_tokens['refresh_token']
        if 'expires_in' in new_tokens:
            import time
            creds['claudeAiOauth']['expiresAt'] = int(time.time() * 1000) + (new_tokens['expires_in'] * 1000)

    with open('$CLAUDE_HOME/.credentials.json', 'w') as f:
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
    if [ ! -f "$CLAUDE_HOME/.credentials.json" ]; then
        return 0
    fi

    echo -e "${YELLOW}[TOKEN]${NC} Checking OAuth token expiry..."

    # Check if token is expired using Python
    EXPIRED=$(python3 -c "
import json
import time
import sys

try:
    with open('$CLAUDE_HOME/.credentials.json') as f:
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

# Copy MCP config to agent home
if [ -f "/app/.mcp.json" ]; then
    cp /app/.mcp.json $CLAUDE_HOME/.mcp.json
    chown agent:agent $CLAUDE_HOME/.mcp.json
    echo -e "${GREEN}[OK]${NC} MCP config copied"
fi

# Save environment variables for cron jobs
mkdir -p /app/data
cat > /app/data/agent-env.sh << ENV_EOF
# Environment variables for scheduled agent runs
export AGENT_NAME="${AGENT_NAME}"
export AGENT_TASK="${AGENT_TASK}"
export AGENT_SCHEDULE="${AGENT_SCHEDULE}"
export META_ACCESS_TOKEN="${META_ACCESS_TOKEN}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}"
export AWS_S3_BUCKET="${AWS_S3_BUCKET}"
export R2_ENDPOINT="${R2_ENDPOINT}"
export AGENT_OUTPUTS_DB_URL="${AGENT_OUTPUTS_DB_URL}"
export PATH="/usr/local/bin:/usr/bin:/bin:\$PATH"
export HOME="/home/agent"
ENV_EOF
chmod 600 /app/data/agent-env.sh
echo -e "${GREEN}[OK]${NC} Environment variables saved for cron"

# Setup cron schedules
echo -e "${YELLOW}[CRON]${NC} Setting up cron schedules..."
crontab -r 2>/dev/null || true

# Always add token refresh cron (every 1 hour for safety)
CRON_LINES="0 * * * * /app/refresh-token.sh >> /app/logs/token-refresh.log 2>&1\n"
echo -e "${GREEN}[OK]${NC} Token refresh scheduled: every 1 hour"

# Add agent schedule if provided
if [ -n "$AGENT_SCHEDULE" ]; then
    if [[ "$AGENT_SCHEDULE" == *"*"* ]]; then
        CRON_LINES="$CRON_LINES$AGENT_SCHEDULE /app/schedule.sh >> /app/logs/cron.log 2>&1\n"
        echo -e "${GREEN}[OK]${NC} Agent scheduled: $AGENT_SCHEDULE"
    else
        IFS=',' read -ra TIMES <<< "$AGENT_SCHEDULE"
        for TIME in "${TIMES[@]}"; do
            HOUR=$(echo $TIME | cut -d: -f1)
            MINUTE=$(echo $TIME | cut -d: -f2)
            CRON_LINES="$CRON_LINES$MINUTE $HOUR * * * /app/schedule.sh >> /app/logs/cron.log 2>&1\n"
            echo -e "${GREEN}[OK]${NC} Agent scheduled at $TIME"
        done
    fi
fi

echo -e "$CRON_LINES" | crontab -
service cron start
echo -e "${GREEN}[OK]${NC} Cron daemon started"

echo -e "${BLUE}==========================================${NC}"
echo -e "${GREEN}[API]${NC} Starting API server on port 8080 as user 'agent'..."
echo -e "${BLUE}==========================================${NC}"

# Ensure /app is writable by agent
chown -R agent:agent /app/logs /app/data

# Start API server as non-root user (required for Claude Code CLI)
exec gosu agent python3 /app/api.py
