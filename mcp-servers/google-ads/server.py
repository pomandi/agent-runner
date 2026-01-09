#!/usr/bin/env python3
"""
Google Ads MCP Server v2.0
===========================
Enhanced MCP Server for Google Ads API integration with Claude Code.

Provides tools for:
- Campaign performance data (Search, PMax, Display, Video)
- Ad group performance with bid strategies
- Keyword analysis with quality scores & historical metrics
- Search terms reports with conversion data
- Geographic and device performance
- Conversion tracking with attribution
- Asset performance (RSA headlines/descriptions)
- Audience insights and demographics
- Budget & bid recommendations
- Change history tracking
- Performance Max insights
- AI Max for Search metrics (TargetingExpansionView)

Environment Variables Required:
- GOOGLE_ADS_YAML_PATH: Path to google-ads.yaml config file
- GOOGLE_ADS_CUSTOMER_ID: Google Ads Customer ID

Version: 2.0 (Enhanced with v22 API features)
API Version: Google Ads API v22
Last Updated: 2025-12-15

New in v2.0:
- Added PMax campaign support with asset group performance
- Added audience demographics breakdown
- Added budget recommendations tool
- Added change history tracking
- Added asset-level performance metrics
- Added hourly performance breakdown
- Added conversion lag analysis
- Added impression share analysis
- Improved error handling and logging
"""

import asyncio
import json
import os
import sys
import logging
from typing import Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================================
# LOGGING SETUP - Detaylı loglar için
# ============================================================================

# Log dosyası yolu - try multiple paths
LOG_DIR = None
for log_path in ["/app/logs/mcp-servers", "/tmp/mcp-servers", "/var/log/mcp-servers"]:
    try:
        LOG_DIR = Path(log_path)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        break
    except (PermissionError, OSError):
        continue

if LOG_DIR is None:
    LOG_DIR = Path("/tmp")

LOG_FILE = LOG_DIR / "google-ads-mcp.log"

# Logger ayarları
logger = logging.getLogger("google-ads-mcp")
logger.setLevel(logging.DEBUG)

# File handler - dosyaya yaz
file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(funcName)-25s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Stderr handler - konsola da yaz (debug için)
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.INFO)
stderr_formatter = logging.Formatter('🔧 MCP-GADS | %(levelname)s | %(message)s')
stderr_handler.setFormatter(stderr_formatter)
logger.addHandler(stderr_handler)

def log_separator():
    """Log dosyasına ayırıcı ekle"""
    logger.info("=" * 80)

def log_tool_call(tool_name: str, arguments: dict):
    """Tool çağrısını logla"""
    log_separator()
    logger.info(f"🔔 TOOL ÇAĞRILDI: {tool_name}")
    logger.info(f"📥 PARAMETRELER: {json.dumps(arguments, default=str)}")
    logger.info(f"⏰ ZAMAN: {datetime.now().isoformat()}")

def log_tool_result(tool_name: str, result: dict, duration_ms: float):
    """Tool sonucunu logla"""
    record_count = 0
    if isinstance(result, dict):
        for key in ['campaigns', 'ad_groups', 'keywords', 'search_terms', 'ads', 'results', 'geo_performance', 'device_performance', 'conversion_actions']:
            if key in result:
                record_count = len(result[key])
                break
        if 'total_campaigns' in result:
            record_count = result['total_campaigns']
        elif 'total_keywords' in result:
            record_count = result['total_keywords']
        elif 'total_search_terms' in result:
            record_count = result['total_search_terms']

    logger.info(f"✅ TOOL TAMAMLANDI: {tool_name}")
    logger.info(f"📊 KAYIT SAYISI: {record_count}")
    logger.info(f"⏱️ SÜRE: {duration_ms:.2f}ms")
    logger.info(f"📤 SONUÇ BOYUTU: {len(json.dumps(result, default=str))} karakter")

def log_tool_error(tool_name: str, error: str):
    """Tool hatasını logla"""
    logger.error(f"❌ TOOL HATASI: {tool_name}")
    logger.error(f"💥 HATA: {error}")

# Başlangıç logu
logger.info("=" * 80)
logger.info("🚀 GOOGLE ADS MCP SERVER BAŞLATILDI")
logger.info(f"📁 LOG DOSYASI: {LOG_FILE}")
logger.info(f"⏰ BAŞLANGIÇ: {datetime.now().isoformat()}")
logger.info("=" * 80)

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

# Google Ads API
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import json_format

# Server info
SERVER_NAME = "google-ads"
SERVER_VERSION = "2.0.0"

# Initialize MCP server
server = Server(SERVER_NAME)

# Global client
_client: Optional[GoogleAdsClient] = None
_ga_service = None


def get_config_path() -> str:
    """Get Google Ads config path from environment or default"""
    return os.getenv("GOOGLE_ADS_YAML_PATH", str(Path.home() / ".claude" / "config" / "google-ads.yaml"))


def get_customer_id() -> str:
    """Get Google Ads customer ID from environment or default"""
    return os.getenv("GOOGLE_ADS_CUSTOMER_ID", "5945647044")


def get_client() -> GoogleAdsClient:
    """Get or create Google Ads client"""
    global _client, _ga_service
    if _client is None:
        config_path = get_config_path()
        _client = GoogleAdsClient.load_from_storage(config_path)
        _ga_service = _client.get_service("GoogleAdsService")
    return _client


def get_ga_service():
    """Get Google Ads service"""
    global _ga_service
    if _ga_service is None:
        get_client()
    return _ga_service


def execute_query(query: str) -> list:
    """Execute GAQL query and return results as dicts"""
    import time
    start_time = time.time()
    results = []

    # Query'yi logla
    logger.debug(f"📝 GAQL QUERY ÇALIŞTIRILACAK:")
    logger.debug(f"{query[:500]}...")  # İlk 500 karakter

    try:
        ga_service = get_ga_service()
        customer_id = get_customer_id()
        logger.debug(f"🔑 Customer ID: {customer_id}")

        response = ga_service.search(
            customer_id=customer_id,
            query=query
        )

        row_count = 0
        for row in response:
            row_dict = json_format.MessageToDict(row._pb)
            results.append(row_dict)
            row_count += 1

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"📊 GAQL SONUÇ: {row_count} satır döndü ({duration_ms:.2f}ms)")

    except GoogleAdsException as ex:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = ex.failure.errors[0].message if ex.failure.errors else str(ex)
        logger.error(f"❌ GAQL HATA: {error_msg} ({duration_ms:.2f}ms)")
        raise Exception(f"Google Ads API Error: {error_msg}")

    return results


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="get_campaigns",
        description="Get Search campaign performance data for a date range. Returns campaign metrics including impressions, clicks, cost, conversions, and impression share.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format"
                },
                "days": {
                    "type": "integer",
                    "description": "Alternative to date range: number of days back from today (default: 7)"
                }
            }
        }
    ),
    Tool(
        name="get_ad_groups",
        description="Get ad group performance data for Search campaigns. Returns metrics by ad group including CTR, CPC, and conversions.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_keywords",
        description="Get keyword performance with quality scores. Returns keyword metrics, match types, and quality score components.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"},
                "min_impressions": {"type": "integer", "description": "Minimum impressions filter (default: 0)"},
                "limit": {"type": "integer", "description": "Max results (default: 1000)"}
            }
        }
    ),
    Tool(
        name="get_search_terms",
        description="Get search terms report showing actual queries that triggered ads. Essential for finding new keywords and negatives.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"},
                "min_impressions": {"type": "integer", "description": "Minimum impressions (default: 1)"},
                "limit": {"type": "integer", "description": "Max results (default: 500)"}
            }
        }
    ),
    Tool(
        name="get_ads",
        description="Get ad performance data including RSA (Responsive Search Ad) details with headlines and descriptions.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_geo_performance",
        description="Get geographic performance breakdown by location/country.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_device_performance",
        description="Get performance breakdown by device type (mobile, desktop, tablet).",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"}
            }
        }
    ),
    Tool(
        name="get_conversions",
        description="Get conversion actions configuration and settings.",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    Tool(
        name="run_gaql_query",
        description="Run a custom GAQL (Google Ads Query Language) query. For advanced users who need specific data not covered by other tools.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "GAQL query to execute"
                }
            },
            "required": ["query"]
        }
    ),
    # ============================================================================
    # NEW TOOLS - Added in v2.0
    # ============================================================================
    Tool(
        name="get_pmax_campaigns",
        description="Get Performance Max campaign data with asset group performance, search term insights, and audience signals.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "days": {"type": "integer", "description": "Number of days back from today (default: 30)"}
            }
        }
    ),
    Tool(
        name="get_asset_performance",
        description="Get RSA (Responsive Search Ad) asset-level performance showing which headlines and descriptions perform best.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"},
                "performance_label": {"type": "string", "description": "Optional: Filter by label (BEST, GOOD, LOW, PENDING)"}
            }
        }
    ),
    Tool(
        name="get_audience_insights",
        description="Get audience demographics breakdown including age, gender, parental status, and income range performance.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "dimension": {
                    "type": "string",
                    "description": "Breakdown dimension: age, gender, parental_status, income. Default: age",
                    "enum": ["age", "gender", "parental_status", "income"]
                }
            }
        }
    ),
    Tool(
        name="get_hourly_performance",
        description="Get performance breakdown by hour of day and day of week to identify optimal ad scheduling.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_impression_share_analysis",
        description="Get detailed impression share analysis including lost IS due to rank and budget, top/absolute top IS.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_change_history",
        description="Get recent changes made to the account including campaign, ad group, keyword, and bid changes.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of history (default: 7, max: 30)"},
                "resource_type": {
                    "type": "string",
                    "description": "Filter by resource type: CAMPAIGN, AD_GROUP, AD, KEYWORD, all. Default: all"
                },
                "limit": {"type": "integer", "description": "Max results (default: 100)"}
            }
        }
    ),
    Tool(
        name="get_budget_recommendations",
        description="Get budget optimization recommendations based on campaign performance and lost impression share.",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_conversion_by_time",
        description="Get conversion performance by conversion lag (time between click and conversion) and by conversion action.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_landing_page_performance",
        description="Get landing page performance metrics including expanded landing page URLs, mobile speed, and conversion rates.",
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "limit": {"type": "integer", "description": "Max results (default: 100)"}
            }
        }
    ),
    Tool(
        name="get_negative_keywords",
        description="Get all negative keywords at campaign and ad group level.",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"},
                "level": {
                    "type": "string",
                    "description": "Level: campaign, ad_group, all. Default: all",
                    "enum": ["campaign", "ad_group", "all"]
                }
            }
        }
    ),
    Tool(
        name="get_account_summary",
        description="Get a comprehensive account summary with key metrics, top campaigns, and actionable insights.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days (default: 30)"}
            }
        }
    )
]


# ============================================================================
# Tool Handlers
# ============================================================================

def get_date_range(start_date: str = None, end_date: str = None, days: int = 7) -> tuple:
    """Calculate date range from parameters"""
    if start_date and end_date:
        return start_date, end_date

    end = datetime.now()
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


async def handle_get_campaigns(start_date: str = None, end_date: str = None, days: int = 7) -> dict:
    """Get campaign performance data"""
    start_date, end_date = get_date_range(start_date, end_date, days)

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.bidding_strategy_type,
            campaign_budget.amount_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.average_cpc,
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_per_conversion,
            metrics.search_impression_share,
            metrics.search_top_impression_share,
            metrics.search_absolute_top_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND campaign.status != 'REMOVED'
        ORDER BY metrics.cost_micros DESC
    """

    results = execute_query(query)
    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_campaigns": len(results),
        "campaigns": results
    }


async def handle_get_ad_groups(start_date: str = None, end_date: str = None, campaign_id: str = None) -> dict:
    """Get ad group performance data"""
    start_date, end_date = get_date_range(start_date, end_date, 7)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            ad_group.id,
            ad_group.name,
            ad_group.status,
            ad_group.cpc_bid_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.average_cpc,
            metrics.conversions,
            metrics.conversions_value,
            metrics.search_impression_share
        FROM ad_group
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND ad_group.status != 'REMOVED'
        {campaign_filter}
        ORDER BY metrics.cost_micros DESC
    """

    results = execute_query(query)
    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_ad_groups": len(results),
        "ad_groups": results
    }


async def handle_get_keywords(start_date: str = None, end_date: str = None,
                               campaign_id: str = None, min_impressions: int = 0,
                               limit: int = 1000) -> dict:
    """Get keyword performance with quality scores"""
    start_date, end_date = get_date_range(start_date, end_date, 7)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            ad_group.id,
            ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.quality_info.quality_score,
            ad_group_criterion.quality_info.creative_quality_score,
            ad_group_criterion.quality_info.search_predicted_ctr,
            ad_group_criterion.quality_info.post_click_quality_score,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.average_cpc,
            metrics.conversions,
            metrics.conversions_value,
            metrics.search_impression_share
        FROM keyword_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND ad_group_criterion.status != 'REMOVED'
        AND metrics.impressions >= {min_impressions}
        {campaign_filter}
        ORDER BY metrics.cost_micros DESC
        LIMIT {limit}
    """

    results = execute_query(query)

    # Count keywords with quality scores
    qs_count = sum(1 for r in results if r.get("adGroupCriterion", {}).get("qualityInfo", {}).get("qualityScore"))

    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_keywords": len(results),
        "keywords_with_qs": qs_count,
        "keywords": results
    }


async def handle_get_search_terms(start_date: str = None, end_date: str = None,
                                   campaign_id: str = None, min_impressions: int = 1,
                                   limit: int = 500) -> dict:
    """Get search terms report"""
    start_date, end_date = get_date_range(start_date, end_date, 7)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            ad_group.id,
            ad_group.name,
            search_term_view.search_term,
            search_term_view.status,
            segments.search_term_match_type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.average_cpc,
            metrics.conversions,
            metrics.conversions_value
        FROM search_term_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND metrics.impressions >= {min_impressions}
        {campaign_filter}
        ORDER BY metrics.impressions DESC
        LIMIT {limit}
    """

    results = execute_query(query)
    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_search_terms": len(results),
        "search_terms": results
    }


async def handle_get_ads(start_date: str = None, end_date: str = None,
                          campaign_id: str = None) -> dict:
    """Get ad performance including RSA details"""
    start_date, end_date = get_date_range(start_date, end_date, 7)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            ad_group.id,
            ad_group.name,
            ad_group_ad.ad.id,
            ad_group_ad.ad.type,
            ad_group_ad.ad.final_urls,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions,
            ad_group_ad.status,
            ad_group_ad.ad_strength,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM ad_group_ad
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND ad_group_ad.status != 'REMOVED'
        {campaign_filter}
        ORDER BY metrics.cost_micros DESC
        LIMIT 500
    """

    results = execute_query(query)
    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_ads": len(results),
        "ads": results
    }


async def handle_get_geo_performance(start_date: str = None, end_date: str = None,
                                      campaign_id: str = None) -> dict:
    """Get geographic performance breakdown"""
    start_date, end_date = get_date_range(start_date, end_date, 7)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            geographic_view.country_criterion_id,
            geographic_view.location_type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM geographic_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND metrics.impressions > 0
        {campaign_filter}
        ORDER BY metrics.impressions DESC
        LIMIT 500
    """

    results = execute_query(query)
    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_locations": len(results),
        "geo_performance": results
    }


async def handle_get_device_performance(start_date: str = None, end_date: str = None) -> dict:
    """Get device performance breakdown"""
    start_date, end_date = get_date_range(start_date, end_date, 7)

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            segments.device,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND campaign.status != 'REMOVED'
        ORDER BY metrics.cost_micros DESC
    """

    results = execute_query(query)
    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_records": len(results),
        "device_performance": results
    }


async def handle_get_conversions() -> dict:
    """Get conversion actions configuration"""
    query = """
        SELECT
            conversion_action.id,
            conversion_action.name,
            conversion_action.type,
            conversion_action.category,
            conversion_action.status,
            conversion_action.counting_type,
            conversion_action.value_settings.default_value,
            conversion_action.attribution_model_settings.attribution_model
        FROM conversion_action
        WHERE conversion_action.status = 'ENABLED'
    """

    results = execute_query(query)
    return {
        "total_conversions": len(results),
        "conversion_actions": results
    }


async def handle_run_gaql_query(query: str) -> dict:
    """Run custom GAQL query"""
    results = execute_query(query)
    return {
        "query": query,
        "total_results": len(results),
        "results": results
    }


# ============================================================================
# NEW Tool Handlers - Added in v2.0
# ============================================================================

async def handle_get_pmax_campaigns(start_date: str = None, end_date: str = None, days: int = 30) -> dict:
    """Get Performance Max campaign data with asset groups"""
    start_date, end_date = get_date_range(start_date, end_date, days)

    # PMax campaigns
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.bidding_strategy_type,
            campaign_budget.amount_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_per_conversion,
            metrics.all_conversions,
            metrics.all_conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'PERFORMANCE_MAX'
        AND campaign.status != 'REMOVED'
        ORDER BY metrics.cost_micros DESC
    """

    campaigns = execute_query(query)

    # Asset groups for PMax
    asset_group_query = f"""
        SELECT
            campaign.id,
            campaign.name,
            asset_group.id,
            asset_group.name,
            asset_group.status,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM asset_group
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'PERFORMANCE_MAX'
        ORDER BY metrics.cost_micros DESC
    """

    try:
        asset_groups = execute_query(asset_group_query)
    except:
        asset_groups = []

    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_pmax_campaigns": len(campaigns),
        "campaigns": campaigns,
        "asset_groups": asset_groups
    }


async def handle_get_asset_performance(start_date: str = None, end_date: str = None,
                                        campaign_id: str = None, performance_label: str = None) -> dict:
    """Get RSA asset-level performance"""
    start_date, end_date = get_date_range(start_date, end_date, 30)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""
    label_filter = f"AND ad_group_ad_asset_view.performance_label = '{performance_label}'" if performance_label else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            ad_group.id,
            ad_group.name,
            ad_group_ad_asset_view.field_type,
            ad_group_ad_asset_view.performance_label,
            asset.text_asset.text,
            asset.type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions
        FROM ad_group_ad_asset_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND ad_group_ad_asset_view.field_type IN ('HEADLINE', 'DESCRIPTION')
        {campaign_filter}
        {label_filter}
        ORDER BY metrics.impressions DESC
        LIMIT 500
    """

    results = execute_query(query)

    # Group by performance label
    by_label = {"BEST": [], "GOOD": [], "LOW": [], "PENDING": [], "UNKNOWN": []}
    for r in results:
        label = r.get("adGroupAdAssetView", {}).get("performanceLabel", "UNKNOWN")
        by_label.get(label, by_label["UNKNOWN"]).append(r)

    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_assets": len(results),
        "by_performance_label": {k: len(v) for k, v in by_label.items()},
        "assets": results
    }


async def handle_get_audience_insights(start_date: str = None, end_date: str = None,
                                        dimension: str = "age") -> dict:
    """Get audience demographics breakdown"""
    start_date, end_date = get_date_range(start_date, end_date, 30)

    dimension_map = {
        "age": "ad_group_criterion.age_range.type",
        "gender": "ad_group_criterion.gender.type",
        "parental_status": "ad_group_criterion.parental_status.type",
        "income": "ad_group_criterion.income_range.type"
    }

    view_map = {
        "age": "age_range_view",
        "gender": "gender_view",
        "parental_status": "parental_status_view",
        "income": "income_range_view"
    }

    dim_field = dimension_map.get(dimension, dimension_map["age"])
    view = view_map.get(dimension, view_map["age"])

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            {dim_field},
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM {view}
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.status != 'REMOVED'
        ORDER BY metrics.impressions DESC
    """

    results = execute_query(query)

    return {
        "date_range": {"start": start_date, "end": end_date},
        "dimension": dimension,
        "total_segments": len(results),
        "data": results
    }


async def handle_get_hourly_performance(start_date: str = None, end_date: str = None,
                                         campaign_id: str = None) -> dict:
    """Get hourly performance breakdown"""
    start_date, end_date = get_date_range(start_date, end_date, 7)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            segments.hour,
            segments.day_of_week,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND campaign.status != 'REMOVED'
        {campaign_filter}
        ORDER BY segments.day_of_week, segments.hour
    """

    results = execute_query(query)

    # Aggregate by hour
    hourly_stats = {}
    for r in results:
        hour = r.get("segments", {}).get("hour", 0)
        if hour not in hourly_stats:
            hourly_stats[hour] = {"impressions": 0, "clicks": 0, "cost_micros": 0, "conversions": 0}
        metrics = r.get("metrics", {})
        hourly_stats[hour]["impressions"] += int(metrics.get("impressions", 0))
        hourly_stats[hour]["clicks"] += int(metrics.get("clicks", 0))
        hourly_stats[hour]["cost_micros"] += int(metrics.get("costMicros", 0))
        hourly_stats[hour]["conversions"] += float(metrics.get("conversions", 0))

    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_records": len(results),
        "hourly_summary": hourly_stats,
        "raw_data": results
    }


async def handle_get_impression_share_analysis(start_date: str = None, end_date: str = None,
                                                campaign_id: str = None) -> dict:
    """Get detailed impression share analysis"""
    start_date, end_date = get_date_range(start_date, end_date, 30)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.search_impression_share,
            metrics.search_top_impression_share,
            metrics.search_absolute_top_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share,
            metrics.search_budget_lost_top_impression_share,
            metrics.search_rank_lost_top_impression_share,
            metrics.search_budget_lost_absolute_top_impression_share,
            metrics.search_rank_lost_absolute_top_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.advertising_channel_type = 'SEARCH'
        AND campaign.status != 'REMOVED'
        {campaign_filter}
        ORDER BY metrics.cost_micros DESC
    """

    results = execute_query(query)

    # Calculate opportunity
    opportunities = []
    for r in results:
        metrics = r.get("metrics", {})
        budget_lost = float(metrics.get("searchBudgetLostImpressionShare", 0) or 0)
        rank_lost = float(metrics.get("searchRankLostImpressionShare", 0) or 0)

        if budget_lost > 0.1 or rank_lost > 0.1:
            opportunities.append({
                "campaign": r.get("campaign", {}).get("name"),
                "budget_lost_is": round(budget_lost * 100, 1),
                "rank_lost_is": round(rank_lost * 100, 1),
                "recommendation": "Increase budget" if budget_lost > rank_lost else "Improve quality/bids"
            })

    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_campaigns": len(results),
        "improvement_opportunities": opportunities,
        "data": results
    }


async def handle_get_change_history(days: int = 7, resource_type: str = "all",
                                     limit: int = 100) -> dict:
    """Get recent change history"""
    days = min(days, 30)  # Max 30 days

    resource_filter = ""
    if resource_type != "all":
        resource_filter = f"AND change_event.change_resource_type = '{resource_type}'"

    query = f"""
        SELECT
            change_event.change_date_time,
            change_event.change_resource_type,
            change_event.change_resource_name,
            change_event.client_type,
            change_event.user_email,
            change_event.old_resource,
            change_event.new_resource,
            change_event.resource_change_operation
        FROM change_event
        WHERE change_event.change_date_time DURING LAST_{days}_DAYS
        {resource_filter}
        ORDER BY change_event.change_date_time DESC
        LIMIT {limit}
    """

    results = execute_query(query)

    return {
        "days": days,
        "resource_type_filter": resource_type,
        "total_changes": len(results),
        "changes": results
    }


async def handle_get_budget_recommendations(campaign_id: str = None) -> dict:
    """Get budget optimization recommendations"""
    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    # Get campaigns with lost IS due to budget
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign_budget.amount_micros,
            campaign_budget.explicitly_shared,
            metrics.cost_micros,
            metrics.impressions,
            metrics.conversions,
            metrics.conversions_value,
            metrics.search_budget_lost_impression_share,
            metrics.search_impression_share
        FROM campaign
        WHERE segments.date DURING LAST_30_DAYS
        AND campaign.advertising_channel_type = 'SEARCH'
        AND campaign.status = 'ENABLED'
        {campaign_filter}
        ORDER BY metrics.search_budget_lost_impression_share DESC
    """

    results = execute_query(query)

    recommendations = []
    for r in results:
        metrics = r.get("metrics", {})
        campaign_info = r.get("campaign", {})
        budget_info = r.get("campaignBudget", {})

        budget_lost = float(metrics.get("searchBudgetLostImpressionShare", 0) or 0)
        current_budget = int(budget_info.get("amountMicros", 0)) / 1_000_000
        cost = int(metrics.get("costMicros", 0)) / 1_000_000
        conversions = float(metrics.get("conversions", 0))

        if budget_lost > 0.05:  # More than 5% lost to budget
            # Estimate potential uplift
            potential_increase = budget_lost * 100
            recommended_budget = current_budget * (1 + budget_lost + 0.1)

            recommendations.append({
                "campaign_id": campaign_info.get("id"),
                "campaign_name": campaign_info.get("name"),
                "current_daily_budget": round(current_budget, 2),
                "recommended_daily_budget": round(recommended_budget, 2),
                "budget_lost_impression_share": f"{round(budget_lost * 100, 1)}%",
                "estimated_conversion_uplift": f"+{round(potential_increase, 0)}%",
                "current_conversions": conversions,
                "priority": "HIGH" if budget_lost > 0.2 else "MEDIUM" if budget_lost > 0.1 else "LOW"
            })

    return {
        "total_campaigns_analyzed": len(results),
        "campaigns_with_budget_opportunity": len(recommendations),
        "recommendations": sorted(recommendations, key=lambda x: x["priority"])
    }


async def handle_get_conversion_by_time(start_date: str = None, end_date: str = None,
                                         campaign_id: str = None) -> dict:
    """Get conversion performance by lag bucket"""
    start_date, end_date = get_date_range(start_date, end_date, 30)

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            segments.conversion_action_name,
            segments.conversion_lag_bucket,
            metrics.conversions,
            metrics.conversions_value,
            metrics.all_conversions
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.status != 'REMOVED'
        AND metrics.conversions > 0
        {campaign_filter}
        ORDER BY metrics.conversions DESC
    """

    results = execute_query(query)

    # Group by lag bucket
    by_lag = {}
    for r in results:
        lag = r.get("segments", {}).get("conversionLagBucket", "UNKNOWN")
        if lag not in by_lag:
            by_lag[lag] = {"conversions": 0, "value": 0}
        by_lag[lag]["conversions"] += float(r.get("metrics", {}).get("conversions", 0))
        by_lag[lag]["value"] += float(r.get("metrics", {}).get("conversionsValue", 0))

    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_records": len(results),
        "by_conversion_lag": by_lag,
        "raw_data": results
    }


async def handle_get_landing_page_performance(start_date: str = None, end_date: str = None,
                                               limit: int = 100) -> dict:
    """Get landing page performance"""
    start_date, end_date = get_date_range(start_date, end_date, 30)

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            landing_page_view.unexpanded_final_url,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_per_conversion,
            metrics.mobile_friendly_clicks_percentage,
            metrics.speed_score
        FROM landing_page_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND metrics.impressions > 0
        ORDER BY metrics.clicks DESC
        LIMIT {limit}
    """

    results = execute_query(query)

    return {
        "date_range": {"start": start_date, "end": end_date},
        "total_landing_pages": len(results),
        "landing_pages": results
    }


async def handle_get_negative_keywords(campaign_id: str = None, level: str = "all") -> dict:
    """Get negative keywords"""
    results = {"campaign_level": [], "ad_group_level": []}

    campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""

    if level in ["campaign", "all"]:
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign_criterion.keyword.text,
                campaign_criterion.keyword.match_type,
                campaign_criterion.negative
            FROM campaign_criterion
            WHERE campaign_criterion.negative = TRUE
            AND campaign_criterion.type = 'KEYWORD'
            {campaign_filter}
        """
        results["campaign_level"] = execute_query(query)

    if level in ["ad_group", "all"]:
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                ad_group.id,
                ad_group.name,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.negative
            FROM ad_group_criterion
            WHERE ad_group_criterion.negative = TRUE
            AND ad_group_criterion.type = 'KEYWORD'
            {campaign_filter}
        """
        results["ad_group_level"] = execute_query(query)

    return {
        "level_filter": level,
        "total_campaign_negatives": len(results["campaign_level"]),
        "total_ad_group_negatives": len(results["ad_group_level"]),
        "negatives": results
    }


async def handle_get_account_summary(days: int = 30) -> dict:
    """Get comprehensive account summary"""
    start_date, end_date = get_date_range(None, None, days)

    # Overall metrics
    account_query = f"""
        SELECT
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value,
            metrics.average_cpc
        FROM customer
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
    """

    account_data = execute_query(account_query)

    # Top campaigns
    campaigns_data = await handle_get_campaigns(start_date, end_date, days)

    # Budget opportunities
    budget_recs = await handle_get_budget_recommendations()

    # Calculate totals
    totals = {
        "impressions": 0, "clicks": 0, "cost": 0,
        "conversions": 0, "conversion_value": 0
    }
    for row in account_data:
        m = row.get("metrics", {})
        totals["impressions"] += int(m.get("impressions", 0))
        totals["clicks"] += int(m.get("clicks", 0))
        totals["cost"] += int(m.get("costMicros", 0)) / 1_000_000
        totals["conversions"] += float(m.get("conversions", 0))
        totals["conversion_value"] += float(m.get("conversionsValue", 0))

    totals["ctr"] = round(totals["clicks"] / totals["impressions"] * 100, 2) if totals["impressions"] > 0 else 0
    totals["cpc"] = round(totals["cost"] / totals["clicks"], 2) if totals["clicks"] > 0 else 0
    totals["cpa"] = round(totals["cost"] / totals["conversions"], 2) if totals["conversions"] > 0 else 0
    totals["roas"] = round(totals["conversion_value"] / totals["cost"], 2) if totals["cost"] > 0 else 0
    totals["cost"] = round(totals["cost"], 2)
    totals["conversion_value"] = round(totals["conversion_value"], 2)

    return {
        "date_range": {"start": start_date, "end": end_date, "days": days},
        "account_totals": totals,
        "campaign_count": campaigns_data.get("total_campaigns", 0),
        "top_5_campaigns": campaigns_data.get("campaigns", [])[:5],
        "budget_opportunities": budget_recs.get("recommendations", [])[:3],
        "insights": {
            "total_spend": f"€{totals['cost']:,.2f}",
            "total_conversions": totals['conversions'],
            "avg_cpa": f"€{totals['cpa']:.2f}",
            "roas": f"{totals['roas']:.2f}x"
        }
    }


# Tool handler mapping
TOOL_HANDLERS = {
    # Original tools
    "get_campaigns": handle_get_campaigns,
    "get_ad_groups": handle_get_ad_groups,
    "get_keywords": handle_get_keywords,
    "get_search_terms": handle_get_search_terms,
    "get_ads": handle_get_ads,
    "get_geo_performance": handle_get_geo_performance,
    "get_device_performance": handle_get_device_performance,
    "get_conversions": handle_get_conversions,
    "run_gaql_query": handle_run_gaql_query,
    # New tools - v2.0
    "get_pmax_campaigns": handle_get_pmax_campaigns,
    "get_asset_performance": handle_get_asset_performance,
    "get_audience_insights": handle_get_audience_insights,
    "get_hourly_performance": handle_get_hourly_performance,
    "get_impression_share_analysis": handle_get_impression_share_analysis,
    "get_change_history": handle_get_change_history,
    "get_budget_recommendations": handle_get_budget_recommendations,
    "get_conversion_by_time": handle_get_conversion_by_time,
    "get_landing_page_performance": handle_get_landing_page_performance,
    "get_negative_keywords": handle_get_negative_keywords,
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
    import time
    start_time = time.time()

    # Tool çağrısını logla
    log_tool_call(name, arguments)

    if name not in TOOL_HANDLERS:
        log_tool_error(name, f"Unknown tool: {name}")
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        handler = TOOL_HANDLERS[name]
        logger.debug(f"Handler başlatılıyor: {handler.__name__}")

        result = await handler(**arguments)

        # Süreyi hesapla
        duration_ms = (time.time() - start_time) * 1000

        # Sonucu logla
        log_tool_result(name, result, duration_ms)

        # Return list of TextContent directly (MCP SDK handles wrapping)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = str(e)
        log_tool_error(name, error_msg)
        logger.error(f"⏱️ HATA SÜRESİ: {duration_ms:.2f}ms")
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
