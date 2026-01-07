#!/usr/bin/env python3
"""
Test MCP Server - Agent erişim testi için
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# MCP SDK
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not found. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Log dosyası
LOG_FILE = Path(__file__).parent / "test-log.txt"

server = Server("test-mcp")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="write_test_log",
            description="Test log dosyasına mesaj yazar",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Log'a yazılacak mesaj"
                    },
                    "agent_name": {
                        "type": "string",
                        "description": "Çağıran agent'ın adı"
                    }
                },
                "required": ["message", "agent_name"]
            }
        ),
        Tool(
            name="read_test_log",
            description="Test log dosyasını okur",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "write_test_log":
        message = arguments.get("message", "No message")
        agent_name = arguments.get("agent_name", "Unknown")
        timestamp = datetime.now().isoformat()

        log_entry = f"[{timestamp}] Agent: {agent_name} | Message: {message}\n"

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)

        return [TextContent(
            type="text",
            text=f"✅ Log yazıldı: {LOG_FILE}\nEntry: {log_entry}"
        )]

    elif name == "read_test_log":
        if LOG_FILE.exists():
            content = LOG_FILE.read_text(encoding="utf-8")
            return [TextContent(
                type="text",
                text=f"📄 Log içeriği:\n{content}"
            )]
        else:
            return [TextContent(
                type="text",
                text="⚠️ Log dosyası henüz oluşturulmamış"
            )]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
