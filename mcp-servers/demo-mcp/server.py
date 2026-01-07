#!/usr/bin/env python3
"""
demo-mcp MCP Server
Agent: demo-collector
Category: collector
Generated: 2025-12-26T15:12:00

Demo agent to test agent+MCP auto-creation

NOTE: All outputs go to PostgreSQL via agent-outputs MCP.
No local file storage - use mcp__agent-outputs__save_output() for all results.
"""
import asyncio
import json
import logging
from datetime import datetime
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo-mcp")

server = Server("demo-mcp")


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
        Tool(
            name="collect_data",
            description="Collect data from the source",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_status",
            description="Get collection status",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")

    if name == "collect_data":
        # TODO: Implement collect_data
        result = {
            "status": "success",
            "tool": "collect_data",
            "timestamp": datetime.now().isoformat(),
            "data": {}
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "get_status":
        # TODO: Implement get_status
        result = {
            "status": "success",
            "tool": "get_status",
            "timestamp": datetime.now().isoformat(),
            "data": {}
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
