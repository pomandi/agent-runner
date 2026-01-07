#!/usr/bin/env python3
"""
WhatsApp Business MCP Server
=============================
MCP Server for sending messages via WhatsApp Business Cloud API.

Provides tools for:
- Sending text messages to WhatsApp numbers
- Sending template messages (for 24h+ conversations)
- Checking message delivery status
- Listing available message templates

Environment Variables Required:
- WHATSAPP_PHONE_NUMBER_ID: Your WhatsApp Business Phone Number ID
- WHATSAPP_ACCESS_TOKEN: Permanent access token from Meta Business
- WHATSAPP_BUSINESS_ACCOUNT_ID: Your WhatsApp Business Account ID (optional)

Version: 1.0.0
API Version: Meta Graph API v21.0
"""

import asyncio
import json
import os
from typing import Any, Optional
from datetime import datetime
from pathlib import Path

import httpx

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Server info
SERVER_NAME = "whatsapp-business"
SERVER_VERSION = "1.0.0"
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Initialize MCP server
server = Server(SERVER_NAME)

# Global credentials
_credentials: Optional[dict] = None


def load_credentials() -> dict:
    """Load credentials from .env file"""
    global _credentials
    if _credentials is not None:
        return _credentials

    env_file = Path.home() / '.claude' / '.env'
    credentials = {}

    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    credentials[key] = value.strip('"').strip("'")

    _credentials = credentials
    return credentials


def get_whatsapp_credentials() -> dict:
    """Get WhatsApp API credentials"""
    creds = load_credentials()

    return {
        "phone_number_id": creds.get("WHATSAPP_PHONE_NUMBER_ID"),
        "access_token": creds.get("WHATSAPP_ACCESS_TOKEN"),
        "business_account_id": creds.get("WHATSAPP_BUSINESS_ACCOUNT_ID")
    }


def format_phone_number(phone: str) -> str:
    """Format phone number for WhatsApp API (remove + and spaces)"""
    return phone.replace("+", "").replace(" ", "").replace("-", "")


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="send_message",
        description="Send a text message to a WhatsApp number. Use this for immediate notifications and alerts. The recipient must have messaged your business first (within 24h) or use send_template_message instead.",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient phone number in international format (e.g., '+32471234567' or '32471234567')"
                },
                "message": {
                    "type": "string",
                    "description": "Text message to send (max 4096 characters)"
                },
                "preview_url": {
                    "type": "boolean",
                    "description": "Whether to show URL previews in the message. Default: true"
                }
            },
            "required": ["to", "message"]
        }
    ),
    Tool(
        name="send_template_message",
        description="Send a pre-approved template message. Required for initiating conversations or messaging after 24h window. Templates must be approved by Meta first.",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient phone number in international format"
                },
                "template_name": {
                    "type": "string",
                    "description": "Name of the approved message template"
                },
                "language_code": {
                    "type": "string",
                    "description": "Template language code (e.g., 'tr', 'en', 'nl'). Default: 'tr'"
                },
                "body_parameters": {
                    "type": "array",
                    "description": "List of parameter values for template body placeholders ({{1}}, {{2}}, etc.)",
                    "items": {"type": "string"}
                },
                "header_parameters": {
                    "type": "array",
                    "description": "Optional: List of parameter values for template header",
                    "items": {"type": "string"}
                }
            },
            "required": ["to", "template_name"]
        }
    ),
    Tool(
        name="send_document",
        description="Send a document (PDF, DOC, etc.) to a WhatsApp number.",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient phone number in international format"
                },
                "document_url": {
                    "type": "string",
                    "description": "Public URL of the document to send"
                },
                "filename": {
                    "type": "string",
                    "description": "Filename to display (e.g., 'report.pdf')"
                },
                "caption": {
                    "type": "string",
                    "description": "Optional caption for the document"
                }
            },
            "required": ["to", "document_url", "filename"]
        }
    ),
    Tool(
        name="send_image",
        description="Send an image to a WhatsApp number.",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient phone number in international format"
                },
                "image_url": {
                    "type": "string",
                    "description": "Public URL of the image to send"
                },
                "caption": {
                    "type": "string",
                    "description": "Optional caption for the image"
                }
            },
            "required": ["to", "image_url"]
        }
    ),
    Tool(
        name="get_message_status",
        description="Get the delivery status of a sent message using its message ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The WhatsApp message ID (wamid) returned when sending a message"
                }
            },
            "required": ["message_id"]
        }
    ),
    Tool(
        name="get_templates",
        description="List all available message templates for your WhatsApp Business account.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of templates to return. Default: 50"
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: APPROVED, PENDING, REJECTED. Default: all",
                    "enum": ["APPROVED", "PENDING", "REJECTED"]
                }
            }
        }
    ),
    Tool(
        name="get_phone_number_info",
        description="Get information about the WhatsApp Business phone number including quality rating and status.",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    )
]


# ============================================================================
# Tool Handlers
# ============================================================================

async def handle_send_message(
    to: str,
    message: str,
    preview_url: bool = True
) -> dict:
    """Send a text message via WhatsApp"""
    creds = get_whatsapp_credentials()
    phone_number_id = creds["phone_number_id"]
    access_token = creds["access_token"]

    if not phone_number_id or not access_token:
        return {
            "success": False,
            "error": "Missing WhatsApp credentials. Set WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN in .env"
        }

    # Format phone number
    to_formatted = format_phone_number(to)

    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_formatted,
        "type": "text",
        "text": {
            "preview_url": preview_url,
            "body": message[:4096]  # WhatsApp limit
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        result = response.json()

        if "messages" in result:
            message_id = result["messages"][0]["id"]
            return {
                "success": True,
                "message_id": message_id,
                "to": to_formatted,
                "message_preview": message[:100] + "..." if len(message) > 100 else message,
                "sent_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": result.get("error", {}).get("message", str(result)),
                "error_code": result.get("error", {}).get("code"),
                "details": result
            }


async def handle_send_template_message(
    to: str,
    template_name: str,
    language_code: str = "tr",
    body_parameters: list = None,
    header_parameters: list = None
) -> dict:
    """Send a template message via WhatsApp"""
    creds = get_whatsapp_credentials()
    phone_number_id = creds["phone_number_id"]
    access_token = creds["access_token"]

    if not phone_number_id or not access_token:
        return {
            "success": False,
            "error": "Missing WhatsApp credentials"
        }

    to_formatted = format_phone_number(to)

    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Build template components
    components = []

    if header_parameters:
        components.append({
            "type": "header",
            "parameters": [{"type": "text", "text": p} for p in header_parameters]
        })

    if body_parameters:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in body_parameters]
        })

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_formatted,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code}
        }
    }

    if components:
        payload["template"]["components"] = components

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        result = response.json()

        if "messages" in result:
            message_id = result["messages"][0]["id"]
            return {
                "success": True,
                "message_id": message_id,
                "to": to_formatted,
                "template": template_name,
                "language": language_code,
                "sent_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": result.get("error", {}).get("message", str(result)),
                "error_code": result.get("error", {}).get("code"),
                "details": result
            }


async def handle_send_document(
    to: str,
    document_url: str,
    filename: str,
    caption: str = None
) -> dict:
    """Send a document via WhatsApp"""
    creds = get_whatsapp_credentials()
    phone_number_id = creds["phone_number_id"]
    access_token = creds["access_token"]

    if not phone_number_id or not access_token:
        return {"success": False, "error": "Missing WhatsApp credentials"}

    to_formatted = format_phone_number(to)

    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    document_obj = {
        "link": document_url,
        "filename": filename
    }
    if caption:
        document_obj["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_formatted,
        "type": "document",
        "document": document_obj
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        result = response.json()

        if "messages" in result:
            return {
                "success": True,
                "message_id": result["messages"][0]["id"],
                "to": to_formatted,
                "document": filename,
                "sent_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": result.get("error", {}).get("message", str(result))
            }


async def handle_send_image(
    to: str,
    image_url: str,
    caption: str = None
) -> dict:
    """Send an image via WhatsApp"""
    creds = get_whatsapp_credentials()
    phone_number_id = creds["phone_number_id"]
    access_token = creds["access_token"]

    if not phone_number_id or not access_token:
        return {"success": False, "error": "Missing WhatsApp credentials"}

    to_formatted = format_phone_number(to)

    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    image_obj = {"link": image_url}
    if caption:
        image_obj["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_formatted,
        "type": "image",
        "image": image_obj
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        result = response.json()

        if "messages" in result:
            return {
                "success": True,
                "message_id": result["messages"][0]["id"],
                "to": to_formatted,
                "sent_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": result.get("error", {}).get("message", str(result))
            }


async def handle_get_message_status(message_id: str) -> dict:
    """Get status of a sent message"""
    creds = get_whatsapp_credentials()
    access_token = creds["access_token"]

    if not access_token:
        return {"success": False, "error": "Missing WhatsApp access token"}

    url = f"{GRAPH_API_BASE}/{message_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        result = response.json()

        if "id" in result:
            return {
                "success": True,
                "message_id": message_id,
                "status": result.get("status", "unknown"),
                "data": result
            }
        else:
            return {
                "success": False,
                "error": result.get("error", {}).get("message", str(result))
            }


async def handle_get_templates(
    limit: int = 50,
    status: str = None
) -> dict:
    """Get available message templates"""
    creds = get_whatsapp_credentials()
    business_account_id = creds["business_account_id"]
    access_token = creds["access_token"]

    if not business_account_id or not access_token:
        return {
            "success": False,
            "error": "Missing WHATSAPP_BUSINESS_ACCOUNT_ID or WHATSAPP_ACCESS_TOKEN"
        }

    url = f"{GRAPH_API_BASE}/{business_account_id}/message_templates"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit}

    if status:
        params["status"] = status

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)
        result = response.json()

        if "data" in result:
            templates = []
            for t in result["data"]:
                templates.append({
                    "name": t.get("name"),
                    "status": t.get("status"),
                    "category": t.get("category"),
                    "language": t.get("language"),
                    "id": t.get("id")
                })

            return {
                "success": True,
                "templates": templates,
                "count": len(templates)
            }
        else:
            return {
                "success": False,
                "error": result.get("error", {}).get("message", str(result))
            }


async def handle_get_phone_number_info() -> dict:
    """Get WhatsApp Business phone number info"""
    creds = get_whatsapp_credentials()
    phone_number_id = creds["phone_number_id"]
    access_token = creds["access_token"]

    if not phone_number_id or not access_token:
        return {"success": False, "error": "Missing WhatsApp credentials"}

    url = f"{GRAPH_API_BASE}/{phone_number_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "fields": "display_phone_number,verified_name,quality_rating,status,messaging_limit_tier"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)
        result = response.json()

        if "display_phone_number" in result:
            return {
                "success": True,
                "phone_number": result.get("display_phone_number"),
                "verified_name": result.get("verified_name"),
                "quality_rating": result.get("quality_rating"),
                "status": result.get("status"),
                "messaging_limit": result.get("messaging_limit_tier"),
                "phone_number_id": phone_number_id
            }
        else:
            return {
                "success": False,
                "error": result.get("error", {}).get("message", str(result))
            }


# Tool handler mapping
TOOL_HANDLERS = {
    "send_message": handle_send_message,
    "send_template_message": handle_send_template_message,
    "send_document": handle_send_document,
    "send_image": handle_send_image,
    "get_message_status": handle_get_message_status,
    "get_templates": handle_get_templates,
    "get_phone_number_info": handle_get_phone_number_info
}


# ============================================================================
# MCP Server Handlers
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    if name not in TOOL_HANDLERS:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        handler = TOOL_HANDLERS[name]
        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2))]


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
