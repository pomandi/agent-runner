#!/usr/bin/env python3
"""
Meta Ads Ad MCP Server
----------------------
Creates ads via Meta Marketing API (Graph API v22.0) for Claude MCP tooling.

Tools:
- create_ad: Create an ad inside an ad set using an existing creative.

Environment Variables (required):
- FACEBOOK_ACCESS_TOKEN   : System user/page access token with ads_management
- FACEBOOK_AD_ACCOUNT_ID  : Default ad account (e.g., act_123456789012345)
"""

import asyncio
import json
import os
from typing import Any, Dict

import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

SERVER = Server("meta-ads-ad")
API_VERSION = "v22.0"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing environment variable: {name}")
    return value


def ensure_act_prefix(ad_account_id: str) -> str:
    return ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"


async def post_graph(url: str, payload: Dict[str, Any], access_token: str) -> Dict[str, Any]:
    data = {k: v for k, v in payload.items() if v is not None}
    data["access_token"] = access_token
    response = await asyncio.to_thread(requests.post, url, data=data, timeout=30)
    try:
        body = response.json()
    except Exception:
        response.raise_for_status()
        body = {"error": {"message": "Unexpected non-JSON response"}}

    if response.status_code >= 400 or "error" in body:
        message = body.get("error", {}).get("message", f"HTTP {response.status_code}")
        raise ValueError(f"Meta API error: {message}")
    return body


def as_text(payload: Dict[str, Any]) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, indent=2))])


TOOLS = [
    Tool(
        name="create_ad",
        description="Create a Meta ad using an existing creative. Uses env FACEBOOK_ACCESS_TOKEN and FACEBOOK_AD_ACCOUNT_ID if ad_account_id not provided.",
        inputSchema={
            "type": "object",
            "properties": {
                "ad_account_id": {"type": "string", "description": "Ad account id, with or without act_ prefix."},
                "adset_id": {"type": "string", "description": "Parent ad set id."},
                "name": {"type": "string", "description": "Ad name."},
                "creative_id": {"type": "string", "description": "Existing ad creative id."},
                "status": {"type": "string", "description": "PAUSED or ACTIVE. Default PAUSED.", "default": "PAUSED"},
                "tracking_specs": {"type": "object", "description": "Optional tracking_specs JSON."},
            },
            "required": ["adset_id", "name", "creative_id"],
        },
    ),
]


@SERVER.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@SERVER.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    if name == "create_ad":
        result = await create_ad(arguments)
        return as_text(result)
    raise ValueError(f"Unknown tool: {name}")


async def create_ad(args: Dict[str, Any]) -> Dict[str, Any]:
    access_token = require_env("FACEBOOK_ACCESS_TOKEN")
    ad_account_id = ensure_act_prefix(args.get("ad_account_id") or require_env("FACEBOOK_AD_ACCOUNT_ID"))

    payload = {
        "name": args["name"],
        "adset_id": args["adset_id"],
        "status": args.get("status", "PAUSED"),
        "creative": json.dumps({"creative_id": args["creative_id"]}),
        "tracking_specs": json.dumps(args.get("tracking_specs")) if args.get("tracking_specs") else None,
    }

    endpoint = f"https://graph.facebook.com/{API_VERSION}/{ad_account_id}/ads"
    body = await post_graph(endpoint, payload, access_token)
    return {
        "ad_id": body.get("id"),
        "status": "created",
        "endpoint": endpoint,
        "request": {"adset_id": args["adset_id"], "creative_id": args["creative_id"]},
    }


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
