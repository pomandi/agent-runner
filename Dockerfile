# Agent Runner Container - Full Visibility + Scheduling + API
# Runs Claude CLI agents with MCP support, cron scheduling, and HTTP API

FROM node:20-slim

# Install system dependencies including cron, ffmpeg, and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-venv \
    procps \
    cron \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Install claude-code-logger for real-time visibility
RUN npm install -g claude-code-logger

# Create directories
WORKDIR /app
RUN mkdir -p /app/logs /app/agents /app/mcp-servers /app/data/visual-content /root/.claude

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip3 install --break-system-packages -r /app/requirements.txt

# Copy MCP servers
COPY mcp-servers/ /app/mcp-servers/

# Copy agents from repo (built into container)
COPY agents/ /app/agents/

# Copy MCP config for Claude
COPY .mcp.json /app/.mcp.json

# Copy scripts and API
COPY entrypoint.sh /entrypoint.sh
COPY schedule.sh /app/schedule.sh
COPY run-agent.sh /app/run-agent.sh
COPY api.py /app/api.py
RUN chmod +x /entrypoint.sh /app/schedule.sh /app/run-agent.sh

# Environment variables
ENV AGENT_NAME=feed-publisher
ENV AGENT_TASK="Run the agent task"
ENV LOG_LEVEL=verbose
ENV AGENT_SCHEDULE=""

# Expose ports: 8000 for logger, 8080 for API
EXPOSE 8000 8080

# Health check via API
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
