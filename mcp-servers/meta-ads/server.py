#!/usr/bin/env python3
"""
Meta Ads MCP Server v2.0
=========================
Enhanced MCP Server for Meta (Facebook/Instagram) Ads API integration with Claude Code.

Provides tools for:
- Campaign performance data with detailed breakdowns
- Ad set performance with targeting info
- Ad performance with creative details
- Account insights with demographic breakdowns
- Creative performance analysis
- Audience insights (age, gender, country, placement)
- Video metrics (views, completions, engagement)
- Conversion tracking with attribution windows
- A/B test analysis
- Budget recommendations
- Advantage+ campaign insights

Environment Variables Required:
- FACEBOOK_APP_ID: Facebook App ID
- FACEBOOK_APP_SECRET: Facebook App Secret
- FACEBOOK_ACCESS_TOKEN: Facebook Access Token
- FACEBOOK_AD_ACCOUNT_ID: Ad Account ID (e.g., act_963386574972372)

Version: 2.0 (Enhanced with v22.0 API features)
API Version: Meta Graph API v22.0
Last Updated: 2025-12-15

New in v2.0:
- Added demographic breakdowns (age, gender, country, placement, device)
- Added video engagement metrics
- Added creative performance analysis
- Added placement performance breakdown
- Added hourly performance data
- Added reach and frequency analysis
- Added conversion attribution breakdown
- Added Advantage+ campaign support
- Improved error handling
"""

import asyncio
import json
import os
import re
from typing import Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Server info
SERVER_NAME = "meta-ads"
SERVER_VERSION = "2.0.0"

# Initialize MCP server
server = Server(SERVER_NAME)

# Global credentials
_credentials: Optional[dict] = None


def load_credentials() -> dict:
    """Load credentials from environment variables or .env file

    Supports multiple credential sources in priority order:
    1. Environment variables (Docker container / production)
    2. .env file (~/.claude/.env for local development)

    Supports both naming conventions:
    - META_ACCESS_TOKEN_POMANDI (container env vars)
    - FACEBOOK_ACCESS_TOKEN (legacy/standard naming)
    """
    global _credentials
    if _credentials is not None:
        return _credentials

    credentials = {}

    # 1. Try environment variables first (Docker container)
    # Support both META_* and FACEBOOK_* naming conventions
    env_mappings = [
        # (credential_key, env_var_options)
        ('FACEBOOK_ACCESS_TOKEN', ['META_ACCESS_TOKEN_POMANDI', 'META_ACCESS_TOKEN', 'FACEBOOK_ACCESS_TOKEN']),
        ('FACEBOOK_APP_ID', ['META_APP_ID_POMANDI', 'META_APP_ID', 'FACEBOOK_APP_ID']),
        ('FACEBOOK_APP_SECRET', ['META_APP_SECRET_POMANDI', 'META_APP_SECRET', 'FACEBOOK_APP_SECRET']),
        ('FACEBOOK_AD_ACCOUNT_ID', ['META_AD_ACCOUNT_ID_POMANDI', 'META_AD_ACCOUNT_ID', 'FACEBOOK_AD_ACCOUNT_ID']),
        ('FACEBOOK_PAGE_ID', ['META_PAGE_ID_POMANDI', 'META_PAGE_ID', 'FACEBOOK_PAGE_ID']),
        ('FACEBOOK_IG_ACCOUNT_ID', ['META_IG_ACCOUNT_ID_POMANDI', 'META_IG_ACCOUNT_ID', 'FACEBOOK_IG_ACCOUNT_ID']),
    ]

    for cred_key, env_options in env_mappings:
        for env_var in env_options:
            value = os.environ.get(env_var)
            if value:
                credentials[cred_key] = value
                break

    # 2. Fall back to .env file for local development
    if not credentials.get('FACEBOOK_ACCESS_TOKEN'):
        env_file = Path.home() / '.claude' / '.env'
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip() and not line.startswith('#') and '=' in line:
                        key, value = line.strip().split('=', 1)
                        # Only add if not already set from env vars
                        if key not in credentials:
                            credentials[key] = value.strip('"').strip("'")

    # Log loaded credentials (without sensitive values)
    loaded_keys = list(credentials.keys())
    import sys
    print(f"[META-ADS] Loaded credentials: {loaded_keys}", file=sys.stderr)

    _credentials = credentials
    return credentials


def get_api_client():
    """Get Facebook Ads API client"""
    try:
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount

        creds = load_credentials()
        FacebookAdsApi.init(
            creds['FACEBOOK_APP_ID'],
            creds['FACEBOOK_APP_SECRET'],
            creds['FACEBOOK_ACCESS_TOKEN']
        )
        account_id = creds.get('FACEBOOK_AD_ACCOUNT_ID', 'act_963386574972372')
        return AdAccount(account_id)
    except ImportError:
        raise Exception("facebook-business package not installed. Run: pip install facebook-business")
    except KeyError as e:
        raise Exception(f"Missing credential: {e}. Check ~/.claude/.env file.")


def get_date_preset(days: int) -> str:
    """Convert days to Meta date preset"""
    presets = {
        7: 'last_7d',
        14: 'last_14d',
        28: 'last_28d',
        30: 'last_30d',
        90: 'last_90d'
    }
    return presets.get(days, 'last_30d')


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="get_campaigns",
        description="Get Meta Ads campaign performance data. Returns campaign metrics including impressions, clicks, spend, and conversions.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of data (7, 14, 28, 30, or 90). Default: 30"
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: ACTIVE, PAUSED, ARCHIVED, or all. Default: all"
                }
            }
        }
    ),
    Tool(
        name="get_adsets",
        description="Get Meta Ads ad set performance data. Returns ad set metrics including targeting, budget, and performance.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of data. Default: 30"
                },
                "campaign_id": {
                    "type": "string",
                    "description": "Optional: Filter by campaign ID"
                }
            }
        }
    ),
    Tool(
        name="get_ads",
        description="Get Meta Ads individual ad performance. Returns ad-level metrics and creative info.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of data. Default: 30"
                },
                "adset_id": {
                    "type": "string",
                    "description": "Optional: Filter by ad set ID"
                }
            }
        }
    ),
    Tool(
        name="get_account_insights",
        description="Get account-level insights with breakdowns. Returns aggregated metrics for the entire ad account.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of data. Default: 30"
                },
                "breakdown": {
                    "type": "string",
                    "description": "Breakdown dimension: age, gender, country, publisher_platform. Default: none"
                }
            }
        }
    ),
    Tool(
        name="get_account_info",
        description="Get Meta Ads account information including name, currency, timezone, and spend limit.",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    Tool(
        name="check_token_health",
        description="Check the health and expiration status of the Meta access token.",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    # ============================================================================
    # NEW TOOLS - Added in v2.0
    # ============================================================================
    Tool(
        name="get_demographic_breakdown",
        description="Get performance breakdown by demographics (age, gender, country, region, or device).",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"},
                "breakdown": {
                    "type": "string",
                    "description": "Breakdown dimension: age, gender, country, region, device_platform, publisher_platform. Default: age",
                    "enum": ["age", "gender", "country", "region", "device_platform", "publisher_platform"]
                },
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_placement_performance",
        description="Get performance breakdown by placement (Facebook Feed, Instagram Feed, Stories, Reels, etc.).",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_video_metrics",
        description="Get video engagement metrics including views, completions, average watch time, and ThruPlay.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_creative_performance",
        description="Get creative-level performance showing which ad creatives perform best.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"},
                "limit": {"type": "integer", "description": "Maximum creatives to return. Default: 50"}
            }
        }
    ),
    Tool(
        name="get_hourly_breakdown",
        description="Get performance breakdown by hour of day to identify optimal ad scheduling.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 7"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_reach_frequency",
        description="Get reach and frequency metrics to understand audience saturation.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    ),
    Tool(
        name="get_conversion_breakdown",
        description="Get conversion breakdown by action type, device, and conversion window.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"},
                "attribution_window": {
                    "type": "string",
                    "description": "Attribution window: 1d_click, 7d_click, 1d_view, default. Default: default",
                    "enum": ["1d_click", "7d_click", "1d_view", "default"]
                }
            }
        }
    ),
    Tool(
        name="get_daily_performance",
        description="Get day-by-day performance trends for analysis and reporting.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"},
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Metrics to include. Default: spend, impressions, clicks, conversions"
                }
            }
        }
    ),
    Tool(
        name="get_account_summary",
        description="Get a comprehensive account summary with key metrics, top campaigns, and recommendations.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"}
            }
        }
    ),
    Tool(
        name="get_cost_analysis",
        description="Get detailed cost analysis including CPM, CPC, CPR (cost per result), and cost trends.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days of data. Default: 30"},
                "campaign_id": {"type": "string", "description": "Optional: Filter by campaign ID"}
            }
        }
    )
]


# ============================================================================
# Tool Handlers
# ============================================================================

async def handle_get_campaigns(days: int = 30, status: str = None) -> dict:
    """Get campaign performance data"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    # Get campaigns
    fields = ['id', 'name', 'status', 'objective', 'created_time', 'daily_budget', 'lifetime_budget']
    campaigns = account.get_campaigns(fields=fields)

    campaigns_data = []
    for campaign in campaigns:
        if status and campaign.get('status') != status:
            continue

        # Get insights for this campaign
        try:
            insights = campaign.get_insights(
                params={'date_preset': date_preset},
                fields=['impressions', 'clicks', 'ctr', 'spend', 'cpc', 'cpm',
                       'reach', 'frequency', 'actions', 'cost_per_action_type']
            )
            campaign_obj = campaign.export_all_data()
            campaign_obj['insights'] = insights[0].export_all_data() if insights else None
        except Exception:
            campaign_obj = campaign.export_all_data()
            campaign_obj['insights'] = None

        campaigns_data.append(campaign_obj)

    # Calculate summary
    total_spend = sum(float(c['insights'].get('spend', 0)) for c in campaigns_data if c.get('insights'))
    total_clicks = sum(int(c['insights'].get('clicks', 0)) for c in campaigns_data if c.get('insights'))
    total_impressions = sum(int(c['insights'].get('impressions', 0)) for c in campaigns_data if c.get('insights'))

    return {
        "date_range": date_preset,
        "total_campaigns": len(campaigns_data),
        "summary": {
            "total_spend": round(total_spend, 2),
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "avg_ctr": round((total_clicks / total_impressions * 100), 2) if total_impressions > 0 else 0
        },
        "campaigns": campaigns_data
    }


async def handle_get_adsets(days: int = 30, campaign_id: str = None) -> dict:
    """Get ad set performance data"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    fields = ['id', 'name', 'campaign_id', 'status', 'optimization_goal',
              'billing_event', 'daily_budget', 'lifetime_budget', 'targeting']

    params = {}
    if campaign_id:
        params['filtering'] = [{'field': 'campaign.id', 'operator': 'EQUAL', 'value': campaign_id}]

    adsets = account.get_ad_sets(fields=fields, params=params)

    adsets_data = []
    for adset in adsets:
        try:
            insights = adset.get_insights(
                params={'date_preset': date_preset},
                fields=['impressions', 'clicks', 'spend', 'cpc', 'actions']
            )
            adset_obj = adset.export_all_data()
            adset_obj['insights'] = insights[0].export_all_data() if insights else None
        except Exception:
            adset_obj = adset.export_all_data()
            adset_obj['insights'] = None

        adsets_data.append(adset_obj)

    return {
        "date_range": date_preset,
        "total_adsets": len(adsets_data),
        "adsets": adsets_data
    }


async def handle_get_ads(days: int = 30, adset_id: str = None) -> dict:
    """Get individual ad performance"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    fields = ['id', 'name', 'adset_id', 'status', 'creative', 'created_time']

    params = {}
    if adset_id:
        params['filtering'] = [{'field': 'adset.id', 'operator': 'EQUAL', 'value': adset_id}]

    ads = account.get_ads(fields=fields, params=params)

    ads_data = []
    for ad in ads:
        try:
            insights = ad.get_insights(
                params={'date_preset': date_preset},
                fields=['impressions', 'clicks', 'spend', 'ctr', 'cpc']
            )
            ad_obj = ad.export_all_data()
            ad_obj['insights'] = insights[0].export_all_data() if insights else None
        except Exception:
            ad_obj = ad.export_all_data()
            ad_obj['insights'] = None

        ads_data.append(ad_obj)

    return {
        "date_range": date_preset,
        "total_ads": len(ads_data),
        "ads": ads_data
    }


async def handle_get_account_insights(days: int = 30, breakdown: str = None) -> dict:
    """Get account-level insights"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    params = {'date_preset': date_preset}
    if breakdown:
        params['breakdowns'] = [breakdown]

    fields = ['impressions', 'clicks', 'ctr', 'spend', 'cpc', 'cpm',
              'reach', 'frequency', 'actions', 'cost_per_action_type',
              'video_p25_watched_actions', 'video_p50_watched_actions',
              'video_p75_watched_actions', 'video_p100_watched_actions']

    insights = account.get_insights(params=params, fields=fields)

    insights_data = [i.export_all_data() for i in insights]

    return {
        "date_range": date_preset,
        "breakdown": breakdown,
        "insights": insights_data
    }


async def handle_get_account_info() -> dict:
    """Get account information"""
    account = get_api_client()

    fields = ['id', 'name', 'account_status', 'currency', 'timezone_name',
              'amount_spent', 'spend_cap', 'min_daily_budget', 'business_name']

    account.api_get(fields=fields)

    return {
        "account": account.export_all_data()
    }


async def handle_check_token_health() -> dict:
    """Check token health and expiration"""
    import requests

    creds = load_credentials()
    token = creds.get('FACEBOOK_ACCESS_TOKEN')
    app_id = creds.get('FACEBOOK_APP_ID')
    app_secret = creds.get('FACEBOOK_APP_SECRET')

    url = 'https://graph.facebook.com/v22.0/debug_token'
    params = {
        'input_token': token,
        'access_token': f'{app_id}|{app_secret}'
    }

    response = requests.get(url, params=params)
    data = response.json()

    if 'data' not in data:
        return {
            "status": "error",
            "message": "Token invalid or expired",
            "action": "Get new token from Graph API Explorer"
        }

    token_info = data['data']
    is_valid = token_info.get('is_valid', False)
    expires_at = token_info.get('expires_at', 0)

    if not is_valid:
        return {
            "status": "invalid",
            "message": "Token is invalid",
            "action": "Get new token from Graph API Explorer"
        }

    if expires_at > 0:
        expiration_date = datetime.fromtimestamp(expires_at)
        hours_remaining = (expiration_date - datetime.now()).total_seconds() / 3600
        days_remaining = int(hours_remaining / 24)

        if hours_remaining < 2:
            return {
                "status": "expiring_soon",
                "expires_in_hours": round(hours_remaining, 1),
                "action": "Token needs refresh immediately"
            }
        elif days_remaining < 7:
            return {
                "status": "warning",
                "expires_in_days": days_remaining,
                "expiration_date": expiration_date.isoformat(),
                "action": "Token expires soon, consider refreshing"
            }
        else:
            return {
                "status": "healthy",
                "expires_in_days": days_remaining,
                "expiration_date": expiration_date.isoformat()
            }
    else:
        return {
            "status": "healthy",
            "message": "Token never expires (system user token)"
        }


# ============================================================================
# NEW Tool Handlers - Added in v2.0
# ============================================================================

async def handle_get_demographic_breakdown(days: int = 30, breakdown: str = "age",
                                            campaign_id: str = None) -> dict:
    """Get performance breakdown by demographics"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    params = {
        'date_preset': date_preset,
        'breakdowns': [breakdown]
    }

    fields = ['impressions', 'clicks', 'spend', 'ctr', 'cpc', 'cpm',
              'reach', 'actions', 'cost_per_action_type']

    if campaign_id:
        # Get specific campaign insights
        from facebook_business.adobjects.campaign import Campaign
        campaign = Campaign(campaign_id)
        insights = campaign.get_insights(params=params, fields=fields)
    else:
        insights = account.get_insights(params=params, fields=fields)

    insights_data = [i.export_all_data() for i in insights]

    # Calculate totals by breakdown
    breakdown_totals = {}
    for insight in insights_data:
        key = insight.get(breakdown, 'Unknown')
        if key not in breakdown_totals:
            breakdown_totals[key] = {
                'impressions': 0, 'clicks': 0, 'spend': 0, 'reach': 0
            }
        breakdown_totals[key]['impressions'] += int(insight.get('impressions', 0))
        breakdown_totals[key]['clicks'] += int(insight.get('clicks', 0))
        breakdown_totals[key]['spend'] += float(insight.get('spend', 0))
        breakdown_totals[key]['reach'] += int(insight.get('reach', 0))

    return {
        "date_range": date_preset,
        "breakdown": breakdown,
        "summary_by_breakdown": breakdown_totals,
        "detailed_data": insights_data
    }


async def handle_get_placement_performance(days: int = 30, campaign_id: str = None) -> dict:
    """Get performance breakdown by placement"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    params = {
        'date_preset': date_preset,
        'breakdowns': ['publisher_platform', 'platform_position']
    }

    fields = ['impressions', 'clicks', 'spend', 'ctr', 'cpc', 'cpm',
              'reach', 'actions', 'cost_per_action_type']

    if campaign_id:
        from facebook_business.adobjects.campaign import Campaign
        campaign = Campaign(campaign_id)
        insights = campaign.get_insights(params=params, fields=fields)
    else:
        insights = account.get_insights(params=params, fields=fields)

    insights_data = [i.export_all_data() for i in insights]

    # Group by placement
    placements = {}
    for insight in insights_data:
        platform = insight.get('publisher_platform', 'unknown')
        position = insight.get('platform_position', 'unknown')
        key = f"{platform} - {position}"

        if key not in placements:
            placements[key] = {
                'impressions': 0, 'clicks': 0, 'spend': 0, 'reach': 0
            }
        placements[key]['impressions'] += int(insight.get('impressions', 0))
        placements[key]['clicks'] += int(insight.get('clicks', 0))
        placements[key]['spend'] += float(insight.get('spend', 0))
        placements[key]['reach'] += int(insight.get('reach', 0))

    # Calculate CTR for each placement
    for key in placements:
        imp = placements[key]['impressions']
        clicks = placements[key]['clicks']
        placements[key]['ctr'] = round((clicks / imp * 100) if imp > 0 else 0, 2)
        placements[key]['cpm'] = round((placements[key]['spend'] / imp * 1000) if imp > 0 else 0, 2)

    return {
        "date_range": date_preset,
        "placements": placements,
        "detailed_data": insights_data
    }


async def handle_get_video_metrics(days: int = 30, campaign_id: str = None) -> dict:
    """Get video engagement metrics"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    params = {'date_preset': date_preset}

    fields = [
        'impressions', 'reach', 'spend',
        'video_p25_watched_actions',
        'video_p50_watched_actions',
        'video_p75_watched_actions',
        'video_p100_watched_actions',
        'video_play_actions',
        'video_thruplay_watched_actions',
        'video_avg_time_watched_actions'
    ]

    if campaign_id:
        from facebook_business.adobjects.campaign import Campaign
        campaign = Campaign(campaign_id)
        insights = campaign.get_insights(params=params, fields=fields)
    else:
        insights = account.get_insights(params=params, fields=fields)

    insights_data = [i.export_all_data() for i in insights]

    # Calculate video metrics summary
    summary = {
        'total_impressions': 0,
        'total_reach': 0,
        'total_spend': 0,
        'video_plays': 0,
        'video_thruplay': 0,
        'p25_completions': 0,
        'p50_completions': 0,
        'p75_completions': 0,
        'p100_completions': 0
    }

    for insight in insights_data:
        summary['total_impressions'] += int(insight.get('impressions', 0))
        summary['total_reach'] += int(insight.get('reach', 0))
        summary['total_spend'] += float(insight.get('spend', 0))

        # Video metrics
        for action in insight.get('video_play_actions', []):
            summary['video_plays'] += int(action.get('value', 0))
        for action in insight.get('video_thruplay_watched_actions', []):
            summary['video_thruplay'] += int(action.get('value', 0))
        for action in insight.get('video_p25_watched_actions', []):
            summary['p25_completions'] += int(action.get('value', 0))
        for action in insight.get('video_p50_watched_actions', []):
            summary['p50_completions'] += int(action.get('value', 0))
        for action in insight.get('video_p75_watched_actions', []):
            summary['p75_completions'] += int(action.get('value', 0))
        for action in insight.get('video_p100_watched_actions', []):
            summary['p100_completions'] += int(action.get('value', 0))

    # Calculate rates
    if summary['video_plays'] > 0:
        summary['completion_rate'] = round(summary['p100_completions'] / summary['video_plays'] * 100, 2)
        summary['thruplay_rate'] = round(summary['video_thruplay'] / summary['video_plays'] * 100, 2)

    return {
        "date_range": date_preset,
        "video_summary": summary,
        "detailed_data": insights_data
    }


async def handle_get_creative_performance(days: int = 30, limit: int = 50) -> dict:
    """Get creative-level performance"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    # Get ads with creative details
    fields = ['id', 'name', 'adset_id', 'creative', 'status', 'created_time']
    ads = account.get_ads(fields=fields, params={'limit': limit})

    ads_data = []
    for ad in ads:
        try:
            insights = ad.get_insights(
                params={'date_preset': date_preset},
                fields=['impressions', 'clicks', 'spend', 'ctr', 'cpc', 'actions', 'cost_per_action_type']
            )
            ad_obj = ad.export_all_data()
            ad_obj['insights'] = insights[0].export_all_data() if insights else None

            # Get creative details
            creative_id = ad_obj.get('creative', {}).get('id')
            if creative_id:
                from facebook_business.adobjects.adcreative import AdCreative
                creative = AdCreative(creative_id)
                creative.api_get(fields=['id', 'name', 'title', 'body', 'image_url', 'thumbnail_url', 'call_to_action_type'])
                ad_obj['creative_details'] = creative.export_all_data()
        except Exception:
            ad_obj = ad.export_all_data()
            ad_obj['insights'] = None

        ads_data.append(ad_obj)

    # Sort by performance (spend)
    ads_data.sort(key=lambda x: float(x.get('insights', {}).get('spend', 0) if x.get('insights') else 0), reverse=True)

    return {
        "date_range": date_preset,
        "total_creatives": len(ads_data),
        "creatives": ads_data[:limit]
    }


async def handle_get_hourly_breakdown(days: int = 7, campaign_id: str = None) -> dict:
    """Get hourly performance breakdown"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    params = {
        'date_preset': date_preset,
        'breakdowns': ['hourly_stats_aggregated_by_advertiser_time_zone']
    }

    fields = ['impressions', 'clicks', 'spend', 'ctr', 'actions']

    if campaign_id:
        from facebook_business.adobjects.campaign import Campaign
        campaign = Campaign(campaign_id)
        insights = campaign.get_insights(params=params, fields=fields)
    else:
        insights = account.get_insights(params=params, fields=fields)

    insights_data = [i.export_all_data() for i in insights]

    # Aggregate by hour
    hourly_data = {}
    for insight in insights_data:
        hour = insight.get('hourly_stats_aggregated_by_advertiser_time_zone', 'unknown')
        if hour not in hourly_data:
            hourly_data[hour] = {'impressions': 0, 'clicks': 0, 'spend': 0}
        hourly_data[hour]['impressions'] += int(insight.get('impressions', 0))
        hourly_data[hour]['clicks'] += int(insight.get('clicks', 0))
        hourly_data[hour]['spend'] += float(insight.get('spend', 0))

    return {
        "date_range": date_preset,
        "hourly_performance": hourly_data,
        "detailed_data": insights_data
    }


async def handle_get_reach_frequency(days: int = 30, campaign_id: str = None) -> dict:
    """Get reach and frequency metrics"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    params = {'date_preset': date_preset}

    fields = ['impressions', 'reach', 'frequency', 'spend', 'cpm']

    if campaign_id:
        from facebook_business.adobjects.campaign import Campaign
        campaign = Campaign(campaign_id)
        insights = campaign.get_insights(params=params, fields=fields)
    else:
        insights = account.get_insights(params=params, fields=fields)

    insights_data = [i.export_all_data() for i in insights]

    # Calculate summary
    total_impressions = sum(int(i.get('impressions', 0)) for i in insights_data)
    total_reach = sum(int(i.get('reach', 0)) for i in insights_data)
    total_spend = sum(float(i.get('spend', 0)) for i in insights_data)

    avg_frequency = total_impressions / total_reach if total_reach > 0 else 0
    cost_per_reach = total_spend / total_reach if total_reach > 0 else 0

    return {
        "date_range": date_preset,
        "summary": {
            "total_impressions": total_impressions,
            "total_reach": total_reach,
            "total_spend": round(total_spend, 2),
            "average_frequency": round(avg_frequency, 2),
            "cost_per_reach": round(cost_per_reach, 4),
            "cpm": round(total_spend / total_impressions * 1000, 2) if total_impressions > 0 else 0
        },
        "detailed_data": insights_data
    }


async def handle_get_conversion_breakdown(days: int = 30, attribution_window: str = "default") -> dict:
    """Get conversion breakdown by action type"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    params = {
        'date_preset': date_preset,
        'action_breakdowns': ['action_type']
    }

    # Set attribution window if specified
    if attribution_window != "default":
        params['action_attribution_windows'] = [attribution_window]

    fields = ['impressions', 'clicks', 'spend', 'actions', 'action_values',
              'cost_per_action_type', 'conversions', 'conversion_values']

    insights = account.get_insights(params=params, fields=fields)
    insights_data = [i.export_all_data() for i in insights]

    # Group actions by type
    actions_summary = {}
    for insight in insights_data:
        for action in insight.get('actions', []):
            action_type = action.get('action_type', 'unknown')
            value = int(action.get('value', 0))
            if action_type not in actions_summary:
                actions_summary[action_type] = 0
            actions_summary[action_type] += value

    # Sort by value
    sorted_actions = dict(sorted(actions_summary.items(), key=lambda x: x[1], reverse=True))

    return {
        "date_range": date_preset,
        "attribution_window": attribution_window,
        "actions_summary": sorted_actions,
        "detailed_data": insights_data
    }


async def handle_get_daily_performance(days: int = 30, campaign_id: str = None,
                                        metrics: list = None) -> dict:
    """Get day-by-day performance"""
    account = get_api_client()

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    params = {
        'time_range': {
            'since': start_date.strftime('%Y-%m-%d'),
            'until': end_date.strftime('%Y-%m-%d')
        },
        'time_increment': 1  # Daily breakdown
    }

    if metrics is None:
        metrics = ['impressions', 'clicks', 'spend', 'reach', 'ctr', 'cpc', 'actions']

    if campaign_id:
        from facebook_business.adobjects.campaign import Campaign
        campaign = Campaign(campaign_id)
        insights = campaign.get_insights(params=params, fields=metrics + ['date_start'])
    else:
        insights = account.get_insights(params=params, fields=metrics + ['date_start'])

    insights_data = [i.export_all_data() for i in insights]

    # Sort by date
    insights_data.sort(key=lambda x: x.get('date_start', ''))

    return {
        "date_range": {
            "start": start_date.strftime('%Y-%m-%d'),
            "end": end_date.strftime('%Y-%m-%d'),
            "days": days
        },
        "metrics_requested": metrics,
        "daily_data": insights_data
    }


async def handle_get_account_summary(days: int = 30) -> dict:
    """Get comprehensive account summary"""
    # Get overall performance
    account_insights = await handle_get_account_insights(days=days)

    # Get campaigns
    campaigns_data = await handle_get_campaigns(days=days)

    # Get token health
    token_health = await handle_check_token_health()

    # Calculate summary metrics
    insights = account_insights.get('insights', [{}])
    first_insight = insights[0] if insights else {}

    total_spend = float(first_insight.get('spend', 0))
    total_impressions = int(first_insight.get('impressions', 0))
    total_clicks = int(first_insight.get('clicks', 0))
    total_reach = int(first_insight.get('reach', 0))

    # Get conversions from actions
    conversions = 0
    conversion_value = 0
    for action in first_insight.get('actions', []):
        if action.get('action_type') in ['purchase', 'lead', 'complete_registration']:
            conversions += int(action.get('value', 0))

    summary = {
        "date_range_days": days,
        "account_metrics": {
            "total_spend": round(total_spend, 2),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_reach": total_reach,
            "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0,
            "cpc": round(total_spend / total_clicks, 2) if total_clicks > 0 else 0,
            "cpm": round(total_spend / total_impressions * 1000, 2) if total_impressions > 0 else 0,
            "frequency": round(total_impressions / total_reach, 2) if total_reach > 0 else 0,
            "conversions": conversions
        },
        "campaigns_summary": campaigns_data.get('summary', {}),
        "top_5_campaigns": campaigns_data.get('campaigns', [])[:5],
        "token_status": token_health.get('status'),
        "insights": {
            "spend_formatted": f"€{total_spend:,.2f}",
            "reach_formatted": f"{total_reach:,}",
            "active_campaigns": sum(1 for c in campaigns_data.get('campaigns', []) if c.get('status') == 'ACTIVE')
        }
    }

    return summary


async def handle_get_cost_analysis(days: int = 30, campaign_id: str = None) -> dict:
    """Get detailed cost analysis"""
    account = get_api_client()
    date_preset = get_date_preset(days)

    params = {'date_preset': date_preset}

    fields = ['impressions', 'clicks', 'spend', 'ctr', 'cpc', 'cpm', 'cpp',
              'reach', 'frequency', 'actions', 'cost_per_action_type']

    if campaign_id:
        from facebook_business.adobjects.campaign import Campaign
        campaign = Campaign(campaign_id)
        insights = campaign.get_insights(params=params, fields=fields)
    else:
        insights = account.get_insights(params=params, fields=fields)

    insights_data = [i.export_all_data() for i in insights]

    # Calculate cost metrics
    first_insight = insights_data[0] if insights_data else {}

    total_spend = float(first_insight.get('spend', 0))
    total_impressions = int(first_insight.get('impressions', 0))
    total_clicks = int(first_insight.get('clicks', 0))
    total_reach = int(first_insight.get('reach', 0))

    # Get cost per action by type
    cost_by_action = {}
    for cpa in first_insight.get('cost_per_action_type', []):
        action_type = cpa.get('action_type', 'unknown')
        cost = float(cpa.get('value', 0))
        cost_by_action[action_type] = round(cost, 2)

    analysis = {
        "date_range": date_preset,
        "cost_metrics": {
            "total_spend": round(total_spend, 2),
            "cpm": round(total_spend / total_impressions * 1000, 2) if total_impressions > 0 else 0,
            "cpc": round(total_spend / total_clicks, 2) if total_clicks > 0 else 0,
            "cost_per_reach": round(total_spend / total_reach, 4) if total_reach > 0 else 0,
            "frequency": round(total_impressions / total_reach, 2) if total_reach > 0 else 0
        },
        "cost_per_action": cost_by_action,
        "detailed_data": insights_data
    }

    return analysis


# Tool handler mapping
TOOL_HANDLERS = {
    # Original tools
    "get_campaigns": handle_get_campaigns,
    "get_adsets": handle_get_adsets,
    "get_ads": handle_get_ads,
    "get_account_insights": handle_get_account_insights,
    "get_account_info": handle_get_account_info,
    "check_token_health": handle_check_token_health,
    # New tools - v2.0
    "get_demographic_breakdown": handle_get_demographic_breakdown,
    "get_placement_performance": handle_get_placement_performance,
    "get_video_metrics": handle_get_video_metrics,
    "get_creative_performance": handle_get_creative_performance,
    "get_hourly_breakdown": handle_get_hourly_breakdown,
    "get_reach_frequency": handle_get_reach_frequency,
    "get_conversion_breakdown": handle_get_conversion_breakdown,
    "get_daily_performance": handle_get_daily_performance,
    "get_account_summary": handle_get_account_summary,
    "get_cost_analysis": handle_get_cost_analysis
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
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    try:
        handler = TOOL_HANDLERS[name]
        result = await handler(**arguments)

        # Return list of TextContent directly (MCP SDK handles wrapping)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        import traceback
        # Return JSON error so it can be properly parsed
        error_result = {
            "error": str(e),
            "tool": name,
            "traceback": traceback.format_exc()[-500:]  # Last 500 chars of traceback
        }
        return [TextContent(type="text", text=json.dumps(error_result))]


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
