# Agent Runner Container - Full Visibility
# Runs Claude CLI agents with complete logging

FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Install claude-code-logger for real-time visibility
RUN npm install -g claude-code-logger

# Create directories
WORKDIR /app
RUN mkdir -p /app/logs /app/agents /root/.claude

# Copy agents from repo (built into container)
COPY agents/ /app/agents/

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
