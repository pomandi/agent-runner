#!/usr/bin/env python3
"""
Microsoft Outlook MCP Server
=============================
MCP Server for Microsoft Graph API integration with Claude Code.

Provides tools for:
- Reading emails from inbox
- Searching emails
- Getting email details
- Listing folders
- Reading attachments

Environment Variables Required (from .env):
- MICROSOFT_CLIENT_ID: Azure App Client ID
- MICROSOFT_CLIENT_SECRET: Azure App Client Secret
- MICROSOFT_TENANT_ID: Azure Tenant ID
- MICROSOFT_REFRESH_TOKEN: OAuth2 Refresh Token

Version: 1.0
API: Microsoft Graph API v1.0
"""

import asyncio
import json
import os
import sys
import base64
from typing import Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# HTTP client
import httpx

# Server info
SERVER_NAME = "microsoft-outlook"
SERVER_VERSION = "1.0.0"

# Initialize MCP server
server = Server(SERVER_NAME)

# Global token cache
_access_token: Optional[str] = None
_token_expiry: Optional[datetime] = None

# Load env file
def load_env():
    """Load environment variables from .env file (try multiple locations)"""
    env_paths = [
        Path("/app/.env"),  # Coolify deployment
        Path("/home/claude/.claude/agents/agent-runner/.env"),  # Agent runner local
        Path("/home/claude/.claude/agents/unified-analytics/mcp-servers/.env"),  # Legacy local
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        # Always update Microsoft tokens (they change frequently)
                        if key.startswith("MICROSOFT_") or key not in os.environ:
                            os.environ[key] = value
            break  # Use first found .env file

# Load env on import
load_env()

# Configuration
def get_config() -> dict:
    """Get Microsoft Graph configuration"""
    return {
        "client_id": os.getenv("MICROSOFT_CLIENT_ID"),
        "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET"),
        "tenant_id": os.getenv("MICROSOFT_TENANT_ID"),
        "refresh_token": os.getenv("MICROSOFT_REFRESH_TOKEN"),
        "user_id": os.getenv("MICROSOFT_USER_ID", "me"),
        "token_url": os.getenv("MICROSOFT_TOKEN_URL"),
    }


async def get_access_token() -> str:
    """Get valid access token, refreshing if necessary"""
    global _access_token, _token_expiry

    # Check if we have a valid cached token
    if _access_token and _token_expiry and datetime.now() < _token_expiry:
        return _access_token

    # Reload env to get latest tokens
    load_env()
    config = get_config()

    # Use "common" endpoint for personal Microsoft accounts (hotmail, outlook.com)
    # This works with public clients and supports Mail.Read scope properly
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

    # Public client - no client_secret, use full Graph API scope URLs
    data = {
        "client_id": config["client_id"],
        "refresh_token": config["refresh_token"],
        "grant_type": "refresh_token",
        "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read offline_access"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)

        if response.status_code != 200:
            error_detail = response.text
            raise Exception(f"Token refresh failed: {response.status_code} - {error_detail}")

        token_data = response.json()
        _access_token = token_data["access_token"]

        # Set expiry (default 1 hour, subtract 5 min buffer)
        expires_in = token_data.get("expires_in", 3600)
        _token_expiry = datetime.now() + timedelta(seconds=expires_in - 300)

        # Update refresh token in env if new one provided
        if "refresh_token" in token_data:
            new_refresh = token_data["refresh_token"]
            if new_refresh != config["refresh_token"]:
                update_refresh_token(new_refresh)

        return _access_token


def update_refresh_token(new_token: str):
    """Update refresh token in .env file"""
    env_path = Path("/workspace/server-data/.env")
    if not env_path.exists():
        return

    content = env_path.read_text()
    lines = content.split('\n')
    updated = False

    for i, line in enumerate(lines):
        if line.startswith('MICROSOFT_REFRESH_TOKEN='):
            lines[i] = f"MICROSOFT_REFRESH_TOKEN='{new_token}'"
            updated = True
            break

    if updated:
        env_path.write_text('\n'.join(lines))
        os.environ["MICROSOFT_REFRESH_TOKEN"] = new_token


async def graph_request(endpoint: str, params: dict = None) -> dict:
    """Make authenticated request to Microsoft Graph API"""
    token = await get_access_token()

    url = f"https://graph.microsoft.com/v1.0/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params, timeout=30.0)

        if response.status_code == 401:
            # Token expired, clear cache and retry
            global _access_token, _token_expiry
            _access_token = None
            _token_expiry = None
            token = await get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            response = await client.get(url, headers=headers, params=params, timeout=30.0)

        if response.status_code != 200:
            raise Exception(f"Graph API Error: {response.status_code} - {response.text}")

        return response.json()


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="get_inbox",
        description="Get emails from inbox. Returns subject, sender, date, preview, and read status.",
        inputSchema={
            "type": "object",
            "properties": {
                "top": {
                    "type": "integer",
                    "description": "Number of emails to retrieve (default: 20, max: 100)"
                },
                "skip": {
                    "type": "integer",
                    "description": "Number of emails to skip for pagination (default: 0)"
                },
                "filter": {
                    "type": "string",
                    "description": "OData filter (e.g., 'isRead eq false' for unread only)"
                },
                "orderby": {
                    "type": "string",
                    "description": "Sort order (default: 'receivedDateTime desc')"
                }
            }
        }
    ),
    Tool(
        name="search_emails",
        description="Search emails by keyword in subject, body, or sender.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (searches in subject, body, sender)"
                },
                "top": {
                    "type": "integer",
                    "description": "Number of results (default: 20)"
                },
                "folder": {
                    "type": "string",
                    "description": "Folder to search in (default: all folders)"
                }
            },
            "required": ["query"]
        }
    ),
    Tool(
        name="get_email",
        description="Get full email details including body content.",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the email message"
                }
            },
            "required": ["message_id"]
        }
    ),
    Tool(
        name="get_folders",
        description="List mail folders (Inbox, Sent, Drafts, etc.).",
        inputSchema={
            "type": "object",
            "properties": {
                "include_children": {
                    "type": "boolean",
                    "description": "Include child folders (default: false)"
                }
            }
        }
    ),
    Tool(
        name="get_folder_emails",
        description="Get emails from a specific folder.",
        inputSchema={
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "Folder ID or well-known name (inbox, sentitems, drafts, deleteditems, junkemail)"
                },
                "top": {
                    "type": "integer",
                    "description": "Number of emails (default: 20)"
                },
                "filter": {
                    "type": "string",
                    "description": "OData filter"
                }
            },
            "required": ["folder_id"]
        }
    ),
    Tool(
        name="get_attachments",
        description="Get list of attachments for an email.",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the email message"
                }
            },
            "required": ["message_id"]
        }
    ),
    Tool(
        name="get_unread_count",
        description="Get count of unread emails in inbox or specific folder.",
        inputSchema={
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "Folder ID (default: inbox)"
                }
            }
        }
    ),
    Tool(
        name="get_recent_emails",
        description="Get emails received in the last N days.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days back (default: 7)"
                },
                "top": {
                    "type": "integer",
                    "description": "Max results (default: 50)"
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "Only unread emails (default: false)"
                }
            }
        }
    ),
    Tool(
        name="download_attachment",
        description="Download an email attachment and save it to a specified path.",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the email message"
                },
                "attachment_id": {
                    "type": "string",
                    "description": "The ID of the attachment"
                },
                "save_path": {
                    "type": "string",
                    "description": "Full path where the file should be saved"
                }
            },
            "required": ["message_id", "attachment_id", "save_path"]
        }
    )
]


# ============================================================================
# Tool Handlers
# ============================================================================

def format_email_summary(message: dict) -> dict:
    """Format email for summary display"""
    return {
        "id": message.get("id"),
        "subject": message.get("subject", "(No Subject)"),
        "from": message.get("from", {}).get("emailAddress", {}).get("address", "Unknown"),
        "from_name": message.get("from", {}).get("emailAddress", {}).get("name", ""),
        "received": message.get("receivedDateTime"),
        "isRead": message.get("isRead", False),
        "hasAttachments": message.get("hasAttachments", False),
        "importance": message.get("importance", "normal"),
        "preview": message.get("bodyPreview", "")[:200]
    }


async def handle_get_inbox(top: int = 20, skip: int = 0, filter: str = None, orderby: str = None) -> dict:
    """Get inbox emails"""
    top = min(top, 100)

    params = {
        "$top": top,
        "$skip": skip,
        "$orderby": orderby or "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,importance,bodyPreview"
    }

    if filter:
        params["$filter"] = filter

    result = await graph_request("me/mailFolders/inbox/messages", params)

    emails = [format_email_summary(msg) for msg in result.get("value", [])]

    return {
        "total_returned": len(emails),
        "skip": skip,
        "emails": emails
    }


async def handle_search_emails(query: str, top: int = 20, folder: str = None) -> dict:
    """Search emails"""
    top = min(top, 50)

    params = {
        "$top": top,
        "$search": f'"{query}"',
        "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,bodyPreview"
    }

    endpoint = f"me/mailFolders/{folder}/messages" if folder else "me/messages"
    result = await graph_request(endpoint, params)

    emails = [format_email_summary(msg) for msg in result.get("value", [])]

    return {
        "query": query,
        "total_results": len(emails),
        "emails": emails
    }


async def handle_get_email(message_id: str) -> dict:
    """Get full email details"""
    params = {
        "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,isRead,hasAttachments,importance,body,bodyPreview,conversationId"
    }

    result = await graph_request(f"me/messages/{message_id}", params)

    return {
        "id": result.get("id"),
        "subject": result.get("subject", "(No Subject)"),
        "from": {
            "email": result.get("from", {}).get("emailAddress", {}).get("address"),
            "name": result.get("from", {}).get("emailAddress", {}).get("name")
        },
        "to": [
            {"email": r.get("emailAddress", {}).get("address"), "name": r.get("emailAddress", {}).get("name")}
            for r in result.get("toRecipients", [])
        ],
        "cc": [
            {"email": r.get("emailAddress", {}).get("address"), "name": r.get("emailAddress", {}).get("name")}
            for r in result.get("ccRecipients", [])
        ],
        "received": result.get("receivedDateTime"),
        "sent": result.get("sentDateTime"),
        "isRead": result.get("isRead"),
        "hasAttachments": result.get("hasAttachments"),
        "importance": result.get("importance"),
        "body": {
            "contentType": result.get("body", {}).get("contentType"),
            "content": result.get("body", {}).get("content")
        },
        "conversationId": result.get("conversationId")
    }


async def handle_get_folders(include_children: bool = False) -> dict:
    """Get mail folders"""
    params = {
        "$select": "id,displayName,totalItemCount,unreadItemCount,parentFolderId"
    }

    if include_children:
        params["$expand"] = "childFolders"

    result = await graph_request("me/mailFolders", params)

    folders = []
    for folder in result.get("value", []):
        folder_info = {
            "id": folder.get("id"),
            "name": folder.get("displayName"),
            "totalItems": folder.get("totalItemCount", 0),
            "unreadItems": folder.get("unreadItemCount", 0)
        }
        if include_children and "childFolders" in folder:
            folder_info["children"] = [
                {
                    "id": cf.get("id"),
                    "name": cf.get("displayName"),
                    "totalItems": cf.get("totalItemCount", 0),
                    "unreadItems": cf.get("unreadItemCount", 0)
                }
                for cf in folder.get("childFolders", [])
            ]
        folders.append(folder_info)

    return {
        "total_folders": len(folders),
        "folders": folders
    }


async def handle_get_folder_emails(folder_id: str, top: int = 20, filter: str = None) -> dict:
    """Get emails from specific folder"""
    top = min(top, 100)

    params = {
        "$top": top,
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,importance,bodyPreview"
    }

    if filter:
        params["$filter"] = filter

    result = await graph_request(f"me/mailFolders/{folder_id}/messages", params)

    emails = [format_email_summary(msg) for msg in result.get("value", [])]

    return {
        "folder": folder_id,
        "total_returned": len(emails),
        "emails": emails
    }


async def handle_get_attachments(message_id: str) -> dict:
    """Get email attachments"""
    result = await graph_request(f"me/messages/{message_id}/attachments")

    attachments = []
    for att in result.get("value", []):
        attachments.append({
            "id": att.get("id"),
            "name": att.get("name"),
            "contentType": att.get("contentType"),
            "size": att.get("size"),
            "isInline": att.get("isInline", False)
        })

    return {
        "message_id": message_id,
        "total_attachments": len(attachments),
        "attachments": attachments
    }


async def handle_get_unread_count(folder_id: str = "inbox") -> dict:
    """Get unread email count"""
    result = await graph_request(f"me/mailFolders/{folder_id}")

    return {
        "folder": result.get("displayName", folder_id),
        "unread_count": result.get("unreadItemCount", 0),
        "total_count": result.get("totalItemCount", 0)
    }


async def handle_get_recent_emails(days: int = 7, top: int = 50, unread_only: bool = False) -> dict:
    """Get recent emails"""
    top = min(top, 100)

    # Calculate date filter
    since_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    filter_parts = [f"receivedDateTime ge {since_date}"]
    if unread_only:
        filter_parts.append("isRead eq false")

    params = {
        "$top": top,
        "$orderby": "receivedDateTime desc",
        "$filter": " and ".join(filter_parts),
        "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,importance,bodyPreview"
    }

    result = await graph_request("me/messages", params)

    emails = [format_email_summary(msg) for msg in result.get("value", [])]

    return {
        "days": days,
        "since": since_date,
        "unread_only": unread_only,
        "total_returned": len(emails),
        "emails": emails
    }


async def handle_download_attachment(message_id: str, attachment_id: str, save_path: str) -> dict:
    """Download email attachment and save to file"""
    # Get the attachment with content
    token = await get_access_token()

    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments/{attachment_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=30.0)

        if response.status_code != 200:
            raise Exception(f"Failed to download attachment: {response.status_code} - {response.text}")

        attachment_data = response.json()

        # Get base64 content
        content_bytes = attachment_data.get("contentBytes")
        if not content_bytes:
            raise Exception("No content in attachment")

        # Decode and save
        file_data = base64.b64decode(content_bytes)

        # Ensure directory exists
        save_dir = Path(save_path).parent
        save_dir.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(save_path, 'wb') as f:
            f.write(file_data)

        return {
            "message_id": message_id,
            "attachment_id": attachment_id,
            "name": attachment_data.get("name"),
            "size": attachment_data.get("size"),
            "saved_to": save_path,
            "success": True
        }


# Tool handler mapping
TOOL_HANDLERS = {
    "get_inbox": handle_get_inbox,
    "search_emails": handle_search_emails,
    "get_email": handle_get_email,
    "get_folders": handle_get_folders,
    "get_folder_emails": handle_get_folder_emails,
    "get_attachments": handle_get_attachments,
    "get_unread_count": handle_get_unread_count,
    "get_recent_emails": handle_get_recent_emails,
    "download_attachment": handle_download_attachment
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
        error_msg = str(e)
        return [TextContent(type="text", text=f"Error: {error_msg}")]


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
