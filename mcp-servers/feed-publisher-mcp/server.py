#!/usr/bin/env python3
"""feed-publisher-mcp MCP Server - Container Version with Image Vision"""
import asyncio
import json
import logging
import os
import base64
import httpx
import boto3
from botocore.config import Config
from datetime import datetime
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("feed-publisher-mcp")

server = Server("feed-publisher-mcp")

# Brand Configuration
BRANDS = {
    "pomandi": {
        "language": "nl",
        "facebook_page_id": "335388637037718",
        "instagram_id": "17841406855004574",
        "access_token_env": "FACE_POMANDI_ACCESS_TOKEN",
        "products": ["men's suits", "ties", "shirts", "formal wear", "accessories", "shoes"]
    },
    "costume": {
        "language": "fr",
        "facebook_page_id": "101071881743506",
        "instagram_id": "17841441106266856",
        "access_token_env": "FACE_COSTUME_ACCESS_TOKEN",
        "products": ["men's suits", "ties", "shirts", "formal wear", "accessories", "shoes"]
    }
}

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "saleorme")
AWS_REGION = os.getenv("AWS_S3_REGION_NAME", "us-east-1")

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


async def download_image(image_url: str) -> tuple:
    """Download image and return (base64_data, media_type)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(image_url)
        if response.status_code != 200:
            raise Exception(f"Failed to download image: {response.status_code}")
        
        content_type = response.headers.get('content-type', 'image/jpeg')
        if 'png' in content_type:
            media_type = 'image/png'
        elif 'gif' in content_type:
            media_type = 'image/gif'
        elif 'webp' in content_type:
            media_type = 'image/webp'
        else:
            media_type = 'image/jpeg'
        
        image_data = base64.standard_b64encode(response.content).decode('utf-8')
        return image_data, media_type


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="view_image",
            description="""View a product image so you can see what it contains.
            
USE THIS BEFORE POSTING to verify the image shows men's fashion (suits, ties, shirts, shoes).
If it shows something else (plates, furniture, etc.), DO NOT post it.

Returns the actual image so you can analyze it yourself.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "Public URL of the image to view"}
                },
                "required": ["image_url"]
            }
        ),
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
            description="""Publish photo to Facebook page.
            
IMPORTANT: Use view_image first to verify the image shows men's fashion!""",
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
            description="""Publish photo to Instagram.
            
IMPORTANT: Use view_image first to verify the image shows men's fashion!""",
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
        if name == "view_image":
            image_url = arguments.get("image_url", "")
            
            if not image_url:
                return [TextContent(type="text", text=json.dumps({"error": "image_url is required"}))]
            
            try:
                image_data, media_type = await download_image(image_url)
                
                # Return image so Claude can see it + context
                return [
                    ImageContent(
                        type="image",
                        data=image_data,
                        mimeType=media_type
                    ),
                    TextContent(
                        type="text", 
                        text=f"""Image URL: {image_url}

Please analyze this image:
1. What type of product is shown? (suit, tie, shirt, plates, furniture, etc.)
2. Is this men's fashion suitable for Pomandi/Costume brand?
3. If suitable, describe colors and style for caption writing.
4. If NOT suitable (not men's fashion), say "SKIP - not suitable" and explain why."""
                    )
                ]
            except Exception as e:
                return [TextContent(type="text", text=json.dumps({"error": f"Failed to load image: {str(e)}"}))]

        elif name == "get_s3_image":
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
