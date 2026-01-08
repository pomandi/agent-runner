# Claude Agent SDK Runner Container
#
# Pure Python SDK implementation:
# - agents.py: Python agent definitions (no .md files)
# - sdk_runner.py: SDK execution with query() or ClaudeSDKClient
# - hooks.py: Pre/Post tool hooks
# - tools/: Custom Python tools with @tool decorator
# - dashboard/: Animated actor monitoring dashboard (React)
#
# Usage:
#   docker run -e CLAUDE_CODE_OAUTH_TOKEN=xxx -e AGENT_NAME=feed-publisher agent-runner

# Stage 1: Build dashboard
FROM node:20-alpine AS dashboard-builder
WORKDIR /dashboard
COPY dashboard/package.json dashboard/vite.config.js ./
RUN npm install
COPY dashboard/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r agent && useradd -r -g agent -d /home/agent -s /bin/bash -m agent

# Create directories
WORKDIR /app
RUN mkdir -p /app/logs /app/tools /app/mcp-servers /home/agent/.claude \
    && chown -R agent:agent /app /home/agent

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application files (pure Python SDK)
COPY --chown=agent:agent agents.py /app/agents.py
COPY --chown=agent:agent sdk_runner.py /app/sdk_runner.py
COPY --chown=agent:agent api.py /app/api.py
COPY --chown=agent:agent hooks.py /app/hooks.py
COPY --chown=agent:agent monitoring.py /app/monitoring.py
COPY --chown=agent:agent entrypoint.sh /app/entrypoint.sh
COPY --chown=agent:agent tools/ /app/tools/

# Copy Temporal application
COPY --chown=agent:agent temporal_app/ /app/temporal_app/

# Copy Memory layer (Qdrant, Redis, embeddings)
COPY --chown=agent:agent memory/ /app/memory/

# Copy LangGraph agents
COPY --chown=agent:agent langgraph_agents/ /app/langgraph_agents/

# Copy MCP servers if they exist
COPY --chown=agent:agent mcp-servers/ /app/mcp-servers/

# Copy actor status module
COPY --chown=agent:agent actor_status.py /app/actor_status.py

# Copy built dashboard from builder stage
COPY --from=dashboard-builder --chown=agent:agent /dashboard/dist /app/dashboard/dist

# Make scripts executable
RUN chmod +x /app/entrypoint.sh /app/sdk_runner.py && \
    find /app/mcp-servers -name "server.py" -exec chmod +x {} \;

# Switch to non-root user
USER agent

# Environment variables
ENV RUN_MODE=api
ENV API_PORT=8080
ENV AGENT_NAME=feed-publisher
ENV AGENT_TASK="Run the default agent task"
ENV LOG_LEVEL=INFO
ENV KEEP_ALIVE=false
ENV HOME=/home/agent
ENV PYTHONPATH=/app

WORKDIR /app

# Healthcheck (checks API server or SDK)
HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || python3 -c "import claude_agent_sdk; print('OK')" || exit 1

# Expose API port
EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
