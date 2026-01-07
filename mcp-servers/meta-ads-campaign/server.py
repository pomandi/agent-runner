#!/usr/bin/env python3
"""
Meta Ads Campaign MCP Server
----------------------------
Creates Meta Ads campaigns via Graph API (v22.0) for Claude MCP tooling.

Tools:
- create_campaign: Create a campaign with objective/budget/special categories.

Environment Variables (required):
- FACEBOOK_ACCESS_TOKEN   : System user/page access token with ads_management
- FACEBOOK_AD_ACCOUNT_ID  : Default ad account (e.g., act_123456789012345)

Optional:
- FACEBOOK_APP_ID / FACEBOOK_APP_SECRET if you handle token refresh externally.
"""

import asyncio
import json
import os
from typing import Any, Dict

import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

SERVER = Server("meta-ads-campaign")
API_VERSION = "v22.0"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
TOOLS = [
    Tool(
        name="create_campaign",
        description="""Create a Meta Ads campaign. Uses env FACEBOOK_ACCESS_TOKEN and FACEBOOK_AD_ACCOUNT_ID if ad_account_id not provided.

IMPORTANT NOTES:
- Use LOWEST_COST_WITHOUT_CAP for automatic bidding (recommended for beginners)
- Use LOWEST_COST_WITH_BID_CAP if you want to set a max bid (requires bid_amount in ad sets)
- Budget can be set at campaign level (here) OR ad set level, not both
- For traffic campaigns use OUTCOME_TRAFFIC, for leads use OUTCOME_LEADS""",
        inputSchema={
            "type": "object",
            "properties": {
                "ad_account_id": {"type": "string", "description": "Ad account id, with or without act_ prefix."},
                "name": {"type": "string", "description": "Campaign name."},
                "objective": {
                    "type": "string",
                    "description": "OUTCOME_TRAFFIC, OUTCOME_LEADS, OUTCOME_SALES, OUTCOME_ENGAGEMENT, OUTCOME_AWARENESS.",
                },
                "daily_budget": {"type": "integer", "description": "Daily budget in cents (e.g., 1000 = €10). Set here OR in ad sets."},
                "status": {"type": "string", "description": "PAUSED or ACTIVE. Default PAUSED.", "default": "PAUSED"},
                "special_ad_categories": {
                    "type": "array",
                    "description": "Special categories: NONE, CREDIT, EMPLOYMENT, HOUSING. Default: NONE.",
                    "items": {"type": "string"},
                    "default": ["NONE"],
                },
                "bid_strategy": {
                    "type": "string",
                    "description": "LOWEST_COST_WITHOUT_CAP (auto bidding, recommended) or LOWEST_COST_WITH_BID_CAP (requires bid_amount in ad sets).",
                    "default": "LOWEST_COST_WITHOUT_CAP",
                },
                "start_time": {"type": "string", "description": "Optional ISO8601 start_time."},
                "stop_time": {"type": "string", "description": "Optional ISO8601 stop_time."},
            },
            "required": ["name", "objective", "daily_budget"],
        },
    ),
]


@SERVER.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@SERVER.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    if name == "create_campaign":
        result = await create_campaign(arguments)
        return as_text(result)
    raise ValueError(f"Unknown tool: {name}")


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
async def create_campaign(args: Dict[str, Any]) -> Dict[str, Any]:
    access_token = require_env("FACEBOOK_ACCESS_TOKEN")
    ad_account_id = ensure_act_prefix(args.get("ad_account_id") or require_env("FACEBOOK_AD_ACCOUNT_ID"))

    # Default to LOWEST_COST_WITHOUT_CAP if not specified (easier for ad sets)
    bid_strategy = args.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP")

    payload = {
        "name": args["name"],
        "objective": args["objective"],
        "status": args.get("status", "PAUSED"),
        "daily_budget": args["daily_budget"],
        "special_ad_categories": json.dumps(args.get("special_ad_categories", ["NONE"])),
        "bid_strategy": bid_strategy,
        "start_time": args.get("start_time"),
        "stop_time": args.get("stop_time"),
    }

    endpoint = f"https://graph.facebook.com/{API_VERSION}/{ad_account_id}/campaigns"
    body = await post_graph(endpoint, payload, access_token)
    return {
        "campaign_id": body.get("id"),
        "status": "created",
        "endpoint": endpoint,
        "request": {k: v for k, v in payload.items() if k != "special_ad_categories"},
    }


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
