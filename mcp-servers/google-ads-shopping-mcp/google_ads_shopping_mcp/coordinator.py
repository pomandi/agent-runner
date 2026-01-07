"""Module declaring the singleton MCP instance.

The singleton allows other modules to register their tools with the same MCP
server using @mcp.tool annotations, thereby 'coordinating' the bootstrapping
of the server.
"""
import sys
import json
from mcp.server.fastmcp import FastMCP

# Creates the singleton.
mcp = FastMCP("Google Ads Shopping Server")

# Send ready signal to stdout for Claude CLI health check
def send_ready_signal():
    """Send ready signal to stdout for MCP health check."""
    ready_message = {"jsonrpc": "2.0", "method": "ready"}
    print(json.dumps(ready_message), flush=True)

# Call ready signal when module is imported
send_ready_signal()
