# Agent Runner Container v2.0 - SDK-Only Architecture
#
# Key features:
# - Uses Claude Agent SDK (not CLI subprocess)
# - Config-driven agents (agents.yaml)
# - Scalable: add agents via YAML, no code changes
# - Uses ~/.claude/.credentials.json for auth (Claude Max subscription)
# - Runs as non-root user (required for Claude Code CLI)

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
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for Claude Code (required - CLI refuses to run with root+skip-permissions)
RUN groupadd -r agent && useradd -r -g agent -d /home/agent -s /bin/bash -m agent

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Install claude-code-logger for real-time visibility
RUN npm install -g claude-code-logger

# Create directories with proper ownership
WORKDIR /app
RUN mkdir -p /app/logs /app/agents /app/mcp-servers /app/data/visual-content /home/agent/.claude \
    && chown -R agent:agent /app /home/agent

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip3 install --break-system-packages -r /app/requirements.txt

# Copy MCP servers
COPY --chown=agent:agent mcp-servers/ /app/mcp-servers/

# Copy agents from repo (built into container)
COPY --chown=agent:agent agents/ /app/agents/

# Copy MCP config for Claude
COPY --chown=agent:agent .mcp.json /app/.mcp.json

# Copy scripts and API
COPY entrypoint.sh /entrypoint.sh
COPY --chown=agent:agent schedule.sh /app/schedule.sh
COPY --chown=agent:agent run-agent.sh /app/run-agent.sh
COPY --chown=agent:agent refresh-token.sh /app/refresh-token.sh
RUN chmod +x /entrypoint.sh /app/schedule.sh /app/run-agent.sh /app/refresh-token.sh

# Copy SDK-based API (v2 architecture)
COPY --chown=agent:agent config/ /app/config/
COPY --chown=agent:agent agent_registry.py /app/agent_registry.py
COPY --chown=agent:agent sdk_executor.py /app/sdk_executor.py
COPY --chown=agent:agent api.py /app/api.py

# Environment variables
ENV AGENT_NAME=feed-publisher
ENV AGENT_TASK="Run the agent task"
ENV LOG_LEVEL=verbose
ENV AGENT_SCHEDULE=""
ENV HOME=/home/agent
ENV USER=agent

# Expose ports: 8000 for logger, 8080 for API
EXPOSE 8000 8080

# Health check via API
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
