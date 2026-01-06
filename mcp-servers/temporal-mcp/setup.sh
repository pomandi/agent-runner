#!/bin/bash
# Setup script for Temporal MCP Server

set -e

echo "================================================"
echo "Temporal MCP Server - Setup"
echo "================================================"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "================================================"
echo "MCP Configuration"
echo "================================================"
echo ""
echo "Add this to your Claude Code MCP settings:"
echo ""
echo '{'
echo '  "mcpServers": {'
echo '    "temporal": {'
echo '      "command": "python3",'
echo "      \"args\": [\"$SCRIPT_DIR/server.py\"],"
echo '      "env": {'
echo '        "TEMPORAL_HOST": "46.224.117.155:7233",'
echo '        "TEMPORAL_NAMESPACE": "default",'
echo '        "TEMPORAL_TASK_QUEUE": "agent-tasks"'
echo '      }'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "================================================"
echo "Quick Test"
echo "================================================"
echo ""
echo "After adding to MCP config, restart Claude Code and try:"
echo ""
echo "  mcp__temporal__list_schedules"
echo "  mcp__temporal__list_workflows"
echo ""
echo "================================================"
