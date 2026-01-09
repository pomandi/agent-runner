#!/usr/bin/env python3
"""
Telegram Bot MCP Server
========================
Send notifications and handle interactive buttons for email assistant.

Environment Variables:
- TELEGRAM_BOT_TOKEN: Bot token from @BotFather
- TELEGRAM_CHAT_ID: Your user chat ID

Tools:
- send_message: Send simple text message
- send_notification: Send notification with action buttons
- send_approval_request: Send approval/rejection request
- get_updates: Poll for button clicks/callbacks
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import httpx
import os
import json
import asyncio

SERVER_NAME = "telegram-bot"
server = Server(SERVER_NAME)

# Tool definitions
TOOLS = [
    Tool(
        name="send_message",
        description="Send simple text message to user",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Message text (supports Markdown)"
                },
                "parse_mode": {
                    "type": "string",
                    "default": "Markdown",
                    "enum": ["Markdown", "HTML"],
                    "description": "Text formatting mode"
                }
            },
            "required": ["text"]
        }
    ),
    Tool(
        name="send_notification",
        description="Send notification with action buttons",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Notification title"
                },
                "items": {
                    "type": "array",
                    "description": "List of items with action buttons",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "buttons": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "callback_data": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "required": ["title", "items"]
        }
    ),
    Tool(
        name="send_approval_request",
        description="Send approval/rejection request with buttons",
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to approve/reject"
                },
                "context_id": {
                    "type": "string",
                    "description": "Context ID for tracking approval"
                },
                "approve_text": {
                    "type": "string",
                    "default": "✅ Approve",
                    "description": "Approve button text"
                },
                "reject_text": {
                    "type": "string",
                    "default": "❌ Reject",
                    "description": "Reject button text"
                }
            },
            "required": ["message", "context_id"]
        }
    ),
    Tool(
        name="get_updates",
        description="Get pending button clicks/callbacks",
        inputSchema={
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "description": "Long polling timeout in seconds"
                }
            }
        }
    )
]


async def send_telegram_api(method: str, payload: dict):
    """Call Telegram Bot API."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

    url = f"https://api.telegram.org/bot{token}/{method}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            if not result.get("ok"):
                raise Exception(f"Telegram API error: {result.get('description', 'Unknown error')}")

            return result
        except httpx.HTTPError as e:
            raise Exception(f"HTTP error calling Telegram API: {str(e)}")


async def handle_send_message(text: str, parse_mode: str = "Markdown"):
    """Send simple text message."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID environment variable not set")

    result = await send_telegram_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    })

    return {
        "success": True,
        "message_id": result["result"]["message_id"],
        "chat_id": result["result"]["chat"]["id"]
    }


async def handle_send_notification(title: str, items: list):
    """Send notification with inline buttons."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID environment variable not set")

    # Build message text
    message = f"*{title}*\n\n"

    # Build inline keyboard
    keyboard = []
    for i, item in enumerate(items, 1):
        message += f"{i}. {item['text']}\n"

        # Add buttons for this item
        if "buttons" in item and item["buttons"]:
            row = []
            for btn in item["buttons"]:
                row.append({
                    "text": btn["text"],
                    "callback_data": btn["callback_data"]
                })
            keyboard.append(row)

    result = await send_telegram_api("sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": keyboard}
    })

    return {
        "success": True,
        "message_id": result["result"]["message_id"],
        "chat_id": result["result"]["chat"]["id"],
        "items_count": len(items)
    }


async def handle_send_approval_request(
    message: str,
    context_id: str,
    approve_text: str = "✅ Approve",
    reject_text: str = "❌ Reject"
):
    """Send approval request with approve/reject buttons."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID environment variable not set")

    keyboard = [[
        {"text": approve_text, "callback_data": f"approve:{context_id}"},
        {"text": reject_text, "callback_data": f"reject:{context_id}"}
    ]]

    result = await send_telegram_api("sendMessage", {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": keyboard}
    })

    return {
        "success": True,
        "message_id": result["result"]["message_id"],
        "chat_id": result["result"]["chat"]["id"],
        "context_id": context_id
    }


async def handle_get_updates(timeout: int = 30):
    """Poll for button clicks (long polling)."""
    result = await send_telegram_api("getUpdates", {
        "timeout": timeout,
        "allowed_updates": ["callback_query"]
    })

    updates = []
    for update in result.get("result", []):
        if "callback_query" in update:
            callback = update["callback_query"]
            updates.append({
                "update_id": update["update_id"],
                "callback_data": callback["data"],
                "message_id": callback["message"]["message_id"],
                "from_user": {
                    "id": callback["from"]["id"],
                    "first_name": callback["from"].get("first_name", ""),
                    "username": callback["from"].get("username", "")
                }
            })

    return {
        "updates": updates,
        "count": len(updates)
    }


# MCP handlers
TOOL_HANDLERS = {
    "send_message": handle_send_message,
    "send_notification": handle_send_notification,
    "send_approval_request": handle_send_approval_request,
    "get_updates": handle_get_updates
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    if name not in TOOL_HANDLERS:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"}, indent=2)
        )]

    try:
        result = await TOOL_HANDLERS[name](**arguments)
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": str(e),
                "tool": name,
                "arguments": arguments
            }, indent=2)
        )]


async def main():
    """Run MCP server."""
    # Validate environment variables
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable not set", flush=True)
        print("Get your token from @BotFather on Telegram", flush=True)
        return

    if not chat_id:
        print("ERROR: TELEGRAM_CHAT_ID environment variable not set", flush=True)
        print("Use @userinfobot on Telegram to get your chat ID", flush=True)
        return

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
