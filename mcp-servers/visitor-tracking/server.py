#!/usr/bin/env python3
"""
Visitor Tracking MCP Server v1.0
================================
Custom visitor tracking database MCP Server for Claude Code integration.

Provides tools for:
- Session statistics (total, unique visitors, attribution)
- Conversion tracking
- Landing page performance
- Traffic source analysis
- Combined summary for analytics workflows

Environment Variables Required:
- VISITOR_TRACKING_DATABASE_URL: PostgreSQL connection string

Database: cryptic-brushlands-51854 (Visitor Tracking PostgreSQL)
Version: 1.0.0
Last Updated: 2026-01-11
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Async PostgreSQL
import asyncpg

# Server info
SERVER_NAME = "visitor-tracking"
SERVER_VERSION = "1.0.0"

# Initialize MCP server
server = Server(SERVER_NAME)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def get_database_url() -> str:
    """Get database URL from environment or .env file"""
    # Try environment variable first
    db_url = os.environ.get("VISITOR_TRACKING_DATABASE_URL")
    if db_url:
        print(f"[{SERVER_NAME.upper()}] Using DATABASE_URL from environment", file=sys.stderr)
        return db_url

    # Fall back to .env file
    env_file = Path.home() / '.claude' / '.env'
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    if key == 'VISITOR_TRACKING_DATABASE_URL':
                        print(f"[{SERVER_NAME.upper()}] Using DATABASE_URL from .env file", file=sys.stderr)
                        return value.strip('"').strip("'")

    raise ValueError("VISITOR_TRACKING_DATABASE_URL not found in environment or .env file")


async def get_pool() -> asyncpg.Pool:
    """Get or create connection pool"""
    global _pool
    if _pool is None:
        db_url = get_database_url()
        _pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
        print(f"[{SERVER_NAME.upper()}] Connection pool created", file=sys.stderr)
    return _pool


def get_date_range(days: int = 7) -> tuple[datetime, datetime]:
    """Calculate date range from days parameter"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

TOOLS = [
    Tool(
        name="get_visitor_stats",
        description="Get session and visitor statistics including attribution metrics. Returns total sessions, unique visitors, UTM/GCLID/FBCLID counts, and median session duration. Excludes bot traffic.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default: 7"
                }
            }
        }
    ),
    Tool(
        name="get_conversions",
        description="Get conversion statistics grouped by conversion type/goal.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default: 7"
                }
            }
        }
    ),
    Tool(
        name="get_top_landing_pages",
        description="Get top landing pages by session count with unique visitor breakdown. Excludes bot traffic.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default: 7"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of pages to return. Default: 10"
                }
            }
        }
    ),
    Tool(
        name="get_traffic_sources",
        description="Get traffic source breakdown by UTM source/medium. Excludes bot traffic.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default: 7"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of sources to return. Default: 10"
                }
            }
        }
    ),
    Tool(
        name="get_visitor_summary",
        description="Get complete visitor analytics summary in a single call. Includes stats, conversions, landing pages, and traffic sources. Optimized for daily analytics workflow.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default: 7"
                }
            }
        }
    ),
]


# ============================================================================
# TOOL HANDLERS
# ============================================================================

async def handle_get_visitor_stats(days: int = 7) -> dict:
    """Get session and visitor statistics"""
    pool = await get_pool()
    start_date, end_date = get_date_range(days)

    query = """
        SELECT
            COUNT(*) as total_sessions,
            COUNT(DISTINCT s.visitor_id) as unique_visitors,
            COUNT(CASE WHEN s.utm_source IS NOT NULL THEN 1 END) as utm_sessions,
            COUNT(CASE WHEN s.gclid IS NOT NULL THEN 1 END) as gclid_sessions,
            COUNT(CASE WHEN s.fbclid IS NOT NULL THEN 1 END) as fbclid_sessions,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.total_time_ms / 1000.0) as median_session_duration
        FROM sessions s
        JOIN visitors v ON s.visitor_id = v.visitor_id
        WHERE s.started_at >= $1 AND s.started_at < $2
        AND v.is_bot = false
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, start_date, end_date)

    return {
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_sessions": row["total_sessions"] if row else 0,
        "unique_visitors": row["unique_visitors"] if row else 0,
        "utm_sessions": row["utm_sessions"] if row else 0,
        "gclid_sessions": row["gclid_sessions"] if row else 0,
        "fbclid_sessions": row["fbclid_sessions"] if row else 0,
        "median_session_duration": float(row["median_session_duration"]) if row and row["median_session_duration"] else 0,
    }


async def handle_get_conversions(days: int = 7) -> dict:
    """Get conversion statistics by type"""
    pool = await get_pool()
    start_date, end_date = get_date_range(days)

    query = """
        SELECT ct.name as goal_type, COUNT(*) as count
        FROM conversions c
        LEFT JOIN conversion_types ct ON c.conversion_type_id = ct.id
        WHERE c.created_at >= $1 AND c.created_at < $2
        GROUP BY ct.name
        ORDER BY count DESC
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, start_date, end_date)

    return {
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "conversions": [dict(row) for row in rows],
        "total_conversions": sum(row["count"] for row in rows),
    }


async def handle_get_top_landing_pages(days: int = 7, limit: int = 10) -> dict:
    """Get top landing pages by session count"""
    pool = await get_pool()
    start_date, end_date = get_date_range(days)

    query = """
        SELECT s.landing_page, COUNT(*) as sessions, COUNT(DISTINCT s.visitor_id) as unique_visitors
        FROM sessions s
        JOIN visitors v ON s.visitor_id = v.visitor_id
        WHERE s.started_at >= $1 AND s.started_at < $2
        AND v.is_bot = false
        GROUP BY s.landing_page
        ORDER BY sessions DESC
        LIMIT $3
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, start_date, end_date, limit)

    return {
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "landing_pages": [dict(row) for row in rows],
    }


async def handle_get_traffic_sources(days: int = 7, limit: int = 10) -> dict:
    """Get traffic source breakdown"""
    pool = await get_pool()
    start_date, end_date = get_date_range(days)

    query = """
        SELECT
            COALESCE(s.utm_source, 'direct') as source,
            COALESCE(s.utm_medium, 'none') as medium,
            COUNT(*) as sessions
        FROM sessions s
        JOIN visitors v ON s.visitor_id = v.visitor_id
        WHERE s.started_at >= $1 AND s.started_at < $2
        AND v.is_bot = false
        GROUP BY s.utm_source, s.utm_medium
        ORDER BY sessions DESC
        LIMIT $3
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, start_date, end_date, limit)

    return {
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "traffic_sources": [dict(row) for row in rows],
    }


async def handle_get_visitor_summary(days: int = 7) -> dict:
    """Get complete visitor analytics summary in a single call"""
    pool = await get_pool()
    start_date, end_date = get_date_range(days)

    print(f"[{SERVER_NAME.upper()}] Fetching visitor summary for {days} days ({start_date.date()} to {end_date.date()})", file=sys.stderr)

    async with pool.acquire() as conn:
        # Query 1: Session stats
        stats_query = """
            SELECT
                COUNT(*) as total_sessions,
                COUNT(DISTINCT s.visitor_id) as unique_visitors,
                COUNT(CASE WHEN s.utm_source IS NOT NULL THEN 1 END) as utm_sessions,
                COUNT(CASE WHEN s.gclid IS NOT NULL THEN 1 END) as gclid_sessions,
                COUNT(CASE WHEN s.fbclid IS NOT NULL THEN 1 END) as fbclid_sessions,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.total_time_ms / 1000.0) as median_session_duration
            FROM sessions s
            JOIN visitors v ON s.visitor_id = v.visitor_id
            WHERE s.started_at >= $1 AND s.started_at < $2
            AND v.is_bot = false
        """
        stats_row = await conn.fetchrow(stats_query, start_date, end_date)

        # Query 2: Conversions
        conversions_query = """
            SELECT ct.name as goal_type, COUNT(*) as count
            FROM conversions c
            LEFT JOIN conversion_types ct ON c.conversion_type_id = ct.id
            WHERE c.created_at >= $1 AND c.created_at < $2
            GROUP BY ct.name
            ORDER BY count DESC
        """
        conversions_rows = await conn.fetch(conversions_query, start_date, end_date)

        # Query 3: Landing pages
        landing_query = """
            SELECT s.landing_page, COUNT(*) as sessions, COUNT(DISTINCT s.visitor_id) as unique_visitors
            FROM sessions s
            JOIN visitors v ON s.visitor_id = v.visitor_id
            WHERE s.started_at >= $1 AND s.started_at < $2
            AND v.is_bot = false
            GROUP BY s.landing_page
            ORDER BY sessions DESC
            LIMIT 10
        """
        landing_rows = await conn.fetch(landing_query, start_date, end_date)

        # Query 4: Traffic sources
        sources_query = """
            SELECT
                COALESCE(s.utm_source, 'direct') as source,
                COALESCE(s.utm_medium, 'none') as medium,
                COUNT(*) as sessions
            FROM sessions s
            JOIN visitors v ON s.visitor_id = v.visitor_id
            WHERE s.started_at >= $1 AND s.started_at < $2
            AND v.is_bot = false
            GROUP BY s.utm_source, s.utm_medium
            ORDER BY sessions DESC
            LIMIT 10
        """
        sources_rows = await conn.fetch(sources_query, start_date, end_date)

    total_sessions = stats_row["total_sessions"] if stats_row else 0
    unique_visitors = stats_row["unique_visitors"] if stats_row else 0

    print(f"[{SERVER_NAME.upper()}] Found {total_sessions} sessions, {unique_visitors} unique visitors", file=sys.stderr)

    return {
        "source": "visitor_tracking",
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        # Stats
        "total_sessions": total_sessions,
        "unique_visitors": unique_visitors,
        "utm_sessions": stats_row["utm_sessions"] if stats_row else 0,
        "gclid_sessions": stats_row["gclid_sessions"] if stats_row else 0,
        "fbclid_sessions": stats_row["fbclid_sessions"] if stats_row else 0,
        "median_session_duration": float(stats_row["median_session_duration"]) if stats_row and stats_row["median_session_duration"] else 0,
        # Conversions
        "conversions": [dict(row) for row in conversions_rows],
        # Landing pages
        "top_landing_pages": [dict(row) for row in landing_rows],
        # Traffic sources
        "traffic_sources": [dict(row) for row in sources_rows],
        # Summary for analytics
        "summary": {
            "total_sessions": total_sessions,
            "unique_visitors": unique_visitors,
            "session_per_visitor": round(total_sessions / unique_visitors, 2) if unique_visitors > 0 else 0,
            "utm_rate": round(stats_row["utm_sessions"] / total_sessions * 100, 1) if stats_row and total_sessions > 0 else 0,
            "paid_sessions": (stats_row["gclid_sessions"] if stats_row else 0) + (stats_row["fbclid_sessions"] if stats_row else 0),
        }
    }


# Tool handler mapping
TOOL_HANDLERS = {
    "get_visitor_stats": handle_get_visitor_stats,
    "get_conversions": handle_get_conversions,
    "get_top_landing_pages": handle_get_top_landing_pages,
    "get_traffic_sources": handle_get_traffic_sources,
    "get_visitor_summary": handle_get_visitor_summary,
}


# ============================================================================
# MCP SERVER HANDLERS
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    if name not in TOOL_HANDLERS:
        return [TextContent(type="text", text=f"Error: Unknown tool: {name}")]

    try:
        handler = TOOL_HANDLERS[name]
        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[{SERVER_NAME.upper()}] Error in {name}: {error_detail}", file=sys.stderr)
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """Run the MCP server"""
    print(f"[{SERVER_NAME.upper()}] Starting server v{SERVER_VERSION}", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
