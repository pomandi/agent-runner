# Agent Runner Container - Full Visibility + Scheduling
# Runs Claude CLI agents with complete logging, MCP support, and cron scheduling

FROM node:20-slim

# Install system dependencies including cron
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-venv \
    procps \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Install claude-code-logger for real-time visibility
RUN npm install -g claude-code-logger

# Create directories
WORKDIR /app
RUN mkdir -p /app/logs /app/agents /app/mcp-servers /root/.claude

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip3 install --break-system-packages -r /app/requirements.txt

# Copy MCP servers
COPY mcp-servers/ /app/mcp-servers/

# Copy agents from repo (built into container)
COPY agents/ /app/agents/

# Copy MCP config for Claude
COPY .mcp.json /app/.mcp.json

# Copy scripts
COPY entrypoint.sh /entrypoint.sh
COPY schedule.sh /app/schedule.sh
COPY run-agent.sh /app/run-agent.sh
RUN chmod +x /entrypoint.sh /app/schedule.sh /app/run-agent.sh

# Environment variables
ENV AGENT_NAME=feed-publisher
ENV AGENT_TASK="Run the agent task"
ENV LOG_LEVEL=verbose
# Schedule format: "HH:MM,HH:MM" or cron format
# Examples: "09:00,18:00" for 9am and 6pm
#           "*/30 * * * *" for every 30 minutes (cron format)
ENV AGENT_SCHEDULE=""

# Expose port for claude-code-logger proxy
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "cron\|node" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
