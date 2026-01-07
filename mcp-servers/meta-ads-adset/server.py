#!/usr/bin/env python3
"""
Meta Ads Ad Set MCP Server
--------------------------
Creates Meta Ads ad sets via Graph API (v22.0) for Claude MCP tooling.

Tools:
- create_adset: Create an ad set with targeting and optimization settings.

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

SERVER = Server("meta-ads-adset")
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
        name="create_adset",
        description="""Create a Meta Ads ad set. Uses env FACEBOOK_ACCESS_TOKEN and FACEBOOK_AD_ACCOUNT_ID if ad_account_id not provided.

IMPORTANT NOTES:
- If campaign has daily_budget, do NOT set daily_budget on ad set (only one level can have budget)
- If campaign uses LOWEST_COST_WITH_BID_CAP strategy, bid_amount is REQUIRED
- For Belgium/Netherlands targeting, use: {"geo_locations": {"countries": ["BE", "NL"]}, "age_min": 25, "age_max": 55}
- For interests, use flexible_spec: [{"interests": [{"id": "6003409392877", "name": "Weddings"}]}]""",
        inputSchema={
            "type": "object",
            "properties": {
                "ad_account_id": {"type": "string", "description": "Ad account id, with or without act_ prefix."},
                "campaign_id": {"type": "string", "description": "Parent campaign id."},
                "name": {"type": "string", "description": "Ad set name."},
                "daily_budget": {"type": "integer", "description": "Daily budget in cents. OMIT if campaign has budget."},
                "billing_event": {"type": "string", "description": "IMPRESSIONS or LINK_CLICKS. Default: IMPRESSIONS."},
                "optimization_goal": {"type": "string", "description": "LINK_CLICKS, LANDING_PAGE_VIEWS, REACH, IMPRESSIONS, LEAD_GENERATION."},
                "targeting": {"type": "object", "description": "Targeting JSON: {geo_locations, age_min, age_max, genders, flexible_spec}."},
                "status": {"type": "string", "description": "PAUSED or ACTIVE. Default PAUSED.", "default": "PAUSED"},
                "bid_amount": {"type": "integer", "description": "Bid cap in cents. REQUIRED if campaign uses LOWEST_COST_WITH_BID_CAP."},
                "start_time": {"type": "string", "description": "Optional ISO8601 start_time."},
                "end_time": {"type": "string", "description": "Optional ISO8601 end_time."},
                "promoted_object": {"type": "object", "description": "Optional promoted_object JSON (e.g., pixel_id)."},
            },
            "required": ["campaign_id", "name", "billing_event", "optimization_goal", "targeting"],
        },
    ),
]


@SERVER.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@SERVER.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    if name == "create_adset":
        result = await create_adset(arguments)
        return as_text(result)
    raise ValueError(f"Unknown tool: {name}")


async def create_adset(args: Dict[str, Any]) -> Dict[str, Any]:
    access_token = require_env("FACEBOOK_ACCESS_TOKEN")
    ad_account_id = ensure_act_prefix(args.get("ad_account_id") or require_env("FACEBOOK_AD_ACCOUNT_ID"))

    payload = {
        "name": args["name"],
        "campaign_id": args["campaign_id"],
        "daily_budget": args["daily_budget"],
        "billing_event": args["billing_event"],
        "optimization_goal": args["optimization_goal"],
        "status": args.get("status", "PAUSED"),
        "bid_amount": args.get("bid_amount"),
        "start_time": args.get("start_time"),
        "end_time": args.get("end_time"),
        "targeting": json.dumps(args["targeting"]),
        "promoted_object": json.dumps(args.get("promoted_object")) if args.get("promoted_object") else None,
    }

    endpoint = f"https://graph.facebook.com/{API_VERSION}/{ad_account_id}/adsets"
    body = await post_graph(endpoint, payload, access_token)
    return {
        "adset_id": body.get("id"),
        "status": "created",
        "endpoint": endpoint,
        "request": {k: v for k, v in payload.items() if k not in {"targeting", "promoted_object"}},
    }


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
