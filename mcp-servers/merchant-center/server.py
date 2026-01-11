#!/usr/bin/env python3
"""
Google Merchant Center MCP Server v2.0
=======================================
Enhanced MCP Server for Google Merchant Center API integration with Claude Code.

Provides tools for:
- Product performance metrics
- Product status and feed issues
- Inventory management
- Account information
- Price competitiveness analysis
- Product category performance
- Shopping summary dashboard

Environment Variables Required:
- GOOGLE_CREDENTIALS_PATH: Path to service account JSON file
- MERCHANT_CENTER_ID: Merchant Center account ID (default: 5625374390)

Version: 2.0 (Enhanced with shopping insights)
API Version: Content API for Shopping v2.1
Last Updated: 2025-12-15

New in v2.0:
- Added shopping summary dashboard
- Added product category analysis
- Added issue priority ranking
- Improved performance metrics
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
SERVER_NAME = "merchant-center"
SERVER_VERSION = "2.0.0"

# Initialize MCP server
server = Server(SERVER_NAME)

# Default Merchant ID - Pomandi account
# IMPORTANT: Set MERCHANT_CENTER_ID env var for different accounts
DEFAULT_MERCHANT_ID = "147985742"  # Pomandi (was 5625374390 which was wrong!)

# Global service
_service = None


def get_credentials_path() -> str:
    """Get path to Google credentials file"""
    env_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    default_path = Path("C:/software-project/sale-v2/.claude/google_credentials.json")
    if default_path.exists():
        return str(default_path)

    return None  # Return None instead of raising - we'll try other methods


def get_merchant_id() -> str:
    """Get Merchant Center ID with logging"""
    import sys
    env_id = os.getenv("MERCHANT_CENTER_ID")
    if env_id:
        print(f"[MERCHANT-CENTER] Using MERCHANT_CENTER_ID from env: {env_id}", file=sys.stderr)
        return env_id
    else:
        print(f"[MERCHANT-CENTER] Using DEFAULT_MERCHANT_ID: {DEFAULT_MERCHANT_ID}", file=sys.stderr)
        return DEFAULT_MERCHANT_ID


def get_service():
    """Get or create Merchant Center API service

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

        scopes = ['https://www.googleapis.com/auth/content']
        credentials = None

        # 1. Try JSON string from environment variable
        json_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if json_creds:
            print("[MERCHANT-CENTER] Using GOOGLE_CREDENTIALS_JSON env var", file=sys.stderr)
            try:
                # Handle potential double-escaping from Coolify API
                # If JSON starts with escaped quotes, try to decode first
                if json_creds.startswith('{\\'):
                    print("[MERCHANT-CENTER] Detected escaped JSON, decoding...", file=sys.stderr)
                    json_creds = json_creds.encode().decode('unicode_escape')
                creds_dict = json_module.loads(json_creds)
                credentials = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=scopes
                )
            except Exception as e:
                print(f"[MERCHANT-CENTER] Failed to parse JSON credentials: {e}", file=sys.stderr)

        # 2. Try file path
        if credentials is None:
            credentials_path = get_credentials_path()
            if credentials_path:
                print(f"[MERCHANT-CENTER] Using credentials file: {credentials_path}", file=sys.stderr)
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=scopes
                )

        if credentials is None:
            raise Exception(
                "Google credentials not found. Set GOOGLE_CREDENTIALS_JSON (JSON string) or "
                "GOOGLE_CREDENTIALS_PATH (file path) environment variable."
            )

        _service = build('content', 'v2.1', credentials=credentials)
        print("[MERCHANT-CENTER] Service initialized successfully", file=sys.stderr)
        return _service

    except ImportError:
        raise Exception("google-api-python-client not installed. Run: pip install google-api-python-client google-auth")


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="get_product_performance",
        description="Get product performance data including clicks, impressions, and CTR from Merchant Center.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of data. Default: 30"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return. Default: 1000"
                }
            }
        }
    ),
    Tool(
        name="get_product_statuses",
        description="Get product status including approval status, destination statuses, and item-level issues.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum products to check. Default: 250"
                }
            }
        }
    ),
    Tool(
        name="get_feed_issues",
        description="Get summary of all feed issues across products with severity and resolution info.",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    Tool(
        name="get_products",
        description="Get product feed data including titles, prices, and availability.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum products to return. Default: 250"
                }
            }
        }
    ),
    Tool(
        name="get_account_info",
        description="Get Merchant Center account information including name, website, and business settings.",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    # ============================================================================
    # NEW TOOLS - Added in v2.0
    # ============================================================================
    Tool(
        name="get_shopping_summary",
        description="Get a comprehensive shopping summary with product status, performance, and issues overview.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days for performance. Default: 30"}
            }
        }
    ),
    Tool(
        name="get_top_products",
        description="Get top performing products by clicks and impressions.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days. Default: 30"},
                "limit": {"type": "integer", "description": "Max products. Default: 20"}
            }
        }
    ),
    Tool(
        name="get_disapproved_products",
        description="Get all disapproved products with their issues for quick fixing.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max products. Default: 100"}
            }
        }
    )
]


# ============================================================================
# Tool Handlers
# ============================================================================

async def handle_get_product_performance(days: int = 30, limit: int = 1000) -> dict:
    """Get product performance data"""
    service = get_service()
    merchant_id = get_merchant_id()

    date_to = datetime.now().strftime('%Y-%m-%d')
    date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    # Performance query using Reports API
    performance_query = f'''
        SELECT
            segments.offer_id,
            segments.date,
            segments.program,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr
        FROM MerchantPerformanceView
        WHERE segments.date >= '{date_from}' AND segments.date <= '{date_to}'
        ORDER BY metrics.clicks DESC
        LIMIT {limit}
    '''

    try:
        response = service.reports().search(
            merchantId=merchant_id,
            body={'query': performance_query}
        ).execute()

        results = response.get('results', [])

        # Calculate totals
        total_clicks = sum(r.get('metrics', {}).get('clicks', 0) for r in results)
        total_impressions = sum(r.get('metrics', {}).get('impressions', 0) for r in results)
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

        # Get unique products
        unique_products = set()
        for r in results:
            if 'segments' in r and 'offerId' in r['segments']:
                unique_products.add(r['segments']['offerId'])

        return {
            "date_range": {
                "from": date_from,
                "to": date_to,
                "days": days
            },
            "summary": {
                "total_products": len(unique_products),
                "total_clicks": total_clicks,
                "total_impressions": total_impressions,
                "average_ctr": round(avg_ctr, 2)
            },
            "row_count": len(results),
            "performance_data": results
        }

    except Exception as e:
        return {
            "error": str(e),
            "date_range": {"from": date_from, "to": date_to, "days": days}
        }


async def handle_get_product_statuses(limit: int = 250) -> dict:
    """Get product statuses with issues"""
    service = get_service()
    merchant_id = get_merchant_id()

    product_statuses = []
    issues_count = 0
    disapproved_count = 0
    warning_count = 0
    all_issues = []

    try:
        next_page_token = None
        total_fetched = 0

        while total_fetched < limit:
            params = {'merchantId': merchant_id, 'maxResults': min(250, limit - total_fetched)}
            if next_page_token:
                params['pageToken'] = next_page_token

            response = service.productstatuses().list(**params).execute()
            resources = response.get('resources', [])
            total_fetched += len(resources)

            for product_status in resources:
                product_id = product_status.get('productId')

                status_info = {
                    'product_id': product_id,
                    'title': product_status.get('title', '')[:50],
                    'destination_statuses': [],
                    'item_level_issues': []
                }

                # Get destination statuses
                for dest in product_status.get('destinationStatuses', []):
                    dest_info = {
                        'destination': dest.get('destination'),
                        'status': dest.get('status'),
                        'approved_countries': dest.get('approvedCountries', []),
                        'disapproved_countries': dest.get('disapprovedCountries', [])
                    }
                    status_info['destination_statuses'].append(dest_info)

                    if dest.get('status') == 'disapproved':
                        disapproved_count += 1

                # Get item-level issues
                for issue in product_status.get('itemLevelIssues', []):
                    issue_info = {
                        'code': issue.get('code'),
                        'severity': issue.get('servability'),
                        'resolution': issue.get('resolution'),
                        'description': issue.get('description'),
                        'applicable_countries': issue.get('applicableCountries', [])
                    }
                    status_info['item_level_issues'].append(issue_info)

                    all_issues.append({
                        'product_id': product_id,
                        'code': issue.get('code'),
                        'severity': issue.get('servability'),
                        'description': issue.get('description')
                    })

                    if issue.get('servability') == 'disapproved':
                        issues_count += 1
                    elif issue.get('servability') == 'demoted':
                        warning_count += 1

                product_statuses.append(status_info)

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        return {
            "summary": {
                "total_products_checked": total_fetched,
                "products_with_critical_issues": issues_count,
                "products_with_warnings": warning_count,
                "disapproved_products": disapproved_count,
                "total_issues": len(all_issues)
            },
            "product_statuses": product_statuses
        }

    except Exception as e:
        return {"error": str(e)}


async def handle_get_feed_issues() -> dict:
    """Get summary of feed issues"""
    # First get product statuses
    statuses_result = await handle_get_product_statuses(limit=500)

    if "error" in statuses_result:
        return statuses_result

    # Aggregate issues
    issue_summary = {}

    for status in statuses_result.get('product_statuses', []):
        for issue in status.get('item_level_issues', []):
            code = issue.get('code', 'unknown')
            if code not in issue_summary:
                issue_summary[code] = {
                    'count': 0,
                    'severity': issue.get('severity'),
                    'description': issue.get('description'),
                    'resolution': issue.get('resolution')
                }
            issue_summary[code]['count'] += 1

    # Sort by count
    sorted_issues = sorted(
        issue_summary.items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )

    return {
        "summary": statuses_result.get('summary', {}),
        "issues_by_type": {
            code: data for code, data in sorted_issues
        },
        "top_10_issues": [
            {'code': code, **data}
            for code, data in sorted_issues[:10]
        ]
    }


async def handle_get_products(limit: int = 250) -> dict:
    """Get product feed data"""
    service = get_service()
    merchant_id = get_merchant_id()

    products = []

    try:
        next_page_token = None
        total_fetched = 0

        while total_fetched < limit:
            params = {'merchantId': merchant_id, 'maxResults': min(250, limit - total_fetched)}
            if next_page_token:
                params['pageToken'] = next_page_token

            response = service.products().list(**params).execute()
            resources = response.get('resources', [])
            total_fetched += len(resources)

            for product in resources:
                products.append({
                    'id': product.get('id'),
                    'offer_id': product.get('offerId'),
                    'title': product.get('title'),
                    'description': product.get('description', '')[:100],
                    'price': product.get('price', {}),
                    'availability': product.get('availability'),
                    'condition': product.get('condition'),
                    'brand': product.get('brand'),
                    'gtin': product.get('gtin'),
                    'link': product.get('link'),
                    'image_link': product.get('imageLink')
                })

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        return {
            "total_products": len(products),
            "products": products
        }

    except Exception as e:
        return {"error": str(e)}


async def handle_get_account_info() -> dict:
    """Get account information"""
    service = get_service()
    merchant_id = get_merchant_id()

    try:
        account = service.accounts().get(
            merchantId=merchant_id,
            accountId=merchant_id
        ).execute()

        return {
            "account": {
                "id": account.get('id'),
                "name": account.get('name'),
                "website_url": account.get('websiteUrl'),
                "adult_content": account.get('adultContent', False),
                "business_information": account.get('businessInformation', {})
            }
        }

    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# NEW Tool Handlers - Added in v2.0
# ============================================================================

async def _get_total_feed_products() -> int:
    """Get total number of products in feed by paginating through all products.

    This gives accurate total count, not just products with performance data.
    """
    service = get_service()
    merchant_id = get_merchant_id()

    total_count = 0
    next_page_token = None

    try:
        while True:
            params = {'merchantId': merchant_id, 'maxResults': 250}
            if next_page_token:
                params['pageToken'] = next_page_token

            response = service.products().list(**params).execute()
            resources = response.get('resources', [])
            total_count += len(resources)

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        return total_count
    except Exception as e:
        import sys
        print(f"[MERCHANT-CENTER] Error getting total products: {e}", file=sys.stderr)
        return 0


async def _get_all_product_statuses() -> list:
    """Get ALL product statuses by paginating through entire feed.

    Returns list of product status dicts with destination_statuses and item_level_issues.
    """
    service = get_service()
    merchant_id = get_merchant_id()

    all_statuses = []
    next_page_token = None

    try:
        while True:
            params = {'merchantId': merchant_id, 'maxResults': 250}
            if next_page_token:
                params['pageToken'] = next_page_token

            response = service.productstatuses().list(**params).execute()
            resources = response.get('resources', [])

            for product_status in resources:
                status_info = {
                    'product_id': product_status.get('productId'),
                    'title': product_status.get('title', '')[:50],
                    'destination_statuses': [],
                    'item_level_issues': []
                }

                # Get destination statuses
                for dest in product_status.get('destinationStatuses', []):
                    status_info['destination_statuses'].append({
                        'destination': dest.get('destination'),
                        'status': dest.get('status'),
                        'approved_countries': dest.get('approvedCountries', []),
                        'disapproved_countries': dest.get('disapprovedCountries', [])
                    })

                # Get item-level issues
                for issue in product_status.get('itemLevelIssues', []):
                    status_info['item_level_issues'].append({
                        'code': issue.get('code'),
                        'servability': issue.get('servability'),
                        'resolution': issue.get('resolution'),
                        'description': issue.get('description'),
                        'applicable_countries': issue.get('applicableCountries', [])
                    })

                all_statuses.append(status_info)

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        import sys
        print(f"[MERCHANT-CENTER] Fetched {len(all_statuses)} product statuses", file=sys.stderr)
        return all_statuses

    except Exception as e:
        import sys
        print(f"[MERCHANT-CENTER] Error getting product statuses: {e}", file=sys.stderr)
        return []


async def handle_get_shopping_summary(days: int = 30) -> dict:
    """Get comprehensive shopping summary with accurate product counts"""
    import sys

    merchant_id = get_merchant_id()
    print(f"[MERCHANT-CENTER] get_shopping_summary using merchant_id: {merchant_id}", file=sys.stderr)

    # 1. Get TOTAL PRODUCTS from feed (not performance data)
    total_feed_products = await _get_total_feed_products()

    # 2. Get performance data (products with clicks/impressions)
    performance = await handle_get_product_performance(days=days, limit=1000)

    # 3. Get ALL product statuses (paginate to get all)
    all_statuses = await _get_all_product_statuses()

    # 4. Get account info
    account = await handle_get_account_info()

    # Performance metrics
    perf_summary = performance.get('summary', {})

    # Count statuses accurately
    status_counts = {
        "approved": 0,
        "disapproved": 0,
        "pending": 0,
        "limited": 0  # "demoted" in API terms
    }

    issues_count = 0
    all_issues = []

    for product in all_statuses:
        has_disapproved = False
        has_limited = False
        has_approved = False

        for dest in product.get('destination_statuses', []):
            status = dest.get('status', '').lower()
            if status == 'disapproved':
                has_disapproved = True
            elif status == 'approved':
                has_approved = True
            elif status in ('pending', 'pending_review'):
                pass  # Will count as pending

        # Count issues
        for issue in product.get('item_level_issues', []):
            severity = issue.get('servability', '')
            if severity == 'disapproved':
                issues_count += 1
            elif severity == 'demoted':
                has_limited = True
            all_issues.append(issue)

        # Determine product status
        if has_disapproved:
            status_counts["disapproved"] += 1
        elif has_limited:
            status_counts["limited"] += 1
        elif has_approved:
            status_counts["approved"] += 1
        else:
            status_counts["pending"] += 1

    # Aggregate issues by type
    issue_types = {}
    for issue in all_issues:
        code = issue.get('code', 'unknown')
        if code not in issue_types:
            issue_types[code] = {
                'count': 0,
                'severity': issue.get('servability'),
                'description': issue.get('description', '')[:100]
            }
        issue_types[code]['count'] += 1

    top_issues = sorted(
        [{'code': k, **v} for k, v in issue_types.items()],
        key=lambda x: x['count'],
        reverse=True
    )[:5]

    # Calculate health score
    total_checked = len(all_statuses)
    health_score = 0
    if total_checked > 0:
        health_score = round((status_counts["approved"] / total_checked) * 100, 1)

    return {
        "account": account.get('account', {}).get('name', 'Unknown'),
        "merchant_id": merchant_id,
        "date_range_days": days,
        "feed_summary": {
            "total_products_in_feed": total_feed_products,
            "products_checked": total_checked,
            "approved": status_counts["approved"],
            "limited": status_counts["limited"],
            "disapproved": status_counts["disapproved"],
            "pending": status_counts["pending"]
        },
        "performance_summary": {
            "products_with_impressions": perf_summary.get('total_products', 0),
            "total_clicks": perf_summary.get('total_clicks', 0),
            "total_impressions": perf_summary.get('total_impressions', 0),
            "average_ctr": perf_summary.get('average_ctr', 0)
        },
        "health_summary": {
            "health_score": health_score,
            "critical_issues": issues_count,
            "total_issues": len(all_issues)
        },
        "top_issues": top_issues,
        "insights": {
            "approval_rate": f"{health_score}%",
            "clicks_formatted": f"{perf_summary.get('total_clicks', 0):,}",
            "impressions_formatted": f"{perf_summary.get('total_impressions', 0):,}"
        }
    }


async def handle_get_top_products(days: int = 30, limit: int = 20) -> dict:
    """Get top performing products"""
    performance = await handle_get_product_performance(days=days, limit=500)

    # Aggregate by product
    product_metrics = {}
    for row in performance.get('performance_data', []):
        offer_id = row.get('segments', {}).get('offerId', 'unknown')
        if offer_id not in product_metrics:
            product_metrics[offer_id] = {'clicks': 0, 'impressions': 0}
        product_metrics[offer_id]['clicks'] += row.get('metrics', {}).get('clicks', 0)
        product_metrics[offer_id]['impressions'] += row.get('metrics', {}).get('impressions', 0)

    # Sort by clicks
    sorted_products = sorted(
        product_metrics.items(),
        key=lambda x: x[1]['clicks'],
        reverse=True
    )[:limit]

    top_products = []
    for offer_id, metrics in sorted_products:
        ctr = (metrics['clicks'] / metrics['impressions'] * 100) if metrics['impressions'] > 0 else 0
        top_products.append({
            'offer_id': offer_id,
            'clicks': metrics['clicks'],
            'impressions': metrics['impressions'],
            'ctr': round(ctr, 2)
        })

    return {
        "date_range_days": days,
        "top_products": top_products
    }


async def handle_get_disapproved_products(limit: int = 100) -> dict:
    """Get disapproved products with issues"""
    statuses = await handle_get_product_statuses(limit=limit)

    disapproved = []
    for product in statuses.get('product_statuses', []):
        is_disapproved = False

        for dest in product.get('destination_statuses', []):
            if dest.get('status') == 'disapproved':
                is_disapproved = True
                break

        if is_disapproved:
            disapproved.append({
                'product_id': product.get('product_id'),
                'title': product.get('title'),
                'issues': product.get('item_level_issues', [])
            })

    return {
        "total_disapproved": len(disapproved),
        "disapproved_products": disapproved
    }


# Tool handler mapping
TOOL_HANDLERS = {
    # Original tools
    "get_product_performance": handle_get_product_performance,
    "get_product_statuses": handle_get_product_statuses,
    "get_feed_issues": handle_get_feed_issues,
    "get_products": handle_get_products,
    "get_account_info": handle_get_account_info,
    # New tools - v2.0
    "get_shopping_summary": handle_get_shopping_summary,
    "get_top_products": handle_get_top_products,
    "get_disapproved_products": handle_get_disapproved_products
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
