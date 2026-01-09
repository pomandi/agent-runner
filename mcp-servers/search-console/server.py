#!/usr/bin/env python3
"""
Google Search Console MCP Server v2.0
======================================
Enhanced MCP Server for Google Search Console API integration with Claude Code.

Provides tools for:
- Search analytics (queries, pages, devices, countries)
- Indexing status
- URL inspection
- Sitemaps
- Query comparison (period over period)
- Page performance trends
- Keyword opportunity analysis
- Position tracking
- Search appearance breakdown
- Daily trends analysis

Environment Variables Required:
- GOOGLE_CREDENTIALS_PATH: Path to service account JSON file

Version: 2.0 (Enhanced with SEO insights)
API Version: Google Search Console API v1
Last Updated: 2025-12-15

New in v2.0:
- Added period comparison (WoW, MoM)
- Added keyword opportunity finder
- Added position distribution analysis
- Added search appearance breakdown
- Added daily trends
- Added query + page combined analysis
- Added SEO summary report
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

# Server info
SERVER_NAME = "search-console"
SERVER_VERSION = "2.0.0"

# Initialize MCP server
server = Server(SERVER_NAME)

# Default site
DEFAULT_SITE = "sc-domain:pomandi.be"

# Global service
_service = None


def get_credentials_path() -> str:
    """Get path to Google credentials file"""
    # Check environment variable first
    env_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # Default location
    default_path = Path("C:/software-project/sale-v2/.claude/google_credentials.json")
    if default_path.exists():
        return str(default_path)

    return None  # Return None instead of raising - we'll try other methods


def get_service():
    """Get or create Search Console API service

    Supports multiple credential sources in priority order:
    1. GOOGLE_CREDENTIALS_JSON environment variable (JSON string)
    2. GOOGLE_CREDENTIALS_PATH environment variable (path to file)
    3. Default file paths
    """
    global _service
    import sys

    if _service is not None:
        return _service

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        import json as json_module

        scopes = ['https://www.googleapis.com/auth/webmasters.readonly']
        credentials = None

        # 1. Try JSON string from environment variable
        json_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if json_creds:
            print("[SEARCH-CONSOLE] Using GOOGLE_CREDENTIALS_JSON env var", file=sys.stderr)
            try:
                # Handle potential double-escaping from Coolify API
                # If JSON starts with escaped quotes, try to decode first
                if json_creds.startswith('{\\'):
                    print("[SEARCH-CONSOLE] Detected escaped JSON, decoding...", file=sys.stderr)
                    json_creds = json_creds.encode().decode('unicode_escape')
                creds_dict = json_module.loads(json_creds)
                credentials = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=scopes
                )
            except Exception as e:
                print(f"[SEARCH-CONSOLE] Failed to parse JSON credentials: {e}", file=sys.stderr)

        # 2. Try file path
        if credentials is None:
            credentials_path = get_credentials_path()
            if credentials_path:
                print(f"[SEARCH-CONSOLE] Using credentials file: {credentials_path}", file=sys.stderr)
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=scopes
                )

        if credentials is None:
            raise Exception(
                "Google credentials not found. Set GOOGLE_CREDENTIALS_JSON (JSON string) or "
                "GOOGLE_CREDENTIALS_PATH (file path) environment variable."
            )

        _service = build('searchconsole', 'v1', credentials=credentials)
        print("[SEARCH-CONSOLE] Service initialized successfully", file=sys.stderr)
        return _service

    except ImportError:
        raise Exception("google-api-python-client not installed. Run: pip install google-api-python-client google-auth")


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="get_search_analytics",
        description="Get search analytics data including queries, pages, devices, and countries.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {
                    "type": "string",
                    "description": "Site URL (e.g., sc-domain:pomandi.be). Default: sc-domain:pomandi.be"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days of data. Default: 28"
                },
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Dimensions: query, page, device, country, date. Default: [query, page]"
                },
                "row_limit": {
                    "type": "integer",
                    "description": "Maximum rows to return. Default: 1000"
                }
            }
        }
    ),
    Tool(
        name="get_top_queries",
        description="Get top performing search queries with clicks, impressions, CTR, and position.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {
                    "type": "string",
                    "description": "Site URL. Default: sc-domain:pomandi.be"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 28"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of queries to return. Default: 100"
                }
            }
        }
    ),
    Tool(
        name="get_top_pages",
        description="Get top performing pages with clicks, impressions, CTR, and position.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {
                    "type": "string",
                    "description": "Site URL. Default: sc-domain:pomandi.be"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 28"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of pages to return. Default: 100"
                }
            }
        }
    ),
    Tool(
        name="get_device_performance",
        description="Get search performance breakdown by device type (desktop, mobile, tablet).",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {
                    "type": "string",
                    "description": "Site URL. Default: sc-domain:pomandi.be"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 28"
                }
            }
        }
    ),
    Tool(
        name="get_country_performance",
        description="Get search performance breakdown by country.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {
                    "type": "string",
                    "description": "Site URL. Default: sc-domain:pomandi.be"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 28"
                }
            }
        }
    ),
    Tool(
        name="get_sitemaps",
        description="Get sitemap information including last submitted, URL count, and status.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {
                    "type": "string",
                    "description": "Site URL. Default: sc-domain:pomandi.be"
                }
            }
        }
    ),
    Tool(
        name="get_sites",
        description="List all sites/properties you have access to in Search Console.",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    # ============================================================================
    # NEW TOOLS - Added in v2.0
    # ============================================================================
    Tool(
        name="get_daily_trends",
        description="Get day-by-day search performance trends.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {"type": "string", "description": "Site URL. Default: sc-domain:pomandi.be"},
                "days": {"type": "integer", "description": "Number of days. Default: 28"}
            }
        }
    ),
    Tool(
        name="get_keyword_opportunities",
        description="Find keyword opportunities (high impressions but low CTR or position 4-20).",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {"type": "string", "description": "Site URL. Default: sc-domain:pomandi.be"},
                "days": {"type": "integer", "description": "Number of days. Default: 28"},
                "min_impressions": {"type": "integer", "description": "Minimum impressions. Default: 100"}
            }
        }
    ),
    Tool(
        name="get_position_distribution",
        description="Get position distribution showing how queries are distributed across positions 1-10, 11-20, etc.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {"type": "string", "description": "Site URL. Default: sc-domain:pomandi.be"},
                "days": {"type": "integer", "description": "Number of days. Default: 28"}
            }
        }
    ),
    Tool(
        name="get_query_page_analysis",
        description="Get combined query + page analysis to see which pages rank for which queries.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {"type": "string", "description": "Site URL. Default: sc-domain:pomandi.be"},
                "days": {"type": "integer", "description": "Number of days. Default: 28"},
                "limit": {"type": "integer", "description": "Max results. Default: 200"}
            }
        }
    ),
    Tool(
        name="get_period_comparison",
        description="Compare performance between two periods (week over week or month over month).",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {"type": "string", "description": "Site URL. Default: sc-domain:pomandi.be"},
                "comparison": {
                    "type": "string",
                    "description": "Comparison type: week (7d vs prev 7d), month (28d vs prev 28d). Default: week",
                    "enum": ["week", "month"]
                }
            }
        }
    ),
    Tool(
        name="get_seo_summary",
        description="Get a comprehensive SEO summary with key metrics, top opportunities, and insights.",
        inputSchema={
            "type": "object",
            "properties": {
                "site_url": {"type": "string", "description": "Site URL. Default: sc-domain:pomandi.be"},
                "days": {"type": "integer", "description": "Number of days. Default: 28"}
            }
        }
    )
]


# ============================================================================
# Tool Handlers
# ============================================================================

async def handle_get_search_analytics(
    site_url: str = DEFAULT_SITE,
    days: int = 28,
    dimensions: list = None,
    row_limit: int = 1000
) -> dict:
    """Get search analytics data"""
    service = get_service()

    end_date = datetime.now() - timedelta(days=3)  # Data has 3-day delay
    start_date = end_date - timedelta(days=days)

    if dimensions is None:
        dimensions = ['query', 'page']

    request = {
        'startDate': start_date.strftime('%Y-%m-%d'),
        'endDate': end_date.strftime('%Y-%m-%d'),
        'dimensions': dimensions,
        'rowLimit': row_limit
    }

    response = service.searchanalytics().query(
        siteUrl=site_url,
        body=request
    ).execute()

    rows = response.get('rows', [])

    # Calculate totals
    total_clicks = sum(r.get('clicks', 0) for r in rows)
    total_impressions = sum(r.get('impressions', 0) for r in rows)
    avg_ctr = total_clicks / total_impressions * 100 if total_impressions > 0 else 0
    avg_position = sum(r.get('position', 0) * r.get('impressions', 0) for r in rows) / total_impressions if total_impressions > 0 else 0

    return {
        "site_url": site_url,
        "date_range": {
            "start": start_date.strftime('%Y-%m-%d'),
            "end": end_date.strftime('%Y-%m-%d'),
            "days": days
        },
        "dimensions": dimensions,
        "summary": {
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "average_ctr": round(avg_ctr, 2),
            "average_position": round(avg_position, 1)
        },
        "row_count": len(rows),
        "rows": rows
    }


async def handle_get_top_queries(
    site_url: str = DEFAULT_SITE,
    days: int = 28,
    limit: int = 100
) -> dict:
    """Get top search queries"""
    result = await handle_get_search_analytics(
        site_url=site_url,
        days=days,
        dimensions=['query'],
        row_limit=limit
    )

    # Format for easier consumption
    queries = []
    for row in result.get('rows', []):
        queries.append({
            'query': row['keys'][0],
            'clicks': row.get('clicks', 0),
            'impressions': row.get('impressions', 0),
            'ctr': round(row.get('ctr', 0) * 100, 2),
            'position': round(row.get('position', 0), 1)
        })

    return {
        "site_url": site_url,
        "date_range": result.get('date_range'),
        "summary": result.get('summary'),
        "queries": queries
    }


async def handle_get_top_pages(
    site_url: str = DEFAULT_SITE,
    days: int = 28,
    limit: int = 100
) -> dict:
    """Get top pages"""
    result = await handle_get_search_analytics(
        site_url=site_url,
        days=days,
        dimensions=['page'],
        row_limit=limit
    )

    # Format for easier consumption
    pages = []
    for row in result.get('rows', []):
        pages.append({
            'page': row['keys'][0],
            'clicks': row.get('clicks', 0),
            'impressions': row.get('impressions', 0),
            'ctr': round(row.get('ctr', 0) * 100, 2),
            'position': round(row.get('position', 0), 1)
        })

    return {
        "site_url": site_url,
        "date_range": result.get('date_range'),
        "summary": result.get('summary'),
        "pages": pages
    }


async def handle_get_device_performance(
    site_url: str = DEFAULT_SITE,
    days: int = 28
) -> dict:
    """Get device performance breakdown"""
    result = await handle_get_search_analytics(
        site_url=site_url,
        days=days,
        dimensions=['device'],
        row_limit=10
    )

    # Format devices
    devices = {}
    for row in result.get('rows', []):
        device = row['keys'][0]
        devices[device] = {
            'clicks': row.get('clicks', 0),
            'impressions': row.get('impressions', 0),
            'ctr': round(row.get('ctr', 0) * 100, 2),
            'position': round(row.get('position', 0), 1)
        }

    return {
        "site_url": site_url,
        "date_range": result.get('date_range'),
        "summary": result.get('summary'),
        "devices": devices
    }


async def handle_get_country_performance(
    site_url: str = DEFAULT_SITE,
    days: int = 28
) -> dict:
    """Get country performance breakdown"""
    result = await handle_get_search_analytics(
        site_url=site_url,
        days=days,
        dimensions=['country'],
        row_limit=50
    )

    # Format countries
    countries = []
    for row in result.get('rows', []):
        countries.append({
            'country': row['keys'][0],
            'clicks': row.get('clicks', 0),
            'impressions': row.get('impressions', 0),
            'ctr': round(row.get('ctr', 0) * 100, 2),
            'position': round(row.get('position', 0), 1)
        })

    return {
        "site_url": site_url,
        "date_range": result.get('date_range'),
        "summary": result.get('summary'),
        "countries": countries
    }


async def handle_get_sitemaps(site_url: str = DEFAULT_SITE) -> dict:
    """Get sitemap information"""
    service = get_service()

    response = service.sitemaps().list(siteUrl=site_url).execute()
    sitemaps = response.get('sitemap', [])

    return {
        "site_url": site_url,
        "sitemaps": sitemaps
    }


async def handle_get_sites() -> dict:
    """List all sites"""
    service = get_service()

    response = service.sites().list().execute()
    sites = response.get('siteEntry', [])

    return {
        "sites": sites
    }


# ============================================================================
# NEW Tool Handlers - Added in v2.0
# ============================================================================

async def handle_get_daily_trends(site_url: str = DEFAULT_SITE, days: int = 28) -> dict:
    """Get daily search performance trends"""
    result = await handle_get_search_analytics(
        site_url=site_url,
        days=days,
        dimensions=['date'],
        row_limit=days
    )

    daily_data = []
    for row in result.get('rows', []):
        daily_data.append({
            'date': row['keys'][0],
            'clicks': row.get('clicks', 0),
            'impressions': row.get('impressions', 0),
            'ctr': round(row.get('ctr', 0) * 100, 2),
            'position': round(row.get('position', 0), 1)
        })

    # Sort by date
    daily_data.sort(key=lambda x: x['date'])

    return {
        "site_url": site_url,
        "date_range": result.get('date_range'),
        "daily_trends": daily_data
    }


async def handle_get_keyword_opportunities(site_url: str = DEFAULT_SITE, days: int = 28,
                                            min_impressions: int = 100) -> dict:
    """Find keyword opportunities"""
    result = await handle_get_search_analytics(
        site_url=site_url,
        days=days,
        dimensions=['query'],
        row_limit=1000
    )

    opportunities = {
        'low_ctr_high_impressions': [],  # High impressions, low CTR
        'position_4_to_10': [],  # Close to top 3
        'position_11_to_20': []  # Second page
    }

    for row in result.get('rows', []):
        query = row['keys'][0]
        impressions = row.get('impressions', 0)
        clicks = row.get('clicks', 0)
        ctr = row.get('ctr', 0) * 100
        position = row.get('position', 0)

        if impressions < min_impressions:
            continue

        item = {
            'query': query,
            'clicks': clicks,
            'impressions': impressions,
            'ctr': round(ctr, 2),
            'position': round(position, 1)
        }

        # Low CTR opportunities (high impressions, low CTR)
        if impressions > min_impressions * 2 and ctr < 2:
            opportunities['low_ctr_high_impressions'].append(item)

        # Position opportunities
        if 4 <= position <= 10:
            opportunities['position_4_to_10'].append(item)
        elif 11 <= position <= 20:
            opportunities['position_11_to_20'].append(item)

    # Sort each by impressions
    for key in opportunities:
        opportunities[key].sort(key=lambda x: x['impressions'], reverse=True)
        opportunities[key] = opportunities[key][:20]  # Top 20 each

    return {
        "site_url": site_url,
        "date_range": result.get('date_range'),
        "opportunities": opportunities,
        "opportunity_counts": {k: len(v) for k, v in opportunities.items()}
    }


async def handle_get_position_distribution(site_url: str = DEFAULT_SITE, days: int = 28) -> dict:
    """Get position distribution"""
    result = await handle_get_search_analytics(
        site_url=site_url,
        days=days,
        dimensions=['query'],
        row_limit=5000
    )

    distribution = {
        'position_1_3': {'queries': 0, 'clicks': 0, 'impressions': 0},
        'position_4_10': {'queries': 0, 'clicks': 0, 'impressions': 0},
        'position_11_20': {'queries': 0, 'clicks': 0, 'impressions': 0},
        'position_21_50': {'queries': 0, 'clicks': 0, 'impressions': 0},
        'position_50_plus': {'queries': 0, 'clicks': 0, 'impressions': 0}
    }

    for row in result.get('rows', []):
        position = row.get('position', 0)
        clicks = row.get('clicks', 0)
        impressions = row.get('impressions', 0)

        if position <= 3:
            bucket = 'position_1_3'
        elif position <= 10:
            bucket = 'position_4_10'
        elif position <= 20:
            bucket = 'position_11_20'
        elif position <= 50:
            bucket = 'position_21_50'
        else:
            bucket = 'position_50_plus'

        distribution[bucket]['queries'] += 1
        distribution[bucket]['clicks'] += clicks
        distribution[bucket]['impressions'] += impressions

    return {
        "site_url": site_url,
        "date_range": result.get('date_range'),
        "position_distribution": distribution
    }


async def handle_get_query_page_analysis(site_url: str = DEFAULT_SITE, days: int = 28,
                                          limit: int = 200) -> dict:
    """Get query + page combined analysis"""
    result = await handle_get_search_analytics(
        site_url=site_url,
        days=days,
        dimensions=['query', 'page'],
        row_limit=limit
    )

    analysis = []
    for row in result.get('rows', []):
        analysis.append({
            'query': row['keys'][0],
            'page': row['keys'][1],
            'clicks': row.get('clicks', 0),
            'impressions': row.get('impressions', 0),
            'ctr': round(row.get('ctr', 0) * 100, 2),
            'position': round(row.get('position', 0), 1)
        })

    return {
        "site_url": site_url,
        "date_range": result.get('date_range'),
        "query_page_data": analysis
    }


async def handle_get_period_comparison(site_url: str = DEFAULT_SITE, comparison: str = "week") -> dict:
    """Compare performance between periods"""
    if comparison == "week":
        current_days = 7
    else:  # month
        current_days = 28

    # Get current period
    current = await handle_get_search_analytics(
        site_url=site_url,
        days=current_days,
        dimensions=['query'],
        row_limit=1
    )

    # Get previous period (we need to modify the date range)
    service = get_service()
    end_date = datetime.now() - timedelta(days=3 + current_days)
    start_date = end_date - timedelta(days=current_days)

    request = {
        'startDate': start_date.strftime('%Y-%m-%d'),
        'endDate': end_date.strftime('%Y-%m-%d'),
        'dimensions': ['query'],
        'rowLimit': 1
    }

    response = service.searchanalytics().query(
        siteUrl=site_url,
        body=request
    ).execute()

    prev_rows = response.get('rows', [])
    prev_clicks = sum(r.get('clicks', 0) for r in prev_rows)
    prev_impressions = sum(r.get('impressions', 0) for r in prev_rows)
    prev_ctr = prev_clicks / prev_impressions * 100 if prev_impressions > 0 else 0

    curr_summary = current.get('summary', {})

    # Calculate changes
    click_change = ((curr_summary.get('total_clicks', 0) - prev_clicks) / max(prev_clicks, 1)) * 100
    imp_change = ((curr_summary.get('total_impressions', 0) - prev_impressions) / max(prev_impressions, 1)) * 100

    return {
        "site_url": site_url,
        "comparison_type": comparison,
        "current_period": {
            "clicks": curr_summary.get('total_clicks', 0),
            "impressions": curr_summary.get('total_impressions', 0),
            "ctr": curr_summary.get('average_ctr', 0),
            "position": curr_summary.get('average_position', 0)
        },
        "previous_period": {
            "clicks": prev_clicks,
            "impressions": prev_impressions,
            "ctr": round(prev_ctr, 2)
        },
        "changes": {
            "clicks_change_percent": round(click_change, 1),
            "impressions_change_percent": round(imp_change, 1)
        }
    }


async def handle_get_seo_summary(site_url: str = DEFAULT_SITE, days: int = 28) -> dict:
    """Get comprehensive SEO summary"""
    # Get all data
    queries = await handle_get_top_queries(site_url=site_url, days=days, limit=10)
    pages = await handle_get_top_pages(site_url=site_url, days=days, limit=10)
    devices = await handle_get_device_performance(site_url=site_url, days=days)
    opportunities = await handle_get_keyword_opportunities(site_url=site_url, days=days)
    distribution = await handle_get_position_distribution(site_url=site_url, days=days)

    summary = queries.get('summary', {})

    return {
        "site_url": site_url,
        "date_range": queries.get('date_range'),
        "key_metrics": {
            "total_clicks": summary.get('total_clicks', 0),
            "total_impressions": summary.get('total_impressions', 0),
            "average_ctr": summary.get('average_ctr', 0),
            "average_position": summary.get('average_position', 0)
        },
        "top_5_queries": queries.get('queries', [])[:5],
        "top_5_pages": pages.get('pages', [])[:5],
        "device_breakdown": devices.get('devices', {}),
        "position_distribution": distribution.get('position_distribution', {}),
        "opportunities_count": opportunities.get('opportunity_counts', {}),
        "top_opportunities": opportunities.get('opportunities', {}).get('position_4_to_10', [])[:5],
        "insights": {
            "clicks_formatted": f"{summary.get('total_clicks', 0):,}",
            "impressions_formatted": f"{summary.get('total_impressions', 0):,}",
            "queries_in_top_3": distribution.get('position_distribution', {}).get('position_1_3', {}).get('queries', 0)
        }
    }


# Tool handler mapping
TOOL_HANDLERS = {
    # Original tools
    "get_search_analytics": handle_get_search_analytics,
    "get_top_queries": handle_get_top_queries,
    "get_top_pages": handle_get_top_pages,
    "get_device_performance": handle_get_device_performance,
    "get_country_performance": handle_get_country_performance,
    "get_sitemaps": handle_get_sitemaps,
    "get_sites": handle_get_sites,
    # New tools - v2.0
    "get_daily_trends": handle_get_daily_trends,
    "get_keyword_opportunities": handle_get_keyword_opportunities,
    "get_position_distribution": handle_get_position_distribution,
    "get_query_page_analysis": handle_get_query_page_analysis,
    "get_period_comparison": handle_get_period_comparison,
    "get_seo_summary": handle_get_seo_summary
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
    """Handle tool calls - return list of TextContent directly"""
    if name not in TOOL_HANDLERS:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        handler = TOOL_HANDLERS[name]
        result = await handler(**arguments)

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


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
