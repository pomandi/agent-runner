#!/usr/bin/env python3
"""feed-publisher-mcp MCP Server - Container Version"""
import asyncio
import json
import logging
import os
import httpx
import boto3
from botocore.config import Config
from datetime import datetime
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("feed-publisher-mcp")

server = Server("feed-publisher-mcp")

# Brand Configuration
BRANDS = {
    "pomandi": {
        "language": "nl",
        "facebook_page_id": "335388637037718",
        "instagram_id": "17841406855004574",
        "access_token_env": "FACE_POMANDI_ACCESS_TOKEN"
    },
    "costume": {
        "language": "fr",
        "facebook_page_id": "101071881743506",
        "instagram_id": "17841441106266856",
        "access_token_env": "FACE_COSTUME_ACCESS_TOKEN"
    }
}

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "saleorme")
AWS_REGION = os.getenv("AWS_S3_REGION_NAME", "us-east-1")

# Database Configuration
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "postgres")

GRAPH_API_URL = "https://graph.facebook.com/v22.0"


def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        config=Config(signature_version='s3v4')
    )


def get_access_token(brand: str) -> str:
    brand_config = BRANDS.get(brand.lower())
    if not brand_config:
        raise ValueError(f"Unknown brand: {brand}")
    return os.getenv(brand_config["access_token_env"], "")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="get_s3_image",
            description="Get presigned URL for product image from S3.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "S3 object key"},
                    "expires_in": {"type": "integer", "default": 3600}
                },
                "required": ["key"]
            }
        ),
        Tool(
            name="list_s3_products",
            description="List product images in S3 bucket.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prefix": {"type": "string", "default": "products/"},
                    "limit": {"type": "integer", "default": 20}
                }
            }
        ),
        Tool(
            name="publish_facebook_photo",
            description="Publish photo to Facebook page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {"type": "string", "enum": ["pomandi", "costume"]},
                    "image_url": {"type": "string"},
                    "caption": {"type": "string"}
                },
                "required": ["brand", "image_url", "caption"]
            }
        ),
        Tool(
            name="publish_instagram_photo",
            description="Publish photo to Instagram.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {"type": "string", "enum": ["pomandi", "costume"]},
                    "image_url": {"type": "string"},
                    "caption": {"type": "string"}
                },
                "required": ["brand", "image_url", "caption"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    logger.info(f"Tool called: {name}")

    try:
        if name == "get_s3_image":
            key = arguments.get("key", "")
            expires_in = arguments.get("expires_in", 3600)
            s3 = get_s3_client()
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': AWS_BUCKET_NAME, 'Key': key},
                ExpiresIn=expires_in
            )
            result = {
                "status": "success",
                "presigned_url": presigned_url,
                "public_url": f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "list_s3_products":
            prefix = arguments.get("prefix", "products/")
            limit = arguments.get("limit", 20)
            s3 = get_s3_client()
            response = s3.list_objects_v2(Bucket=AWS_BUCKET_NAME, Prefix=prefix, MaxKeys=limit)
            files = [{
                "key": obj['Key'],
                "size": obj['Size'],
                "public_url": f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{obj['Key']}"
            } for obj in response.get('Contents', [])]
            return [TextContent(type="text", text=json.dumps({"count": len(files), "files": files}, indent=2))]

        elif name == "publish_facebook_photo":
            brand = arguments.get("brand", "").lower()
            image_url = arguments.get("image_url", "")
            caption = arguments.get("caption", "")
            brand_config = BRANDS.get(brand)
            if not brand_config:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown brand: {brand}"}))]
            access_token = get_access_token(brand)
            if not access_token:
                return [TextContent(type="text", text=json.dumps({"error": "No access token configured"}))]
            page_id = brand_config["facebook_page_id"]
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{GRAPH_API_URL}/{page_id}/photos",
                    data={"url": image_url, "caption": caption, "access_token": access_token}
                )
                data = response.json()
                if "error" in data:
                    return [TextContent(type="text", text=json.dumps({"status": "error", "error": data["error"]}, indent=2))]
                return [TextContent(type="text", text=json.dumps({
                    "status": "success", "platform": "facebook", "post_id": data.get("post_id") or data.get("id")
                }, indent=2))]

        elif name == "publish_instagram_photo":
            brand = arguments.get("brand", "").lower()
            image_url = arguments.get("image_url", "")
            caption = arguments.get("caption", "")
            brand_config = BRANDS.get(brand)
            if not brand_config:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown brand: {brand}"}))]
            access_token = get_access_token(brand)
            if not access_token:
                return [TextContent(type="text", text=json.dumps({"error": "No access token configured"}))]
            instagram_id = brand_config["instagram_id"]
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Create container
                container_resp = await client.post(
                    f"{GRAPH_API_URL}/{instagram_id}/media",
                    data={"image_url": image_url, "caption": caption, "access_token": access_token}
                )
                container_data = container_resp.json()
                if "error" in container_data:
                    return [TextContent(type="text", text=json.dumps({"status": "error", "error": container_data["error"]}, indent=2))]
                container_id = container_data.get("id")
                await asyncio.sleep(5)
                # Publish
                publish_resp = await client.post(
                    f"{GRAPH_API_URL}/{instagram_id}/media_publish",
                    data={"creation_id": container_id, "access_token": access_token}
                )
                publish_data = publish_resp.json()
                if "error" in publish_data:
                    return [TextContent(type="text", text=json.dumps({"status": "error", "error": publish_data["error"]}, indent=2))]
                return [TextContent(type="text", text=json.dumps({
                    "status": "success", "platform": "instagram", "media_id": publish_data.get("id")
                }, indent=2))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        logger.error(f"Error in {name}: {e}")
        return [TextContent(type="text", text=json.dumps({"status": "error", "error": str(e)}, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
