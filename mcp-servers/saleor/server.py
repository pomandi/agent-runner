"""
Saleor GraphQL MCP Server
Pomandi e-commerce icin Saleor API entegrasyonu
"""
import asyncio
import json
import logging
import os
from typing import Any, Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from dotenv import load_dotenv

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("saleor-mcp")

# Load environment variables
load_dotenv()

# Configuration
SALEOR_URL = os.getenv("SALEOR_URL", "https://api.pomandi.com/graphql/")
SALEOR_TOKEN = os.getenv("SALEOR_TOKEN", "")
DEFAULT_CHANNEL = os.getenv("SALEOR_CHANNEL", "default-channel")


class SaleorClient:
    """Async Saleor GraphQL client"""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self.client = httpx.AsyncClient(timeout=30.0)

    async def query(self, query: str, variables: dict = None) -> dict:
        """Execute GraphQL query"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await self.client.post(self.url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"GraphQL error: {e}")
            return {"errors": [{"message": str(e)}]}

    async def close(self):
        await self.client.aclose()


# GraphQL Queries
QUERIES = {
    "products_list": """
        query Products($channel: String!, $first: Int = 20, $after: String, $search: String) {
            products(channel: $channel, first: $first, after: $after, filter: {search: $search}) {
                totalCount
                pageInfo { hasNextPage endCursor }
                edges {
                    node {
                        id name slug description
                        category { id name }
                        thumbnail { url }
                        pricing { priceRange { start { gross { amount currency } } } }
                    }
                }
            }
        }
    """,

    "product_detail": """
        query Product($id: ID!, $channel: String!) {
            product(id: $id, channel: $channel) {
                id name slug description seoTitle seoDescription
                category { id name slug }
                collections { id name }
                media { id url alt type }
                variants {
                    id name sku
                    stocks { quantity warehouse { name } }
                    channelListings { channel { slug } price { amount currency } }
                }
            }
        }
    """,

    "orders_list": """
        query Orders($first: Int = 20, $after: String) {
            orders(first: $first, after: $after, sortBy: {field: CREATED_AT, direction: DESC}) {
                totalCount
                pageInfo { hasNextPage endCursor }
                edges {
                    node {
                        id number created status paymentStatus
                        total { gross { amount currency } }
                        user { email }
                        billingAddress { firstName lastName city country { country } }
                        lines { productName quantity }
                    }
                }
            }
        }
    """,

    "order_detail": """
        query Order($id: ID!) {
            order(id: $id) {
                id number created status paymentStatus
                total { gross { amount currency } }
                subtotal { gross { amount currency } }
                shippingPrice { gross { amount currency } }
                user { email firstName lastName }
                billingAddress {
                    firstName lastName streetAddress1 streetAddress2
                    city postalCode country { country code } phone
                }
                shippingAddress {
                    firstName lastName streetAddress1 streetAddress2
                    city postalCode country { country code } phone
                }
                lines {
                    id productName variantName quantity
                    unitPrice { gross { amount currency } }
                    totalPrice { gross { amount currency } }
                    thumbnail { url }
                }
                payments { id gateway paymentMethodType chargeStatus total { amount currency } }
                fulfillments { id status trackingNumber lines { quantity orderLine { productName } } }
            }
        }
    """,

    "pages_list": """
        query Pages($first: Int = 50) {
            pages(first: $first) {
                edges {
                    node {
                        id title slug isPublished created
                        translations { language { code } title }
                    }
                }
            }
        }
    """,

    "page_detail": """
        query Page($id: ID!) {
            page(id: $id) {
                id title slug content seoTitle seoDescription isPublished created
                translations {
                    language { code language }
                    title content seoTitle seoDescription
                }
            }
        }
    """,

    "categories_list": """
        query Categories($first: Int = 100) {
            categories(first: $first) {
                edges {
                    node {
                        id name slug description
                        products { totalCount }
                    }
                }
            }
        }
    """,

    "collections_list": """
        query Collections($channel: String!, $first: Int = 50) {
            collections(channel: $channel, first: $first) {
                edges {
                    node {
                        id name slug description
                        products(first: 5) { totalCount edges { node { id name } } }
                    }
                }
            }
        }
    """,

    "channels_list": """
        query Channels {
            channels { id name slug currencyCode defaultCountry { code country } isActive }
        }
    """,

    "store_stats": """
        query StoreStats {
            products { totalCount }
            categories { totalCount }
            collections { totalCount }
            orders { totalCount }
        }
    """,

    "missing_translations": """
        query MissingTranslations($channel: String!, $languageCode: LanguageCodeEnum!, $first: Int = 50) {
            products(channel: $channel, first: $first) {
                edges {
                    node {
                        id name
                        translation(languageCode: $languageCode) { id name }
                    }
                }
            }
        }
    """,

    "customers_list": """
        query Customers($first: Int = 20, $after: String) {
            customers(first: $first, after: $after) {
                totalCount
                pageInfo { hasNextPage endCursor }
                edges {
                    node {
                        id email firstName lastName isActive dateJoined
                        orders { totalCount }
                        addresses { city country { country } }
                    }
                }
            }
        }
    """,

    "search_products": """
        query SearchProducts($channel: String!, $search: String!) {
            products(channel: $channel, first: 50, filter: {search: $search}) {
                edges {
                    node {
                        id name slug
                        category { name }
                        variants { id sku }
                    }
                }
            }
        }
    """
}

# Mutations
MUTATIONS = {
    "translate_product": """
        mutation TranslateProduct($id: ID!, $languageCode: LanguageCodeEnum!, $input: TranslationInput!) {
            productTranslate(id: $id, languageCode: $languageCode, input: $input) {
                product { id translation(languageCode: $languageCode) { name description } }
                errors { field message }
            }
        }
    """,

    "translate_page": """
        mutation TranslatePage($id: ID!, $languageCode: LanguageCodeEnum!, $input: PageTranslationInput!) {
            pageTranslate(id: $id, languageCode: $languageCode, input: $input) {
                page { id translation(languageCode: $languageCode) { title content } }
                errors { field message }
            }
        }
    """,

    "create_page": """
        mutation CreatePage($input: PageCreateInput!) {
            pageCreate(input: $input) {
                page { id title slug }
                errors { field message }
            }
        }
    """,

    "update_page": """
        mutation UpdatePage($id: ID!, $input: PageInput!) {
            pageUpdate(id: $id, input: $input) {
                page { id title slug content }
                errors { field message }
            }
        }
    """,

    "create_collection": """
        mutation CreateCollection($input: CollectionCreateInput!) {
            collectionCreate(input: $input) {
                collection { id name slug }
                errors { field message }
            }
        }
    """,

    "add_products_to_collection": """
        mutation AddToCollection($collectionId: ID!, $products: [ID!]!) {
            collectionAddProducts(collectionId: $collectionId, products: $products) {
                collection { id name products { totalCount } }
                errors { field message }
            }
        }
    """,

    "update_product": """
        mutation UpdateProduct($id: ID!, $input: ProductInput!) {
            productUpdate(id: $id, input: $input) {
                product { id name slug }
                errors { field message }
            }
        }
    """
}

# Initialize server
app = Server("saleor-mcp")
client: Optional[SaleorClient] = None


def get_client() -> SaleorClient:
    global client
    if client is None:
        client = SaleorClient(SALEOR_URL, SALEOR_TOKEN)
    return client


def format_result(data: dict) -> str:
    """Format GraphQL result as readable text"""
    if "errors" in data and data["errors"]:
        return f"Error: {json.dumps(data['errors'], indent=2)}"
    return json.dumps(data.get("data", data), indent=2, ensure_ascii=False)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Saleor tools"""
    return [
        # Products
        Tool(
            name="saleor_products_list",
            description="List products with optional search. Returns product name, price, category, thumbnail.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Search term for products"},
                    "first": {"type": "integer", "description": "Number of products (default: 20)"},
                    "channel": {"type": "string", "description": "Channel slug (default: default-channel)"}
                }
            }
        ),
        Tool(
            name="saleor_product_detail",
            description="Get detailed product info including variants, stock, translations, media.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Product ID"},
                    "channel": {"type": "string", "description": "Channel slug"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="saleor_product_search",
            description="Search products by name, SKU or description.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Search query"},
                    "channel": {"type": "string", "description": "Channel slug"}
                },
                "required": ["search"]
            }
        ),
        Tool(
            name="saleor_product_update",
            description="Update product details (name, description, SEO).",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Product ID"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "seoTitle": {"type": "string"},
                    "seoDescription": {"type": "string"}
                },
                "required": ["id"]
            }
        ),

        # Orders
        Tool(
            name="saleor_orders_list",
            description="List recent orders with customer info, status, total amount.",
            inputSchema={
                "type": "object",
                "properties": {
                    "first": {"type": "integer", "description": "Number of orders (default: 20)"}
                }
            }
        ),
        Tool(
            name="saleor_order_detail",
            description="Get full order details including items, addresses, payments, fulfillments.",
            inputSchema={
                "type": "object",
                "properties": {"id": {"type": "string", "description": "Order ID"}},
                "required": ["id"]
            }
        ),

        # Pages
        Tool(
            name="saleor_pages_list",
            description="List all CMS pages with translation status.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="saleor_page_detail",
            description="Get page content and all translations.",
            inputSchema={
                "type": "object",
                "properties": {"id": {"type": "string", "description": "Page ID"}},
                "required": ["id"]
            }
        ),
        Tool(
            name="saleor_page_create",
            description="Create a new CMS page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "slug": {"type": "string"},
                    "content": {"type": "string"},
                    "isPublished": {"type": "boolean"}
                },
                "required": ["title", "slug"]
            }
        ),
        Tool(
            name="saleor_page_update",
            description="Update an existing page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "isPublished": {"type": "boolean"}
                },
                "required": ["id"]
            }
        ),

        # Collections
        Tool(
            name="saleor_collections_list",
            description="List product collections.",
            inputSchema={
                "type": "object",
                "properties": {"channel": {"type": "string"}}
            }
        ),
        Tool(
            name="saleor_collection_create",
            description="Create a new product collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "slug": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="saleor_collection_add_products",
            description="Add products to a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collectionId": {"type": "string"},
                    "productIds": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["collectionId", "productIds"]
            }
        ),

        # Categories
        Tool(
            name="saleor_categories_list",
            description="List all categories with product counts.",
            inputSchema={"type": "object", "properties": {}}
        ),

        # Channels
        Tool(
            name="saleor_channels_list",
            description="List all sales channels.",
            inputSchema={"type": "object", "properties": {}}
        ),

        # Translations
        Tool(
            name="saleor_translate_product",
            description="Translate a product to FR or NL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "languageCode": {"type": "string", "enum": ["FR", "NL"]},
                    "name": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["id", "languageCode"]
            }
        ),
        Tool(
            name="saleor_translate_page",
            description="Translate a CMS page to FR or NL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "languageCode": {"type": "string", "enum": ["FR", "NL"]},
                    "title": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["id", "languageCode"]
            }
        ),
        Tool(
            name="saleor_missing_translations",
            description="Find products missing translations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "languageCode": {"type": "string", "enum": ["FR", "NL"]},
                    "channel": {"type": "string"}
                },
                "required": ["languageCode"]
            }
        ),

        # Customers
        Tool(
            name="saleor_customers_list",
            description="List customers with order counts.",
            inputSchema={
                "type": "object",
                "properties": {"first": {"type": "integer"}}
            }
        ),

        # Statistics
        Tool(
            name="saleor_store_stats",
            description="Get store statistics: product, category, collection, order counts.",
            inputSchema={"type": "object", "properties": {}}
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a Saleor tool"""
    saleor = get_client()
    result = {}

    try:
        # Products
        if name == "saleor_products_list":
            channel = arguments.get("channel", DEFAULT_CHANNEL)
            result = await saleor.query(QUERIES["products_list"], {
                "channel": channel,
                "first": arguments.get("first", 20),
                "search": arguments.get("search")
            })

        elif name == "saleor_product_detail":
            result = await saleor.query(QUERIES["product_detail"], {
                "id": arguments["id"],
                "channel": arguments.get("channel", DEFAULT_CHANNEL)
            })

        elif name == "saleor_product_search":
            result = await saleor.query(QUERIES["search_products"], {
                "channel": arguments.get("channel", DEFAULT_CHANNEL),
                "search": arguments["search"]
            })

        elif name == "saleor_product_update":
            input_data = {}
            if "name" in arguments:
                input_data["name"] = arguments["name"]
            if "description" in arguments:
                input_data["description"] = arguments["description"]
            if "seoTitle" in arguments or "seoDescription" in arguments:
                input_data["seo"] = {}
                if "seoTitle" in arguments:
                    input_data["seo"]["title"] = arguments["seoTitle"]
                if "seoDescription" in arguments:
                    input_data["seo"]["description"] = arguments["seoDescription"]

            result = await saleor.query(MUTATIONS["update_product"], {
                "id": arguments["id"],
                "input": input_data
            })

        # Orders
        elif name == "saleor_orders_list":
            result = await saleor.query(QUERIES["orders_list"], {
                "first": arguments.get("first", 20)
            })

        elif name == "saleor_order_detail":
            result = await saleor.query(QUERIES["order_detail"], {"id": arguments["id"]})

        # Pages
        elif name == "saleor_pages_list":
            result = await saleor.query(QUERIES["pages_list"], {})

        elif name == "saleor_page_detail":
            result = await saleor.query(QUERIES["page_detail"], {"id": arguments["id"]})

        elif name == "saleor_page_create":
            result = await saleor.query(MUTATIONS["create_page"], {
                "input": {
                    "title": arguments["title"],
                    "slug": arguments["slug"],
                    "content": arguments.get("content", ""),
                    "isPublished": arguments.get("isPublished", False)
                }
            })

        elif name == "saleor_page_update":
            input_data = {k: arguments[k] for k in ["title", "content", "isPublished"] if k in arguments}
            result = await saleor.query(MUTATIONS["update_page"], {
                "id": arguments["id"],
                "input": input_data
            })

        # Collections
        elif name == "saleor_collections_list":
            result = await saleor.query(QUERIES["collections_list"], {
                "channel": arguments.get("channel", DEFAULT_CHANNEL)
            })

        elif name == "saleor_collection_create":
            result = await saleor.query(MUTATIONS["create_collection"], {
                "input": {
                    "name": arguments["name"],
                    "slug": arguments.get("slug", arguments["name"].lower().replace(" ", "-")),
                    "description": arguments.get("description", "")
                }
            })

        elif name == "saleor_collection_add_products":
            result = await saleor.query(MUTATIONS["add_products_to_collection"], {
                "collectionId": arguments["collectionId"],
                "products": arguments["productIds"]
            })

        # Categories
        elif name == "saleor_categories_list":
            result = await saleor.query(QUERIES["categories_list"], {})

        # Channels
        elif name == "saleor_channels_list":
            result = await saleor.query(QUERIES["channels_list"], {})

        # Translations
        elif name == "saleor_translate_product":
            input_data = {k: arguments[k] for k in ["name", "description"] if k in arguments}
            result = await saleor.query(MUTATIONS["translate_product"], {
                "id": arguments["id"],
                "languageCode": arguments["languageCode"],
                "input": input_data
            })

        elif name == "saleor_translate_page":
            input_data = {k: arguments[k] for k in ["title", "content"] if k in arguments}
            result = await saleor.query(MUTATIONS["translate_page"], {
                "id": arguments["id"],
                "languageCode": arguments["languageCode"],
                "input": input_data
            })

        elif name == "saleor_missing_translations":
            result = await saleor.query(QUERIES["missing_translations"], {
                "channel": arguments.get("channel", DEFAULT_CHANNEL),
                "languageCode": arguments["languageCode"]
            })
            # Filter missing
            if result.get("data", {}).get("products", {}).get("edges"):
                missing = [
                    {"id": e["node"]["id"], "name": e["node"]["name"]}
                    for e in result["data"]["products"]["edges"]
                    if not e["node"].get("translation") or not e["node"]["translation"].get("name")
                ]
                result = {"missing_translations": missing, "count": len(missing)}

        # Customers
        elif name == "saleor_customers_list":
            result = await saleor.query(QUERIES["customers_list"], {
                "first": arguments.get("first", 20)
            })

        # Statistics
        elif name == "saleor_store_stats":
            result = await saleor.query(QUERIES["store_stats"], {})

        else:
            result = {"error": f"Unknown tool: {name}"}

    except Exception as e:
        logger.error(f"Tool {name} error: {e}")
        result = {"error": str(e)}

    return [TextContent(type="text", text=format_result(result))]


async def main():
    """Run the MCP server"""
    logger.info(f"Starting Saleor MCP Server - URL: {SALEOR_URL}")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
