#!/usr/bin/env python3
"""
Cloudflare R2 MCP Server
========================

MCP server for accessing Cloudflare R2 storage.
Provides tools for listing objects and getting public URLs.

Environment Variables:
- R2_ACCOUNT_ID: Cloudflare account ID
- R2_ACCESS_KEY_ID: R2 access key
- R2_SECRET_ACCESS_KEY: R2 secret key
- R2_ENDPOINT: R2 endpoint URL
- R2_BUCKET_NAME: Default bucket name
- R2_PUBLIC_URL: Public URL prefix for objects

Author: Claude
Version: 1.0.0
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

import boto3
from botocore.config import Config
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Initialize MCP server
server = Server("cloudflare-r2")

# R2 Configuration from environment
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "pomandi-media")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-1de25a6a3db9483aa103360222346a62.r2.dev")


def get_r2_client():
    """Create and return an S3 client configured for Cloudflare R2."""
    if not all([R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT]):
        raise ValueError("R2 credentials not configured. Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT")

    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"}
        ),
        region_name="auto"
    )


def get_public_url(key: str) -> str:
    """Get public URL for an object."""
    # Remove leading slash if present
    key = key.lstrip("/")
    return f"{R2_PUBLIC_URL.rstrip('/')}/{key}"


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available R2 tools."""
    return [
        Tool(
            name="list_objects",
            description="List objects in R2 bucket with optional prefix filter. Returns object keys, sizes, and public URLs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prefix": {
                        "type": "string",
                        "description": "Filter objects by prefix (e.g., 'products/', 'products/wedding-suits/')"
                    },
                    "max_keys": {
                        "type": "integer",
                        "description": "Maximum number of objects to return (default: 100)",
                        "default": 100
                    },
                    "bucket": {
                        "type": "string",
                        "description": f"Bucket name (default: {R2_BUCKET_NAME})"
                    }
                }
            }
        ),
        Tool(
            name="get_object_url",
            description="Get public URL for an object in R2.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Object key (path) in the bucket"
                    }
                },
                "required": ["key"]
            }
        ),
        Tool(
            name="list_product_images",
            description="List product images from R2, optionally filtered by collection or product slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection slug to filter (e.g., 'wedding-suits', 'all-suits')"
                    },
                    "product_slug": {
                        "type": "string",
                        "description": "Product slug to filter"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of images to return (default: 10)",
                        "default": 10
                    },
                    "image_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Image extensions to include (default: ['jpg', 'jpeg', 'png', 'webp'])"
                    }
                }
            }
        ),
        Tool(
            name="get_hero_images",
            description="Get hero images for landing pages. Returns 4 product images suitable for split hero layout.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection to get images from (e.g., 'Wedding-Suits', 'All-Suits')",
                        "default": "All-Suits"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of images to return (default: 4)",
                        "default": 4
                    }
                }
            }
        ),
        Tool(
            name="check_credentials",
            description="Check if R2 credentials are configured and valid.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    try:
        if name == "list_objects":
            result = await list_objects(
                prefix=arguments.get("prefix", ""),
                max_keys=arguments.get("max_keys", 100),
                bucket=arguments.get("bucket", R2_BUCKET_NAME)
            )
        elif name == "get_object_url":
            result = await get_object_url_tool(arguments["key"])
        elif name == "list_product_images":
            result = await list_product_images(
                collection=arguments.get("collection"),
                product_slug=arguments.get("product_slug"),
                limit=arguments.get("limit", 10),
                image_types=arguments.get("image_types", ["jpg", "jpeg", "png", "webp"])
            )
        elif name == "get_hero_images":
            result = await get_hero_images(
                collection=arguments.get("collection", "All-Suits"),
                count=arguments.get("count", 4)
            )
        elif name == "check_credentials":
            result = await check_credentials()
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        error_result = {
            "error": str(e),
            "tool": name,
            "arguments": arguments
        }
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


async def list_objects(prefix: str = "", max_keys: int = 100, bucket: str = R2_BUCKET_NAME) -> Dict[str, Any]:
    """List objects in R2 bucket."""
    client = get_r2_client()

    params = {
        "Bucket": bucket,
        "MaxKeys": max_keys
    }
    if prefix:
        params["Prefix"] = prefix

    response = client.list_objects_v2(**params)

    objects = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        objects.append({
            "key": key,
            "size": obj["Size"],
            "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
            "public_url": get_public_url(key)
        })

    return {
        "bucket": bucket,
        "prefix": prefix,
        "count": len(objects),
        "is_truncated": response.get("IsTruncated", False),
        "objects": objects
    }


async def get_object_url_tool(key: str) -> Dict[str, Any]:
    """Get public URL for an object."""
    return {
        "key": key,
        "public_url": get_public_url(key)
    }


async def list_product_images(
    collection: Optional[str] = None,
    product_slug: Optional[str] = None,
    limit: int = 10,
    image_types: List[str] = None
) -> Dict[str, Any]:
    """List product images from R2."""
    if image_types is None:
        image_types = ["jpg", "jpeg", "png", "webp"]

    client = get_r2_client()

    # Build prefix based on filters
    prefix = "products/"
    if collection:
        prefix = f"products/{collection.lower()}/"
    if product_slug:
        prefix = f"products/{product_slug}/"

    response = client.list_objects_v2(
        Bucket=R2_BUCKET_NAME,
        Prefix=prefix,
        MaxKeys=limit * 5  # Get more to filter by type
    )

    images = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        # Check if it's an image
        ext = key.split(".")[-1].lower() if "." in key else ""
        if ext in image_types:
            images.append({
                "key": key,
                "size": obj["Size"],
                "public_url": get_public_url(key),
                "extension": ext
            })

        if len(images) >= limit:
            break

    return {
        "collection": collection,
        "product_slug": product_slug,
        "count": len(images),
        "images": images
    }


async def get_hero_images(collection: str = "All-Suits", count: int = 4) -> Dict[str, Any]:
    """
    Get hero images for landing pages.
    Returns images from R2 products/ folder.
    Note: R2 images are not collection-organized, so returns general product images.
    """
    try:
        client = get_r2_client()

        # List images from products/ folder
        response = client.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix="products/",
            MaxKeys=count * 3  # Get extra to filter
        )

        images = []
        image_extensions = ["jpg", "jpeg", "png", "webp"]

        for obj in response.get("Contents", []):
            key = obj["Key"]
            ext = key.split(".")[-1].lower().split("v")[0]  # Handle .jpgv1234 format
            if ext in image_extensions and obj["Size"] > 10000:  # Skip tiny images
                images.append(get_public_url(key))
                if len(images) >= count:
                    break

        if len(images) >= count:
            return {
                "collection": collection,
                "count": len(images),
                "images": images[:count],
                "source": "r2"
            }

    except Exception as e:
        pass  # Fall through to fallback

    # Fallback to static images
    fallback_images = ["/1.png", "/2.png", "/3.png", "/4.png"]
    return {
        "collection": collection,
        "count": count,
        "images": fallback_images[:count],
        "source": "fallback"
    }


async def check_credentials() -> Dict[str, Any]:
    """Check if R2 credentials are configured."""
    config_status = {
        "R2_ACCOUNT_ID": "SET" if R2_ACCOUNT_ID else "NOT_SET",
        "R2_ACCESS_KEY_ID": "SET" if R2_ACCESS_KEY_ID else "NOT_SET",
        "R2_SECRET_ACCESS_KEY": "SET" if R2_SECRET_ACCESS_KEY else "NOT_SET",
        "R2_ENDPOINT": R2_ENDPOINT or "NOT_SET",
        "R2_BUCKET_NAME": R2_BUCKET_NAME,
        "R2_PUBLIC_URL": R2_PUBLIC_URL
    }

    is_configured = all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT])

    # Test connection if configured
    connection_test = None
    if is_configured:
        try:
            client = get_r2_client()
            response = client.list_buckets()
            buckets = [b["Name"] for b in response.get("Buckets", [])]
            connection_test = {
                "status": "success",
                "buckets": buckets
            }
        except Exception as e:
            connection_test = {
                "status": "failed",
                "error": str(e)
            }

    return {
        "is_configured": is_configured,
        "config_status": config_status,
        "connection_test": connection_test
    }


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
