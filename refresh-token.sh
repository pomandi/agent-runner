#!/bin/bash
# Auto Token Refresh Script for Claude OAuth
# Runs via cron every 6 hours to keep tokens fresh
# ALSO updates Coolify env var to persist across container restarts

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

LOG_PREFIX="[TOKEN-REFRESH $(date '+%Y-%m-%d %H:%M:%S')]"

# Claude Code OAuth client_id (official)
CLAUDE_CLIENT_ID="9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CREDENTIALS_FILE="/root/.claude/.credentials.json"

# Coolify API configuration (for persisting refreshed tokens)
COOLIFY_API_URL="${COOLIFY_API_URL:-https://coolify.faric.cloud/api/v1}"
COOLIFY_API_TOKEN="${COOLIFY_API_TOKEN:-}"
COOLIFY_APP_UUID="${COOLIFY_APP_UUID:-pss0wkokscwckssws8g4gow8}"

log_info() {
    echo -e "${GREEN}${LOG_PREFIX}${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}${LOG_PREFIX}${NC} $1"
}

log_error() {
    echo -e "${RED}${LOG_PREFIX}${NC} $1"
}

# Function to update Coolify env var with new credentials
update_coolify_env() {
    if [ -z "$COOLIFY_API_TOKEN" ]; then
        log_warn "COOLIFY_API_TOKEN not set, skipping Coolify env update"
        log_warn "Token will be lost on container restart!"
        return 1
    fi

    log_info "Updating Coolify CLAUDE_CREDENTIALS_B64 env var..."

    # Read credentials and base64 encode
    NEW_CREDS_B64=$(cat "$CREDENTIALS_FILE" | base64 -w 0)

    # Update via Coolify API (bulk update endpoint)
    RESPONSE=$(curl -s -X PATCH "${COOLIFY_API_URL}/applications/${COOLIFY_APP_UUID}/envs/bulk" \
        -H "Authorization: Bearer ${COOLIFY_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "[{\"key\": \"CLAUDE_CREDENTIALS_B64\", \"value\": \"${NEW_CREDS_B64}\"}]" 2>/dev/null)

    if echo "$RESPONSE" | grep -q "CLAUDE_CREDENTIALS_B64"; then
        log_info "Coolify env var updated successfully - token will persist across restarts"
        return 0
    else
        log_error "Failed to update Coolify env var"
        log_error "Response: $RESPONSE"
        return 1
    fi
}

# Check if credentials file exists
if [ ! -f "$CREDENTIALS_FILE" ]; then
    log_error "Credentials file not found: $CREDENTIALS_FILE"
    exit 1
fi

# Get token info using Python
TOKEN_INFO=$(python3 -c "
import json
import time
import sys

try:
    with open('$CREDENTIALS_FILE') as f:
        data = json.load(f)

    oauth = data.get('claudeAiOauth', {})
    expires_at = oauth.get('expiresAt', 0)
    refresh_token = oauth.get('refreshToken', '')

    now = int(time.time() * 1000)
    remaining_ms = expires_at - now
    remaining_hours = remaining_ms / 1000 / 60 / 60

    # Refresh if less than 2 hours remaining (buffer for 6-hour cron)
    needs_refresh = remaining_hours < 2

    print(f'{remaining_hours:.1f}')
    print('true' if needs_refresh else 'false')
    print(refresh_token)
except Exception as e:
    print('0')
    print('true')
    print('')
    sys.exit(1)
" 2>/dev/null)

REMAINING_HOURS=$(echo "$TOKEN_INFO" | sed -n '1p')
NEEDS_REFRESH=$(echo "$TOKEN_INFO" | sed -n '2p')
REFRESH_TOKEN=$(echo "$TOKEN_INFO" | sed -n '3p')

log_info "Token remaining: ${REMAINING_HOURS} hours"

if [ "$NEEDS_REFRESH" != "true" ]; then
    log_info "Token still valid, no refresh needed"
    exit 0
fi

if [ -z "$REFRESH_TOKEN" ]; then
    log_error "No refresh token found in credentials"
    exit 1
fi

log_warn "Token needs refresh, calling Anthropic API..."

# Call Anthropic OAuth refresh endpoint
RESPONSE=$(curl -s -X POST "https://console.anthropic.com/v1/oauth/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=refresh_token" \
    -d "refresh_token=$REFRESH_TOKEN" \
    -d "client_id=$CLAUDE_CLIENT_ID" 2>/dev/null)

# Check if response contains access_token
if echo "$RESPONSE" | grep -q "access_token"; then
    # Update credentials file with new tokens
    python3 -c "
import json
import time
import sys

response = '''$RESPONSE'''
try:
    new_tokens = json.loads(response)

    with open('$CREDENTIALS_FILE') as f:
        creds = json.load(f)

    if 'claudeAiOauth' in creds:
        creds['claudeAiOauth']['accessToken'] = new_tokens.get('access_token')
        if 'refresh_token' in new_tokens:
            creds['claudeAiOauth']['refreshToken'] = new_tokens['refresh_token']
        if 'expires_in' in new_tokens:
            creds['claudeAiOauth']['expiresAt'] = int(time.time() * 1000) + (new_tokens['expires_in'] * 1000)

    with open('$CREDENTIALS_FILE', 'w') as f:
        json.dump(creds, f)

    # Calculate new expiry
    new_expires = creds['claudeAiOauth']['expiresAt']
    new_remaining = (new_expires - int(time.time() * 1000)) / 1000 / 60 / 60
    print(f'{new_remaining:.1f}')
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
"

    if [ $? -eq 0 ]; then
        NEW_HOURS=$(python3 -c "
import json, time
with open('$CREDENTIALS_FILE') as f:
    d = json.load(f)
expires = d.get('claudeAiOauth', {}).get('expiresAt', 0)
print(f'{(expires - time.time()*1000)/1000/60/60:.1f}')
" 2>/dev/null)
        log_info "Token refresh successful! New token valid for ${NEW_HOURS} hours"

        # CRITICAL: Also update Coolify env var to persist across container restarts
        update_coolify_env

        exit 0
    else
        log_error "Failed to update credentials file"
        exit 1
    fi
else
    log_error "Token refresh failed"
    log_error "Response: $RESPONSE"
    exit 1
fi
