#!/usr/bin/env python3
"""
Shopify MCP Server v2.0
========================
Enhanced MCP Server for Shopify Admin API integration with Claude Code.

Provides tools for:
- Order data and analytics
- Product information and inventory
- Customer data
- Abandoned checkouts
- Sales analytics
- Daily revenue trends
- Customer lifetime value
- Conversion funnel analysis
- Store summary dashboard

Environment Variables Required:
- SHOPIFY_ACCESS_TOKEN: Shopify Admin API access token
- SHOPIFY_STORE_NAME: Store name (e.g., papyon-fashion)

Version: 2.0 (Enhanced with e-commerce insights)
API Version: 2024-01
Last Updated: 2025-12-15

New in v2.0:
- Added store summary dashboard
- Added daily revenue trends
- Added customer cohort analysis
- Added fulfillment tracking
- Improved sales analytics
"""

import asyncio
import json
import os
from typing import Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import requests

# Server info
SERVER_NAME = "shopify"
SERVER_VERSION = "2.0.0"
API_VERSION = "2024-10"

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


def get_shopify_client():
    """Get Shopify API configuration"""
    creds = load_credentials()
    store = creds.get('SHOPIFY_STORE_NAME', 'papyon-fashion')
    token = creds.get('SHOPIFY_ACCESS_TOKEN')

    if not token:
        raise Exception("SHOPIFY_ACCESS_TOKEN not found in ~/.claude/.env")

    return {
        "base_url": f"https://{store}.myshopify.com/admin/api/{API_VERSION}",
        "headers": {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json"
        }
    }


def shopify_get(endpoint: str, params: dict = None) -> dict:
    """Make GET request to Shopify API"""
    client = get_shopify_client()
    url = f"{client['base_url']}/{endpoint}"
    response = requests.get(url, headers=client['headers'], params=params or {})

    if response.status_code != 200:
        raise Exception(f"Shopify API error: {response.status_code} - {response.text}")

    return response.json()


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="get_orders",
        description="Get Shopify orders with details including line items, payment status, and fulfillment status.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of order history. Default: 30"
                },
                "status": {
                    "type": "string",
                    "description": "Order status filter: any, open, closed, cancelled. Default: any"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum orders to return. Default: 250"
                }
            }
        }
    ),
    Tool(
        name="get_products",
        description="Get Shopify products with variants, prices, and inventory levels.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum products to return. Default: 250"
                },
                "status": {
                    "type": "string",
                    "description": "Product status: active, archived, draft. Default: active"
                }
            }
        }
    ),
    Tool(
        name="get_customers",
        description="Get Shopify customer data including order counts and total spend.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum customers to return. Default: 250"
                }
            }
        }
    ),
    Tool(
        name="get_abandoned_checkouts",
        description="Get abandoned checkout data showing incomplete purchases.",
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
        name="get_inventory_levels",
        description="Get current inventory levels for all products/variants.",
        inputSchema={
            "type": "object",
            "properties": {
                "low_stock_threshold": {
                    "type": "integer",
                    "description": "Threshold for low stock alert. Default: 10"
                }
            }
        }
    ),
    Tool(
        name="get_sales_analytics",
        description="Get sales analytics including revenue, AOV, and top products.",
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
        name="get_shop_info",
        description="Get Shopify store information including name, domain, and settings.",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    # ============================================================================
    # NEW TOOLS - Added in v2.0
    # ============================================================================
    Tool(
        name="get_store_summary",
        description="Get a comprehensive store summary with sales, orders, customers, and inventory health.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days. Default: 30"}
            }
        }
    ),
    Tool(
        name="get_daily_revenue",
        description="Get daily revenue breakdown for trend analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days. Default: 30"}
            }
        }
    ),
    Tool(
        name="get_fulfillment_status",
        description="Get fulfillment status of recent orders (unfulfilled, partially fulfilled, fulfilled).",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days. Default: 7"}
            }
        }
    )
]


# ============================================================================
# Tool Handlers
# ============================================================================

async def handle_get_orders(days: int = 30, status: str = "any", limit: int = 250) -> dict:
    """Get orders with details"""
    date_from = datetime.now() - timedelta(days=days)
    date_to = datetime.now()

    params = {
        "status": status,
        "created_at_min": date_from.isoformat(),
        "created_at_max": date_to.isoformat(),
        "limit": min(limit, 250)
    }

    data = shopify_get("orders.json", params)
    orders = data.get('orders', [])

    # Calculate summary
    total_revenue = sum(float(o.get('total_price', 0)) for o in orders)
    completed_orders = [o for o in orders if o.get('financial_status') == 'paid']
    avg_order_value = total_revenue / len(orders) if orders else 0

    return {
        "date_range": {
            "from": date_from.strftime("%Y-%m-%d"),
            "to": date_to.strftime("%Y-%m-%d"),
            "days": days
        },
        "summary": {
            "total_orders": len(orders),
            "completed_orders": len(completed_orders),
            "total_revenue": round(total_revenue, 2),
            "average_order_value": round(avg_order_value, 2),
            "currency": orders[0].get('currency') if orders else 'EUR'
        },
        "orders": orders
    }


async def handle_get_products(limit: int = 250, status: str = "active") -> dict:
    """Get products with variants"""
    params = {
        "limit": min(limit, 250),
        "status": status
    }

    data = shopify_get("products.json", params)
    products = data.get('products', [])

    # Count variants
    total_variants = sum(len(p.get('variants', [])) for p in products)

    return {
        "summary": {
            "total_products": len(products),
            "total_variants": total_variants,
            "status_filter": status
        },
        "products": products
    }


async def handle_get_customers(limit: int = 250) -> dict:
    """Get customer data"""
    params = {"limit": min(limit, 250)}

    data = shopify_get("customers.json", params)
    customers = data.get('customers', [])

    # Analyze customer behavior
    new_customers = [c for c in customers if c.get('orders_count', 0) == 1]
    repeat_customers = [c for c in customers if c.get('orders_count', 0) > 1]

    return {
        "summary": {
            "total_customers": len(customers),
            "new_customers": len(new_customers),
            "repeat_customers": len(repeat_customers),
            "repeat_rate": round(len(repeat_customers) / len(customers) * 100, 2) if customers else 0
        },
        "customers": customers
    }


async def handle_get_abandoned_checkouts(days: int = 30) -> dict:
    """Get abandoned checkouts"""
    date_from = datetime.now() - timedelta(days=days)

    params = {
        "created_at_min": date_from.isoformat(),
        "limit": 250
    }

    data = shopify_get("checkouts.json", params)
    checkouts = data.get('checkouts', [])

    # Calculate lost revenue
    lost_revenue = sum(float(c.get('total_price', 0)) for c in checkouts)

    return {
        "date_range_days": days,
        "summary": {
            "total_abandoned": len(checkouts),
            "lost_revenue": round(lost_revenue, 2)
        },
        "checkouts": checkouts
    }


async def handle_get_inventory_levels(low_stock_threshold: int = 10) -> dict:
    """Get inventory levels"""
    # First get products
    data = shopify_get("products.json", {"limit": 250})
    products = data.get('products', [])

    out_of_stock = []
    low_stock = []

    for product in products:
        for variant in product.get('variants', []):
            inventory = variant.get('inventory_quantity', 0)

            item = {
                'product_title': product.get('title'),
                'variant_title': variant.get('title'),
                'sku': variant.get('sku'),
                'inventory': inventory,
                'price': variant.get('price')
            }

            if inventory == 0:
                out_of_stock.append(item)
            elif inventory <= low_stock_threshold:
                low_stock.append(item)

    return {
        "threshold": low_stock_threshold,
        "summary": {
            "out_of_stock_count": len(out_of_stock),
            "low_stock_count": len(low_stock)
        },
        "out_of_stock": out_of_stock[:50],
        "low_stock": low_stock[:50]
    }


async def handle_get_sales_analytics(days: int = 30) -> dict:
    """Get sales analytics"""
    # Get orders for the period
    orders_data = await handle_get_orders(days=days)
    orders = orders_data.get('orders', [])

    # Product performance analysis
    product_sales = defaultdict(lambda: {'quantity': 0, 'revenue': 0, 'orders': 0})

    for order in orders:
        for item in order.get('line_items', []):
            product_id = item.get('product_id')
            if product_id:
                product_sales[product_id]['quantity'] += item.get('quantity', 0)
                product_sales[product_id]['revenue'] += float(item.get('price', 0)) * item.get('quantity', 0)
                product_sales[product_id]['orders'] += 1
                if 'title' not in product_sales[product_id]:
                    product_sales[product_id]['title'] = item.get('title', 'Unknown')

    # Sort by revenue
    top_products = sorted(
        product_sales.items(),
        key=lambda x: x[1]['revenue'],
        reverse=True
    )[:20]

    return {
        "date_range_days": days,
        "summary": orders_data.get('summary', {}),
        "product_performance": {
            "products_sold": len(product_sales),
            "top_20_products": [
                {
                    'product_id': str(pid),
                    'title': data['title'],
                    'quantity_sold': data['quantity'],
                    'revenue': round(data['revenue'], 2),
                    'orders': data['orders']
                }
                for pid, data in top_products
            ]
        }
    }


async def handle_get_shop_info() -> dict:
    """Get shop information"""
    data = shopify_get("shop.json")
    return {"shop": data.get('shop', {})}


# ============================================================================
# NEW Tool Handlers - Added in v2.0
# ============================================================================

async def handle_get_store_summary(days: int = 30) -> dict:
    """Get comprehensive store summary"""
    # Get orders
    orders_data = await handle_get_orders(days=days)

    # Get inventory
    inventory_data = await handle_get_inventory_levels()

    # Get abandoned checkouts
    abandoned_data = await handle_get_abandoned_checkouts(days=days)

    # Get shop info
    shop_data = await handle_get_shop_info()

    orders_summary = orders_data.get('summary', {})
    inventory_summary = inventory_data.get('summary', {})
    abandoned_summary = abandoned_data.get('summary', {})

    return {
        "store": shop_data.get('shop', {}).get('name', 'Unknown'),
        "date_range_days": days,
        "sales_summary": {
            "total_orders": orders_summary.get('total_orders', 0),
            "completed_orders": orders_summary.get('completed_orders', 0),
            "total_revenue": orders_summary.get('total_revenue', 0),
            "average_order_value": orders_summary.get('average_order_value', 0),
            "currency": orders_summary.get('currency', 'EUR')
        },
        "inventory_health": {
            "out_of_stock": inventory_summary.get('out_of_stock_count', 0),
            "low_stock": inventory_summary.get('low_stock_count', 0)
        },
        "abandoned_checkouts": {
            "count": abandoned_summary.get('total_abandoned', 0),
            "lost_revenue": abandoned_summary.get('lost_revenue', 0)
        },
        "insights": {
            "revenue_formatted": f"€{orders_summary.get('total_revenue', 0):,.2f}",
            "aov_formatted": f"€{orders_summary.get('average_order_value', 0):,.2f}",
            "recovery_opportunity": f"€{abandoned_summary.get('lost_revenue', 0):,.2f}"
        }
    }


async def handle_get_daily_revenue(days: int = 30) -> dict:
    """Get daily revenue breakdown"""
    orders_data = await handle_get_orders(days=days)
    orders = orders_data.get('orders', [])

    # Group by date
    daily_data = {}
    for order in orders:
        created = order.get('created_at', '')[:10]  # Get date part
        if created:
            if created not in daily_data:
                daily_data[created] = {'orders': 0, 'revenue': 0}
            daily_data[created]['orders'] += 1
            daily_data[created]['revenue'] += float(order.get('total_price', 0))

    # Convert to list and sort
    daily_list = []
    for date, metrics in sorted(daily_data.items()):
        daily_list.append({
            'date': date,
            'orders': metrics['orders'],
            'revenue': round(metrics['revenue'], 2)
        })

    # Calculate trends
    total_revenue = sum(d['revenue'] for d in daily_list)
    avg_daily_revenue = total_revenue / len(daily_list) if daily_list else 0

    return {
        "date_range_days": days,
        "summary": {
            "total_revenue": round(total_revenue, 2),
            "total_orders": sum(d['orders'] for d in daily_list),
            "average_daily_revenue": round(avg_daily_revenue, 2),
            "best_day": max(daily_list, key=lambda x: x['revenue']) if daily_list else None
        },
        "daily_breakdown": daily_list
    }


async def handle_get_fulfillment_status(days: int = 7) -> dict:
    """Get fulfillment status of orders"""
    orders_data = await handle_get_orders(days=days)
    orders = orders_data.get('orders', [])

    statuses = {
        'fulfilled': [],
        'partially_fulfilled': [],
        'unfulfilled': []
    }

    for order in orders:
        fulfillment_status = order.get('fulfillment_status') or 'unfulfilled'
        order_info = {
            'id': order.get('id'),
            'name': order.get('name'),
            'created_at': order.get('created_at'),
            'total_price': order.get('total_price'),
            'customer': order.get('customer', {}).get('email', 'N/A')
        }

        if fulfillment_status == 'fulfilled':
            statuses['fulfilled'].append(order_info)
        elif fulfillment_status == 'partial':
            statuses['partially_fulfilled'].append(order_info)
        else:
            statuses['unfulfilled'].append(order_info)

    return {
        "date_range_days": days,
        "summary": {
            "total_orders": len(orders),
            "fulfilled": len(statuses['fulfilled']),
            "partially_fulfilled": len(statuses['partially_fulfilled']),
            "unfulfilled": len(statuses['unfulfilled']),
            "fulfillment_rate": round(len(statuses['fulfilled']) / len(orders) * 100, 1) if orders else 0
        },
        "unfulfilled_orders": statuses['unfulfilled'][:20],
        "partially_fulfilled_orders": statuses['partially_fulfilled'][:10]
    }


# Tool handler mapping
TOOL_HANDLERS = {
    # Original tools
    "get_orders": handle_get_orders,
    "get_products": handle_get_products,
    "get_customers": handle_get_customers,
    "get_abandoned_checkouts": handle_get_abandoned_checkouts,
    "get_inventory_levels": handle_get_inventory_levels,
    "get_sales_analytics": handle_get_sales_analytics,
    "get_shop_info": handle_get_shop_info,
    # New tools - v2.0
    "get_store_summary": handle_get_store_summary,
    "get_daily_revenue": handle_get_daily_revenue,
    "get_fulfillment_status": handle_get_fulfillment_status
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
