#!/usr/bin/env python3
"""
Afspraak DB MCP Server v1.0
============================
MCP Server for Coolify PostgreSQL Afspraak (Appointment) Database integration with Claude Code.

Provides tools for:
- Appointment data retrieval
- Visitor tracking cross-reference (GCLID, visitor_id, session_id)
- Campaign performance tracking
- Customer data

Database: Coolify PostgreSQL (afspraak-db)
Host: lgckoswc0gwks4g4o4gogwcw (internal) / 91.98.235.81 (via SSH)

Environment Variables Required:
- AFSPRAAK_DB_HOST: Database host (default: lgckoswc0gwks4g4o4gogwcw)
- AFSPRAAK_DB_USER: Database user (default: postgres)
- AFSPRAAK_DB_PASSWORD: Database password
- AFSPRAAK_DB_NAME: Database name (default: postgres)
- AFSPRAAK_DB_PORT: Database port (default: 5432)

Version: 1.0
Last Updated: 2025-12-16
"""

import asyncio
import json
import os
from typing import Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import psycopg2
from psycopg2.extras import RealDictCursor

# Server info
SERVER_NAME = "afspraak-db"
SERVER_VERSION = "1.0.0"

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


def get_db_connection():
    """Get PostgreSQL database connection"""
    creds = load_credentials()
    # Default to Coolify afspraak-db credentials
    host = creds.get('AFSPRAAK_DB_HOST', 'lgckoswc0gwks4g4o4gogwcw')
    user = creds.get('AFSPRAAK_DB_USER', 'postgres')
    password = creds.get('AFSPRAAK_DB_PASSWORD', 'ml3ecPKeHgG06vCEkPIIqU3e5iosOJnN9K04CF9D285xmytEQaxQGT52Ri94h4HL')
    dbname = creds.get('AFSPRAAK_DB_NAME', 'postgres')
    port = creds.get('AFSPRAAK_DB_PORT', '5432')

    conn = psycopg2.connect(
        host=host,
        user=user,
        password=password,
        dbname=dbname,
        port=port,
        cursor_factory=RealDictCursor
    )
    return conn


def execute_query(query: str, params: tuple = None) -> list:
    """Execute a query and return results"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return []
    finally:
        conn.close()


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools"""
    return [
        Tool(
            name="get_appointments",
            description="Get all appointments from afspraak-db. Returns appointment details including customer info, gclid, visitor_id, session_id, and source.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back. Default: 30"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum appointments to return. Default: 100"
                    }
                }
            }
        ),
        Tool(
            name="get_appointments_with_gclid",
            description="Get appointments that have a GCLID (Google Click ID) for Google Ads attribution analysis. These are confirmed conversions from Google Ads.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back. Default: 30"
                    }
                }
            }
        ),
        Tool(
            name="get_appointments_with_fbclid",
            description="Get appointments that have a FBCLID (Facebook Click ID) for Meta Ads attribution analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back. Default: 30"
                    }
                }
            }
        ),
        Tool(
            name="get_appointment_stats",
            description="Get appointment statistics summary including counts by source, with/without tracking IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze. Default: 30"
                    }
                }
            }
        ),
        Tool(
            name="get_appointments_by_visitor",
            description="Get appointments for a specific visitor_id to cross-reference with visitor tracking system.",
            inputSchema={
                "type": "object",
                "properties": {
                    "visitor_id": {
                        "type": "string",
                        "description": "The visitor ID from visitor tracking system"
                    }
                },
                "required": ["visitor_id"]
            }
        ),
        Tool(
            name="get_appointments_by_session",
            description="Get appointments for a specific session_id to cross-reference with visitor tracking system.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "The session ID from visitor tracking system"
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_daily_appointments",
            description="Get daily appointment counts for trend analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze. Default: 30"
                    }
                }
            }
        ),
        Tool(
            name="get_appointment_sources",
            description="Get breakdown of appointments by source (pomandi_be_widget, pomandi_com, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze. Default: 30"
                    }
                }
            }
        ),
        Tool(
            name="get_utm_tracking",
            description="Get UTM tracking data to see which campaigns drove appointments.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze. Default: 30"
                    }
                }
            }
        ),
        Tool(
            name="raw_query",
            description="Execute a raw SELECT query on the afspraak database. Use for custom queries not covered by other tools.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute (SELECT only for safety)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_tables",
            description="List all tables in the afspraak-db database.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_table_schema",
            description="Get the schema/columns of a specific table.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table to inspect"
                    }
                },
                "required": ["table_name"]
            }
        )
    ]


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    try:
        if name == "get_appointments":
            result = await get_appointments(arguments)
        elif name == "get_appointments_with_gclid":
            result = await get_appointments_with_gclid(arguments)
        elif name == "get_appointments_with_fbclid":
            result = await get_appointments_with_fbclid(arguments)
        elif name == "get_appointment_stats":
            result = await get_appointment_stats(arguments)
        elif name == "get_appointments_by_visitor":
            result = await get_appointments_by_visitor(arguments)
        elif name == "get_appointments_by_session":
            result = await get_appointments_by_session(arguments)
        elif name == "get_daily_appointments":
            result = await get_daily_appointments(arguments)
        elif name == "get_appointment_sources":
            result = await get_appointment_sources(arguments)
        elif name == "get_utm_tracking":
            result = await get_utm_tracking(arguments)
        elif name == "raw_query":
            result = await raw_query(arguments)
        elif name == "get_tables":
            result = await get_tables(arguments)
        elif name == "get_table_schema":
            result = await get_table_schema(arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def get_appointments(args: dict) -> dict:
    """Get appointments with customer info"""
    days = args.get("days", 30)
    limit = args.get("limit", 100)

    query = """
        SELECT
            a.id,
            a.created_at,
            a.gclid,
            a.fbclid,
            a.visitor_id,
            a.session_id,
            a.appointment_source,
            a.source_url,
            a.conversion_value,
            a.google_ads_conversion_sent,
            a.meta_ads_conversion_sent,
            c.name as customer_name,
            c.email as customer_email,
            c.phone as customer_phone,
            s.start_time as slot_start,
            s.end_time as slot_end
        FROM appointments_appointment a
        JOIN appointments_customer c ON a.customer_id = c.id
        LEFT JOIN appointments_appointmentslot s ON a.slot_id = s.id
        WHERE a.created_at >= NOW() - INTERVAL '%s days'
        ORDER BY a.created_at DESC
        LIMIT %s
    """

    results = execute_query(query, (days, limit))

    return {
        "count": len(results),
        "days": days,
        "appointments": [dict(r) for r in results]
    }


async def get_appointments_with_gclid(args: dict) -> dict:
    """Get appointments with GCLID for Google Ads attribution"""
    days = args.get("days", 30)

    query = """
        SELECT
            a.id,
            a.created_at,
            a.gclid,
            a.visitor_id,
            a.session_id,
            a.appointment_source,
            a.source_url,
            a.google_ads_conversion_sent,
            a.google_ads_conversion_sent_at,
            c.name as customer_name,
            c.email as customer_email,
            c.phone as customer_phone
        FROM appointments_appointment a
        JOIN appointments_customer c ON a.customer_id = c.id
        WHERE a.gclid IS NOT NULL
        AND a.gclid != ''
        AND a.gclid NOT LIKE 'TEST%'
        AND a.created_at >= NOW() - INTERVAL '%s days'
        ORDER BY a.created_at DESC
    """

    results = execute_query(query, (days,))

    return {
        "count": len(results),
        "days": days,
        "description": "Real appointments with Google Ads GCLID attribution",
        "appointments": [dict(r) for r in results]
    }


async def get_appointments_with_fbclid(args: dict) -> dict:
    """Get appointments with FBCLID for Meta Ads attribution"""
    days = args.get("days", 30)

    query = """
        SELECT
            a.id,
            a.created_at,
            a.fbclid,
            a.visitor_id,
            a.session_id,
            a.appointment_source,
            a.source_url,
            a.meta_ads_conversion_sent,
            a.meta_ads_conversion_sent_at,
            c.name as customer_name,
            c.email as customer_email,
            c.phone as customer_phone
        FROM appointments_appointment a
        JOIN appointments_customer c ON a.customer_id = c.id
        WHERE a.fbclid IS NOT NULL
        AND a.fbclid != ''
        AND a.created_at >= NOW() - INTERVAL '%s days'
        ORDER BY a.created_at DESC
    """

    results = execute_query(query, (days,))

    return {
        "count": len(results),
        "days": days,
        "description": "Appointments with Meta Ads FBCLID attribution",
        "appointments": [dict(r) for r in results]
    }


async def get_appointment_stats(args: dict) -> dict:
    """Get appointment statistics"""
    days = args.get("days", 30)

    # Total count
    total_query = """
        SELECT COUNT(*) as total
        FROM appointments_appointment
        WHERE created_at >= NOW() - INTERVAL '%s days'
    """
    total = execute_query(total_query, (days,))[0]['total']

    # With GCLID
    gclid_query = """
        SELECT COUNT(*) as count
        FROM appointments_appointment
        WHERE gclid IS NOT NULL AND gclid != '' AND gclid NOT LIKE 'TEST%'
        AND created_at >= NOW() - INTERVAL '%s days'
    """
    with_gclid = execute_query(gclid_query, (days,))[0]['count']

    # With FBCLID
    fbclid_query = """
        SELECT COUNT(*) as count
        FROM appointments_appointment
        WHERE fbclid IS NOT NULL AND fbclid != ''
        AND created_at >= NOW() - INTERVAL '%s days'
    """
    with_fbclid = execute_query(fbclid_query, (days,))[0]['count']

    # With visitor_id
    visitor_query = """
        SELECT COUNT(*) as count
        FROM appointments_appointment
        WHERE visitor_id IS NOT NULL AND visitor_id != ''
        AND created_at >= NOW() - INTERVAL '%s days'
    """
    with_visitor_id = execute_query(visitor_query, (days,))[0]['count']

    # By source
    source_query = """
        SELECT appointment_source, COUNT(*) as count
        FROM appointments_appointment
        WHERE created_at >= NOW() - INTERVAL '%s days'
        GROUP BY appointment_source
        ORDER BY count DESC
    """
    by_source = execute_query(source_query, (days,))

    return {
        "days": days,
        "total_appointments": total,
        "with_gclid": with_gclid,
        "with_fbclid": with_fbclid,
        "with_visitor_id": with_visitor_id,
        "by_source": [dict(r) for r in by_source]
    }


async def get_appointments_by_visitor(args: dict) -> dict:
    """Get appointments for a specific visitor"""
    visitor_id = args.get("visitor_id")

    query = """
        SELECT
            a.id,
            a.created_at,
            a.gclid,
            a.fbclid,
            a.visitor_id,
            a.session_id,
            a.appointment_source,
            c.name as customer_name,
            c.email as customer_email
        FROM appointments_appointment a
        JOIN appointments_customer c ON a.customer_id = c.id
        WHERE a.visitor_id = %s
        ORDER BY a.created_at DESC
    """

    results = execute_query(query, (visitor_id,))

    return {
        "visitor_id": visitor_id,
        "count": len(results),
        "appointments": [dict(r) for r in results]
    }


async def get_appointments_by_session(args: dict) -> dict:
    """Get appointments for a specific session"""
    session_id = args.get("session_id")

    query = """
        SELECT
            a.id,
            a.created_at,
            a.gclid,
            a.fbclid,
            a.visitor_id,
            a.session_id,
            a.appointment_source,
            c.name as customer_name,
            c.email as customer_email
        FROM appointments_appointment a
        JOIN appointments_customer c ON a.customer_id = c.id
        WHERE a.session_id = %s
        ORDER BY a.created_at DESC
    """

    results = execute_query(query, (session_id,))

    return {
        "session_id": session_id,
        "count": len(results),
        "appointments": [dict(r) for r in results]
    }


async def get_daily_appointments(args: dict) -> dict:
    """Get daily appointment counts"""
    days = args.get("days", 30)

    query = """
        SELECT
            DATE(created_at) as date,
            COUNT(*) as total,
            COUNT(CASE WHEN gclid IS NOT NULL AND gclid != '' AND gclid NOT LIKE 'TEST%' THEN 1 END) as from_google_ads,
            COUNT(CASE WHEN fbclid IS NOT NULL AND fbclid != '' THEN 1 END) as from_meta_ads
        FROM appointments_appointment
        WHERE created_at >= NOW() - INTERVAL '%s days'
        GROUP BY DATE(created_at)
        ORDER BY date DESC
    """

    results = execute_query(query, (days,))

    return {
        "days": days,
        "daily_counts": [dict(r) for r in results]
    }


async def get_appointment_sources(args: dict) -> dict:
    """Get breakdown by appointment source"""
    days = args.get("days", 30)

    query = """
        SELECT
            appointment_source,
            COUNT(*) as count,
            COUNT(CASE WHEN gclid IS NOT NULL AND gclid != '' AND gclid NOT LIKE 'TEST%' THEN 1 END) as with_gclid,
            COUNT(CASE WHEN fbclid IS NOT NULL AND fbclid != '' THEN 1 END) as with_fbclid
        FROM appointments_appointment
        WHERE created_at >= NOW() - INTERVAL '%s days'
        GROUP BY appointment_source
        ORDER BY count DESC
    """

    results = execute_query(query, (days,))

    return {
        "days": days,
        "sources": [dict(r) for r in results]
    }


async def get_utm_tracking(args: dict) -> dict:
    """Get UTM tracking data"""
    days = args.get("days", 30)

    query = """
        SELECT
            utm_source,
            utm_medium,
            utm_campaign,
            utm_content,
            utm_term,
            COUNT(*) as count
        FROM appointments_utmtracking
        WHERE created_at >= NOW() - INTERVAL '%s days'
        GROUP BY utm_source, utm_medium, utm_campaign, utm_content, utm_term
        ORDER BY count DESC
        LIMIT 50
    """

    try:
        results = execute_query(query, (days,))
        return {
            "days": days,
            "utm_data": [dict(r) for r in results]
        }
    except Exception as e:
        return {"error": str(e), "message": "UTM tracking table might not have expected columns"}


async def raw_query(args: dict) -> dict:
    """Execute raw SELECT query"""
    query = args.get("query", "")

    # Safety check - only allow SELECT
    if not query.strip().upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed"}

    try:
        results = execute_query(query)
        return {
            "count": len(results),
            "data": [dict(r) for r in results]
        }
    except Exception as e:
        return {"error": str(e)}


async def get_tables(args: dict) -> dict:
    """List all tables"""
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """

    results = execute_query(query)

    return {
        "tables": [r['table_name'] for r in results]
    }


async def get_table_schema(args: dict) -> dict:
    """Get table schema"""
    table_name = args.get("table_name")

    query = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """

    results = execute_query(query, (table_name,))

    return {
        "table": table_name,
        "columns": [dict(r) for r in results]
    }


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Main entry point"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
