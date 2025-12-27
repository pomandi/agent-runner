# Agent Runner Container - Full Visibility
# Runs Claude CLI agents with complete logging and MCP support

FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-venv \
    procps \
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

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment variables (can be overridden)
ENV AGENT_NAME=feed-publisher
ENV AGENT_TASK="Run the agent task"
ENV LOG_LEVEL=verbose

# Expose port for claude-code-logger proxy
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "node" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
