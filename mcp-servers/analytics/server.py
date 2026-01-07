#!/usr/bin/env python3
"""
Google Analytics 4 MCP Server v2.0
===================================
Enhanced MCP Server for Google Analytics 4 (GA4) API integration with Claude Code.

Provides tools for:
- Report data (traffic, users, conversions)
- Real-time data with detailed breakdowns
- Dimension and metric exploration
- Account/property information
- User journey and funnel analysis
- E-commerce metrics
- Engagement and retention analysis
- Custom event tracking
- UTM campaign performance
- Landing page analysis
- User acquisition breakdown
- Cohort analysis

Environment Variables Required:
- GOOGLE_CREDENTIALS_PATH: Path to service account JSON file
- GA4_PROPERTY_ID: GA4 Property ID (e.g., 123456789)

Version: 2.0 (Enhanced with additional insights)
API Version: Google Analytics Data API v1beta
Last Updated: 2025-12-15

New in v2.0:
- Added user journey analysis
- Added e-commerce metrics
- Added engagement depth analysis
- Added UTM campaign tracking
- Added landing page performance
- Added browser/OS breakdown
- Added city-level geo data
- Added custom event analysis
- Added session quality metrics
- Added account summary
"""

import asyncio
import json
import os
from typing import Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Server info
SERVER_NAME = "analytics"
SERVER_VERSION = "2.0.0"

# Initialize MCP server
server = Server(SERVER_NAME)

# Global clients
_data_client = None
_admin_client = None


def get_credentials_path() -> str:
    """Get path to Google credentials file"""
    env_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    default_path = Path("C:/software-project/sale-v2/.claude/google_credentials.json")
    if default_path.exists():
        return str(default_path)

    raise Exception("Google credentials file not found. Set GOOGLE_CREDENTIALS_PATH environment variable.")


def get_property_id() -> str:
    """Get GA4 Property ID"""
    prop_id = os.getenv("GA4_PROPERTY_ID")
    if prop_id:
        return prop_id

    # Try to load from .env
    env_file = Path.home() / '.claude' / '.env'
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('GA4_PROPERTY_ID='):
                    return line.strip().split('=', 1)[1].strip('"').strip("'")

    raise Exception("GA4_PROPERTY_ID not found. Set environment variable or add to ~/.claude/.env")


def get_data_client():
    """Get or create GA4 Data API client"""
    global _data_client

    if _data_client is not None:
        return _data_client

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.oauth2 import service_account

        credentials_path = get_credentials_path()
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/analytics.readonly']
        )

        _data_client = BetaAnalyticsDataClient(credentials=credentials)
        return _data_client

    except ImportError:
        raise Exception("google-analytics-data not installed. Run: pip install google-analytics-data")


def get_admin_client():
    """Get or create GA4 Admin API client"""
    global _admin_client

    if _admin_client is not None:
        return _admin_client

    try:
        from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
        from google.oauth2 import service_account

        credentials_path = get_credentials_path()
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/analytics.readonly']
        )

        _admin_client = AnalyticsAdminServiceClient(credentials=credentials)
        return _admin_client

    except ImportError:
        raise Exception("google-analytics-admin not installed. Run: pip install google-analytics-admin")


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="run_report",
        description="Run a GA4 report with custom dimensions and metrics. Returns session/user data for analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID. If not provided, uses GA4_PROPERTY_ID env var."
                },
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Dimensions to include (e.g., date, sessionSource, country). Default: [date]"
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Metrics to include (e.g., sessions, activeUsers). Default: [sessions, activeUsers]"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days of data. Default: 30"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return. Default: 10000"
                }
            }
        }
    ),
    Tool(
        name="get_traffic_overview",
        description="Get traffic overview including sessions, users, pageviews, and engagement metrics.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 30"
                }
            }
        }
    ),
    Tool(
        name="get_traffic_sources",
        description="Get traffic source breakdown showing where visitors come from.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 30"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum sources to return. Default: 50"
                }
            }
        }
    ),
    Tool(
        name="get_top_pages",
        description="Get top performing pages by pageviews and engagement.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 30"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum pages to return. Default: 50"
                }
            }
        }
    ),
    Tool(
        name="get_device_breakdown",
        description="Get traffic breakdown by device category (desktop, mobile, tablet).",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 30"
                }
            }
        }
    ),
    Tool(
        name="get_country_breakdown",
        description="Get traffic breakdown by country.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 30"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum countries to return. Default: 20"
                }
            }
        }
    ),
    Tool(
        name="get_realtime_data",
        description="Get real-time analytics data showing current active users.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID"
                }
            }
        }
    ),
    Tool(
        name="get_conversions",
        description="Get conversion event data.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days. Default: 30"
                }
            }
        }
    ),
    Tool(
        name="get_property_info",
        description="Get GA4 property information including name, currency, and timezone.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {
                    "type": "string",
                    "description": "GA4 property ID"
                }
            }
        }
    ),
    # ============================================================================
    # NEW TOOLS - Added in v2.0
    # ============================================================================
    Tool(
        name="get_utm_campaigns",
        description="Get UTM campaign performance with source, medium, and campaign breakdown.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"},
                "limit": {"type": "integer", "description": "Max campaigns. Default: 50"}
            }
        }
    ),
    Tool(
        name="get_landing_pages",
        description="Get landing page performance with entry metrics and bounce rates.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"},
                "limit": {"type": "integer", "description": "Max pages. Default: 50"}
            }
        }
    ),
    Tool(
        name="get_user_acquisition",
        description="Get new user acquisition breakdown by channel and first user source.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"},
                "limit": {"type": "integer", "description": "Max sources. Default: 30"}
            }
        }
    ),
    Tool(
        name="get_engagement_metrics",
        description="Get engagement metrics including scroll depth, time on page, and events per session.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"}
            }
        }
    ),
    Tool(
        name="get_browser_breakdown",
        description="Get traffic breakdown by browser and operating system.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"},
                "limit": {"type": "integer", "description": "Max browsers. Default: 20"}
            }
        }
    ),
    Tool(
        name="get_city_breakdown",
        description="Get traffic breakdown by city for detailed geographic analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"},
                "limit": {"type": "integer", "description": "Max cities. Default: 50"},
                "country_filter": {"type": "string", "description": "Optional: Filter by country code (e.g., BE, NL)"}
            }
        }
    ),
    Tool(
        name="get_ecommerce_overview",
        description="Get e-commerce metrics including purchases, revenue, and cart activity.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"}
            }
        }
    ),
    Tool(
        name="get_all_events",
        description="Get all tracked events with counts and user engagement.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"},
                "limit": {"type": "integer", "description": "Max events. Default: 100"}
            }
        }
    ),
    Tool(
        name="get_hourly_traffic",
        description="Get traffic breakdown by hour of day to identify peak times.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 7"}
            }
        }
    ),
    Tool(
        name="get_account_summary",
        description="Get a comprehensive account summary with key metrics and insights.",
        inputSchema={
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "GA4 property ID"},
                "days": {"type": "integer", "description": "Number of days. Default: 30"}
            }
        }
    )
]


# ============================================================================
# Helper Functions
# ============================================================================

def format_report_response(response) -> dict:
    """Format GA4 report response to dict"""
    rows = []

    for row in response.rows:
        row_data = {}

        # Add dimensions
        for i, dim_value in enumerate(row.dimension_values):
            dim_name = response.dimension_headers[i].name
            row_data[dim_name] = dim_value.value

        # Add metrics
        for i, metric_value in enumerate(row.metric_values):
            metric_name = response.metric_headers[i].name
            row_data[metric_name] = metric_value.value

        rows.append(row_data)

    return {
        "row_count": response.row_count,
        "rows": rows
    }


# ============================================================================
# Tool Handlers
# ============================================================================

async def handle_run_report(
    property_id: str = None,
    dimensions: List[str] = None,
    metrics: List[str] = None,
    days: int = 30,
    limit: int = 10000
) -> dict:
    """Run a custom GA4 report"""
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric
    )

    client = get_data_client()
    prop_id = property_id or get_property_id()

    if dimensions is None:
        dimensions = ['date']
    if metrics is None:
        metrics = ['sessions', 'activeUsers']

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    request = RunReportRequest(
        property=f"properties/{prop_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )],
        limit=limit
    )

    response = client.run_report(request)

    result = format_report_response(response)
    result['property_id'] = prop_id
    result['date_range'] = {
        'start': start_date.strftime('%Y-%m-%d'),
        'end': end_date.strftime('%Y-%m-%d'),
        'days': days
    }
    result['dimensions'] = dimensions
    result['metrics'] = metrics

    return result


async def handle_get_traffic_overview(property_id: str = None, days: int = 30) -> dict:
    """Get traffic overview"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['date'],
        metrics=[
            'sessions', 'activeUsers', 'newUsers', 'screenPageViews',
            'averageSessionDuration', 'engagedSessions', 'bounceRate'
        ],
        days=days
    )

    # Calculate totals
    rows = result.get('rows', [])
    totals = {
        'sessions': sum(int(r.get('sessions', 0)) for r in rows),
        'activeUsers': sum(int(r.get('activeUsers', 0)) for r in rows),
        'newUsers': sum(int(r.get('newUsers', 0)) for r in rows),
        'pageviews': sum(int(r.get('screenPageViews', 0)) for r in rows)
    }

    # Calculate averages
    if len(rows) > 0:
        totals['avgSessionDuration'] = sum(float(r.get('averageSessionDuration', 0)) for r in rows) / len(rows)
        totals['avgBounceRate'] = sum(float(r.get('bounceRate', 0)) for r in rows) / len(rows)

    result['summary'] = totals
    return result


async def handle_get_traffic_sources(property_id: str = None, days: int = 30, limit: int = 50) -> dict:
    """Get traffic sources breakdown"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['sessionSource', 'sessionMedium'],
        metrics=['sessions', 'activeUsers', 'engagedSessions', 'bounceRate'],
        days=days,
        limit=limit
    )

    # Format for easier consumption
    sources = []
    for row in result.get('rows', []):
        sources.append({
            'source': row.get('sessionSource', '(direct)'),
            'medium': row.get('sessionMedium', '(none)'),
            'sessions': int(row.get('sessions', 0)),
            'users': int(row.get('activeUsers', 0)),
            'engaged_sessions': int(row.get('engagedSessions', 0)),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2)
        })

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'sources': sources
    }


async def handle_get_top_pages(property_id: str = None, days: int = 30, limit: int = 50) -> dict:
    """Get top pages"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['pagePath'],
        metrics=['screenPageViews', 'activeUsers', 'averageSessionDuration', 'bounceRate'],
        days=days,
        limit=limit
    )

    # Format for easier consumption
    pages = []
    for row in result.get('rows', []):
        pages.append({
            'page': row.get('pagePath', '/'),
            'pageviews': int(row.get('screenPageViews', 0)),
            'users': int(row.get('activeUsers', 0)),
            'avg_duration': round(float(row.get('averageSessionDuration', 0)), 1),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2)
        })

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'pages': pages
    }


async def handle_get_device_breakdown(property_id: str = None, days: int = 30) -> dict:
    """Get device breakdown"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['deviceCategory'],
        metrics=['sessions', 'activeUsers', 'bounceRate', 'averageSessionDuration'],
        days=days,
        limit=10
    )

    # Format devices
    devices = {}
    for row in result.get('rows', []):
        device = row.get('deviceCategory', 'unknown')
        devices[device] = {
            'sessions': int(row.get('sessions', 0)),
            'users': int(row.get('activeUsers', 0)),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2),
            'avg_duration': round(float(row.get('averageSessionDuration', 0)), 1)
        }

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'devices': devices
    }


async def handle_get_country_breakdown(property_id: str = None, days: int = 30, limit: int = 20) -> dict:
    """Get country breakdown"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['country'],
        metrics=['sessions', 'activeUsers', 'bounceRate'],
        days=days,
        limit=limit
    )

    # Format countries
    countries = []
    for row in result.get('rows', []):
        countries.append({
            'country': row.get('country', 'Unknown'),
            'sessions': int(row.get('sessions', 0)),
            'users': int(row.get('activeUsers', 0)),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2)
        })

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'countries': countries
    }


async def handle_get_realtime_data(property_id: str = None) -> dict:
    """Get real-time data"""
    from google.analytics.data_v1beta.types import (
        RunRealtimeReportRequest, Dimension, Metric
    )

    client = get_data_client()
    prop_id = property_id or get_property_id()

    request = RunRealtimeReportRequest(
        property=f"properties/{prop_id}",
        dimensions=[
            Dimension(name='country'),
            Dimension(name='deviceCategory')
        ],
        metrics=[Metric(name='activeUsers')]
    )

    response = client.run_realtime_report(request)
    result = format_report_response(response)
    result['property_id'] = prop_id
    result['timestamp'] = datetime.now().isoformat()

    # Calculate total active users
    total_active = sum(int(r.get('activeUsers', 0)) for r in result.get('rows', []))
    result['total_active_users'] = total_active

    return result


async def handle_get_conversions(property_id: str = None, days: int = 30) -> dict:
    """Get conversion events"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['eventName'],
        metrics=['eventCount', 'totalUsers', 'eventValue'],
        days=days,
        limit=100
    )

    # Filter for likely conversion events
    events = []
    for row in result.get('rows', []):
        event_name = row.get('eventName', '')
        # Include common conversion event patterns
        if any(x in event_name.lower() for x in ['purchase', 'sign_up', 'lead', 'conversion', 'submit', 'complete', 'book']):
            events.append({
                'event': event_name,
                'count': int(row.get('eventCount', 0)),
                'users': int(row.get('totalUsers', 0)),
                'value': float(row.get('eventValue', 0))
            })

    # If no conversion events found, show all events
    if not events:
        events = [
            {
                'event': row.get('eventName', ''),
                'count': int(row.get('eventCount', 0)),
                'users': int(row.get('totalUsers', 0)),
                'value': float(row.get('eventValue', 0))
            }
            for row in result.get('rows', [])
        ]

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'events': events
    }


async def handle_get_property_info(property_id: str = None) -> dict:
    """Get property information"""
    client = get_admin_client()
    prop_id = property_id or get_property_id()

    property_name = f"properties/{prop_id}"
    property_info = client.get_property(name=property_name)

    return {
        "property": {
            "name": property_info.name,
            "display_name": property_info.display_name,
            "industry_category": str(property_info.industry_category),
            "time_zone": property_info.time_zone,
            "currency_code": property_info.currency_code,
            "create_time": property_info.create_time.isoformat() if property_info.create_time else None
        }
    }


# ============================================================================
# NEW Tool Handlers - Added in v2.0
# ============================================================================

async def handle_get_utm_campaigns(property_id: str = None, days: int = 30, limit: int = 50) -> dict:
    """Get UTM campaign performance"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['sessionCampaignName', 'sessionSource', 'sessionMedium'],
        metrics=['sessions', 'activeUsers', 'newUsers', 'engagedSessions', 'bounceRate', 'averageSessionDuration'],
        days=days,
        limit=limit
    )

    campaigns = []
    for row in result.get('rows', []):
        campaign = row.get('sessionCampaignName', '(not set)')
        if campaign and campaign != '(not set)':
            campaigns.append({
                'campaign': campaign,
                'source': row.get('sessionSource', '(direct)'),
                'medium': row.get('sessionMedium', '(none)'),
                'sessions': int(row.get('sessions', 0)),
                'users': int(row.get('activeUsers', 0)),
                'new_users': int(row.get('newUsers', 0)),
                'engaged_sessions': int(row.get('engagedSessions', 0)),
                'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2),
                'avg_duration': round(float(row.get('averageSessionDuration', 0)), 1)
            })

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'campaigns': campaigns
    }


async def handle_get_landing_pages(property_id: str = None, days: int = 30, limit: int = 50) -> dict:
    """Get landing page performance"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['landingPage'],
        metrics=['sessions', 'activeUsers', 'bounceRate', 'averageSessionDuration', 'engagedSessions', 'screenPageViews'],
        days=days,
        limit=limit
    )

    pages = []
    for row in result.get('rows', []):
        pages.append({
            'landing_page': row.get('landingPage', '/'),
            'sessions': int(row.get('sessions', 0)),
            'users': int(row.get('activeUsers', 0)),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2),
            'avg_duration': round(float(row.get('averageSessionDuration', 0)), 1),
            'engaged_sessions': int(row.get('engagedSessions', 0)),
            'pageviews': int(row.get('screenPageViews', 0))
        })

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'landing_pages': pages
    }


async def handle_get_user_acquisition(property_id: str = None, days: int = 30, limit: int = 30) -> dict:
    """Get new user acquisition breakdown"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['firstUserSource', 'firstUserMedium', 'firstUserCampaignName'],
        metrics=['newUsers', 'activeUsers', 'engagedSessions'],
        days=days,
        limit=limit
    )

    sources = []
    for row in result.get('rows', []):
        sources.append({
            'source': row.get('firstUserSource', '(direct)'),
            'medium': row.get('firstUserMedium', '(none)'),
            'campaign': row.get('firstUserCampaignName', '(not set)'),
            'new_users': int(row.get('newUsers', 0)),
            'total_users': int(row.get('activeUsers', 0)),
            'engaged_sessions': int(row.get('engagedSessions', 0))
        })

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'acquisition_sources': sources
    }


async def handle_get_engagement_metrics(property_id: str = None, days: int = 30) -> dict:
    """Get engagement metrics"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['date'],
        metrics=[
            'sessions', 'engagedSessions', 'engagementRate',
            'averageSessionDuration', 'screenPageViewsPerSession',
            'eventCount', 'userEngagementDuration'
        ],
        days=days
    )

    rows = result.get('rows', [])

    # Calculate averages
    totals = {
        'sessions': sum(int(r.get('sessions', 0)) for r in rows),
        'engaged_sessions': sum(int(r.get('engagedSessions', 0)) for r in rows),
        'total_events': sum(int(r.get('eventCount', 0)) for r in rows)
    }

    if len(rows) > 0:
        totals['avg_engagement_rate'] = round(sum(float(r.get('engagementRate', 0)) for r in rows) / len(rows) * 100, 2)
        totals['avg_session_duration'] = round(sum(float(r.get('averageSessionDuration', 0)) for r in rows) / len(rows), 1)
        totals['avg_pages_per_session'] = round(sum(float(r.get('screenPageViewsPerSession', 0)) for r in rows) / len(rows), 2)
        totals['events_per_session'] = round(totals['total_events'] / totals['sessions'], 2) if totals['sessions'] > 0 else 0

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'engagement_summary': totals,
        'daily_data': rows
    }


async def handle_get_browser_breakdown(property_id: str = None, days: int = 30, limit: int = 20) -> dict:
    """Get browser and OS breakdown"""
    # Browser breakdown
    browser_result = await handle_run_report(
        property_id=property_id,
        dimensions=['browser'],
        metrics=['sessions', 'activeUsers', 'bounceRate'],
        days=days,
        limit=limit
    )

    # OS breakdown
    os_result = await handle_run_report(
        property_id=property_id,
        dimensions=['operatingSystem'],
        metrics=['sessions', 'activeUsers', 'bounceRate'],
        days=days,
        limit=limit
    )

    browsers = []
    for row in browser_result.get('rows', []):
        browsers.append({
            'browser': row.get('browser', 'Unknown'),
            'sessions': int(row.get('sessions', 0)),
            'users': int(row.get('activeUsers', 0)),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2)
        })

    operating_systems = []
    for row in os_result.get('rows', []):
        operating_systems.append({
            'os': row.get('operatingSystem', 'Unknown'),
            'sessions': int(row.get('sessions', 0)),
            'users': int(row.get('activeUsers', 0)),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2)
        })

    return {
        'property_id': browser_result.get('property_id'),
        'date_range': browser_result.get('date_range'),
        'browsers': browsers,
        'operating_systems': operating_systems
    }


async def handle_get_city_breakdown(property_id: str = None, days: int = 30,
                                     limit: int = 50, country_filter: str = None) -> dict:
    """Get city-level breakdown"""
    dimensions = ['city', 'country']

    result = await handle_run_report(
        property_id=property_id,
        dimensions=dimensions,
        metrics=['sessions', 'activeUsers', 'bounceRate', 'averageSessionDuration'],
        days=days,
        limit=limit * 2  # Get more to filter
    )

    cities = []
    for row in result.get('rows', []):
        country = row.get('country', 'Unknown')

        # Apply country filter if specified
        if country_filter and country_filter.lower() not in country.lower():
            continue

        cities.append({
            'city': row.get('city', 'Unknown'),
            'country': country,
            'sessions': int(row.get('sessions', 0)),
            'users': int(row.get('activeUsers', 0)),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2),
            'avg_duration': round(float(row.get('averageSessionDuration', 0)), 1)
        })

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'country_filter': country_filter,
        'cities': cities[:limit]
    }


async def handle_get_ecommerce_overview(property_id: str = None, days: int = 30) -> dict:
    """Get e-commerce metrics"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['date'],
        metrics=[
            'ecommercePurchases', 'purchaseRevenue', 'totalPurchasers',
            'addToCarts', 'checkouts', 'itemsViewed',
            'purchaserConversionRate', 'averagePurchaseRevenue'
        ],
        days=days
    )

    rows = result.get('rows', [])

    # Calculate totals
    totals = {
        'total_purchases': sum(int(r.get('ecommercePurchases', 0)) for r in rows),
        'total_revenue': sum(float(r.get('purchaseRevenue', 0)) for r in rows),
        'total_purchasers': sum(int(r.get('totalPurchasers', 0)) for r in rows),
        'total_add_to_carts': sum(int(r.get('addToCarts', 0)) for r in rows),
        'total_checkouts': sum(int(r.get('checkouts', 0)) for r in rows),
        'total_items_viewed': sum(int(r.get('itemsViewed', 0)) for r in rows)
    }

    if len(rows) > 0:
        totals['avg_conversion_rate'] = round(sum(float(r.get('purchaserConversionRate', 0)) for r in rows) / len(rows) * 100, 2)
        totals['avg_order_value'] = round(sum(float(r.get('averagePurchaseRevenue', 0)) for r in rows) / len(rows), 2)

    # Calculate funnel
    if totals['total_items_viewed'] > 0:
        totals['cart_rate'] = round(totals['total_add_to_carts'] / totals['total_items_viewed'] * 100, 2)
    if totals['total_add_to_carts'] > 0:
        totals['checkout_rate'] = round(totals['total_checkouts'] / totals['total_add_to_carts'] * 100, 2)
    if totals['total_checkouts'] > 0:
        totals['purchase_rate'] = round(totals['total_purchases'] / totals['total_checkouts'] * 100, 2)

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'ecommerce_summary': totals,
        'daily_data': rows
    }


async def handle_get_all_events(property_id: str = None, days: int = 30, limit: int = 100) -> dict:
    """Get all tracked events"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['eventName'],
        metrics=['eventCount', 'totalUsers', 'eventCountPerUser'],
        days=days,
        limit=limit
    )

    events = []
    for row in result.get('rows', []):
        events.append({
            'event_name': row.get('eventName', ''),
            'event_count': int(row.get('eventCount', 0)),
            'total_users': int(row.get('totalUsers', 0)),
            'events_per_user': round(float(row.get('eventCountPerUser', 0)), 2)
        })

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'total_event_types': len(events),
        'events': events
    }


async def handle_get_hourly_traffic(property_id: str = None, days: int = 7) -> dict:
    """Get hourly traffic breakdown"""
    result = await handle_run_report(
        property_id=property_id,
        dimensions=['hour'],
        metrics=['sessions', 'activeUsers', 'bounceRate'],
        days=days
    )

    hourly_data = {}
    for row in result.get('rows', []):
        hour = int(row.get('hour', 0))
        hourly_data[hour] = {
            'sessions': int(row.get('sessions', 0)),
            'users': int(row.get('activeUsers', 0)),
            'bounce_rate': round(float(row.get('bounceRate', 0)) * 100, 2)
        }

    # Find peak hours
    sorted_hours = sorted(hourly_data.items(), key=lambda x: x[1]['sessions'], reverse=True)
    peak_hours = [h[0] for h in sorted_hours[:3]]

    return {
        'property_id': result.get('property_id'),
        'date_range': result.get('date_range'),
        'hourly_breakdown': hourly_data,
        'peak_hours': peak_hours
    }


async def handle_get_account_summary(property_id: str = None, days: int = 30) -> dict:
    """Get comprehensive account summary"""
    # Get traffic overview
    traffic = await handle_get_traffic_overview(property_id=property_id, days=days)

    # Get top sources
    sources = await handle_get_traffic_sources(property_id=property_id, days=days, limit=5)

    # Get device breakdown
    devices = await handle_get_device_breakdown(property_id=property_id, days=days)

    # Get top pages
    pages = await handle_get_top_pages(property_id=property_id, days=days, limit=5)

    # Get realtime
    try:
        realtime = await handle_get_realtime_data(property_id=property_id)
        current_users = realtime.get('total_active_users', 0)
    except:
        current_users = 'N/A'

    summary = traffic.get('summary', {})

    return {
        'property_id': property_id or get_property_id(),
        'date_range': traffic.get('date_range'),
        'current_active_users': current_users,
        'key_metrics': {
            'total_sessions': summary.get('sessions', 0),
            'total_users': summary.get('activeUsers', 0),
            'new_users': summary.get('newUsers', 0),
            'pageviews': summary.get('pageviews', 0),
            'avg_session_duration': round(summary.get('avgSessionDuration', 0), 1),
            'bounce_rate': round(summary.get('avgBounceRate', 0) * 100, 2)
        },
        'top_5_sources': sources.get('sources', [])[:5],
        'device_breakdown': devices.get('devices', {}),
        'top_5_pages': pages.get('pages', [])[:5],
        'insights': {
            'sessions_formatted': f"{summary.get('sessions', 0):,}",
            'users_formatted': f"{summary.get('activeUsers', 0):,}",
            'mobile_share': round(devices.get('devices', {}).get('mobile', {}).get('sessions', 0) /
                                  max(summary.get('sessions', 1), 1) * 100, 1)
        }
    }


# Tool handler mapping
TOOL_HANDLERS = {
    # Original tools
    "run_report": handle_run_report,
    "get_traffic_overview": handle_get_traffic_overview,
    "get_traffic_sources": handle_get_traffic_sources,
    "get_top_pages": handle_get_top_pages,
    "get_device_breakdown": handle_get_device_breakdown,
    "get_country_breakdown": handle_get_country_breakdown,
    "get_realtime_data": handle_get_realtime_data,
    "get_conversions": handle_get_conversions,
    "get_property_info": handle_get_property_info,
    # New tools - v2.0
    "get_utm_campaigns": handle_get_utm_campaigns,
    "get_landing_pages": handle_get_landing_pages,
    "get_user_acquisition": handle_get_user_acquisition,
    "get_engagement_metrics": handle_get_engagement_metrics,
    "get_browser_breakdown": handle_get_browser_breakdown,
    "get_city_breakdown": handle_get_city_breakdown,
    "get_ecommerce_overview": handle_get_ecommerce_overview,
    "get_all_events": handle_get_all_events,
    "get_hourly_traffic": handle_get_hourly_traffic,
    "get_account_summary": handle_get_account_summary
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
