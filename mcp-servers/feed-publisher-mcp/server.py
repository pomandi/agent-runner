#!/usr/bin/env python3
"""
feed-publisher-mcp MCP Server
Agent: feed-publisher
Category: publisher

Publishes feed posts to Facebook and Instagram.
Gets product images from AWS S3 (saleorme bucket) and captions from agent_outputs database.
Supports both Pomandi (NL) and Costume (FR) brands.

INCLUDES: Automatic Meta token refresh functionality
- Check token health
- Exchange short-lived for long-lived tokens (60 days)
- Auto-refresh when < 7 days remaining
"""
import asyncio
import json
import logging
import os
import re
import random
import httpx
import boto3
from botocore.config import Config
from datetime import datetime, timedelta
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent
import base64

# Configure logging
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

# Meta App Configuration (for token refresh)
META_APP_ID = os.getenv("FACEBOOK_APP_ID", "3710843852505482")
META_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "")

# Env file path for token updates
ENV_FILE_PATH = os.getenv("META_ENV_FILE", "/home/claude/projects/sale-v2/saleor/backend.env")
TOKEN_LOG_PATH = Path.home() / '.claude' / 'logs' / 'meta-token'

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "saleorme")
AWS_REGION = os.getenv("AWS_S3_REGION_NAME", "us-east-1")

# Database Configuration (agent_outputs)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "dXn0xUUpebj1ooW9nI0gJMQJMrJloLaVexQkDm8XvWN6CYNwd3JMXiVUuBcgqr4m")
DB_NAME = os.getenv("DB_NAME", "postgres")

# Facebook Graph API
GRAPH_API_URL = "https://graph.facebook.com/v22.0"


def get_s3_client():
    """Get boto3 S3 client."""
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        config=Config(signature_version='s3v4')
    )


def get_access_token(brand: str) -> str:
    """Get access token for brand."""
    brand_config = BRANDS.get(brand.lower())
    if not brand_config:
        raise ValueError(f"Unknown brand: {brand}")
    return os.getenv(brand_config["access_token_env"], "")


# =============================================================================
# TOKEN MANAGEMENT FUNCTIONS
# =============================================================================

async def check_token_expiration(token: str) -> dict:
    """Check if token is valid and when it expires."""
    if not META_APP_SECRET:
        return {"error": "FACEBOOK_APP_SECRET not configured"}

    url = f"{GRAPH_API_URL}/debug_token"
    params = {
        'input_token': token,
        'access_token': f"{META_APP_ID}|{META_APP_SECRET}"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        data = response.json()

    if 'data' not in data:
        return {
            'is_valid': False,
            'needs_refresh': True,
            'reason': 'Invalid token or cannot validate',
            'error': data.get('error', {})
        }

    token_info = data['data']

    if not token_info.get('is_valid', False):
        return {
            'is_valid': False,
            'needs_refresh': True,
            'reason': 'Token is invalid',
            'error_code': token_info.get('error', {}).get('code'),
            'error_message': token_info.get('error', {}).get('message')
        }

    expires_at = token_info.get('expires_at', 0)

    if expires_at == 0:
        return {
            'is_valid': True,
            'needs_refresh': False,
            'reason': 'Never expires (system user token)',
            'type': 'permanent',
            'scopes': token_info.get('scopes', [])
        }

    expiration_date = datetime.fromtimestamp(expires_at)
    now = datetime.now()
    days_remaining = (expiration_date - now).days
    hours_remaining = (expiration_date - now).total_seconds() / 3600

    # Token types and refresh logic
    if hours_remaining < 2:
        return {
            'is_valid': True,
            'needs_refresh': True,
            'reason': f'Short-lived token (expires in {int(hours_remaining * 60)} minutes)',
            'type': 'short_lived',
            'expires_at': expiration_date.isoformat(),
            'hours_remaining': round(hours_remaining, 2),
            'days_remaining': days_remaining
        }
    elif days_remaining < 7:
        return {
            'is_valid': True,
            'needs_refresh': True,
            'reason': f'Expiring soon ({days_remaining} days remaining)',
            'type': 'long_lived',
            'expires_at': expiration_date.isoformat(),
            'days_remaining': days_remaining
        }
    else:
        return {
            'is_valid': True,
            'needs_refresh': False,
            'reason': f'Token valid for {days_remaining} days',
            'type': 'long_lived',
            'expires_at': expiration_date.isoformat(),
            'days_remaining': days_remaining,
            'scopes': token_info.get('scopes', [])
        }


async def exchange_for_long_lived_token(short_token: str) -> dict:
    """Exchange short-lived token for long-lived token (60 days)."""
    if not META_APP_SECRET:
        return {"success": False, "error": "FACEBOOK_APP_SECRET not configured"}

    url = f"{GRAPH_API_URL}/oauth/access_token"
    params = {
        'grant_type': 'fb_exchange_token',
        'client_id': META_APP_ID,
        'client_secret': META_APP_SECRET,
        'fb_exchange_token': short_token
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)

        if response.status_code != 200:
            return {
                'success': False,
                'error': response.text,
                'status_code': response.status_code
            }

        data = response.json()

        if 'error' in data:
            return {
                'success': False,
                'error': data['error']
            }

        expires_in_seconds = data.get('expires_in', 5184000)  # Default 60 days
        expiration_date = datetime.now() + timedelta(seconds=expires_in_seconds)

        return {
            'success': True,
            'token': data['access_token'],
            'expires_in_seconds': expires_in_seconds,
            'expires_in_days': expires_in_seconds // 86400,
            'expiration_date': expiration_date.isoformat()
        }


def update_env_file(brand: str, new_token: str) -> dict:
    """Update .env file with new token for brand."""
    try:
        env_file = Path(ENV_FILE_PATH)

        if not env_file.exists():
            return {"success": False, "error": f"Env file not found: {ENV_FILE_PATH}"}

        content = env_file.read_text(encoding='utf-8')
        brand_config = BRANDS.get(brand.lower())

        if not brand_config:
            return {"success": False, "error": f"Unknown brand: {brand}"}

        token_key = brand_config["access_token_env"]

        # Check if key exists
        if token_key not in content:
            return {"success": False, "error": f"Token key {token_key} not found in env file"}

        # Replace token
        new_content = re.sub(
            rf'{token_key}=.+',
            f'{token_key}={new_token}',
            content
        )

        # Backup original
        backup_file = env_file.with_suffix('.env.bak')
        backup_file.write_text(content, encoding='utf-8')

        # Write new content
        env_file.write_text(new_content, encoding='utf-8')

        # Also update os.environ for current session
        os.environ[token_key] = new_token

        return {
            "success": True,
            "brand": brand,
            "token_key": token_key,
            "env_file": str(env_file),
            "backup": str(backup_file)
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def log_token_refresh(brand: str, token_info: dict) -> bool:
    """Log token refresh to history."""
    try:
        TOKEN_LOG_PATH.mkdir(parents=True, exist_ok=True)
        log_file = TOKEN_LOG_PATH / f'{brand}-refresh-history.json'

        # Load existing history
        if log_file.exists():
            history = json.loads(log_file.read_text(encoding='utf-8'))
        else:
            history = []

        # Add new entry
        history.append({
            'timestamp': datetime.now().isoformat(),
            'brand': brand,
            'token_preview': token_info.get('token', '')[:30] + '...',
            'expires_in_days': token_info.get('expires_in_days'),
            'expiration_date': token_info.get('expiration_date')
        })

        # Keep only last 50 entries
        history = history[-50:]

        log_file.write_text(json.dumps(history, indent=2), encoding='utf-8')
        return True

    except Exception as e:
        logger.warning(f"Could not log refresh: {e}")
        return False


async def auto_refresh_token_if_needed(brand: str) -> dict:
    """Check token and auto-refresh if needed. Returns status."""
    token = get_access_token(brand)

    if not token:
        return {
            "status": "error",
            "brand": brand,
            "message": "No token configured"
        }

    # Check token status
    check_result = await check_token_expiration(token)

    if not check_result.get('is_valid'):
        return {
            "status": "invalid",
            "brand": brand,
            "message": "Token is invalid - manual refresh required",
            "details": check_result
        }

    if not check_result.get('needs_refresh'):
        return {
            "status": "valid",
            "brand": brand,
            "message": check_result.get('reason'),
            "days_remaining": check_result.get('days_remaining'),
            "expires_at": check_result.get('expires_at')
        }

    # Token needs refresh - attempt exchange
    logger.info(f"Auto-refreshing token for {brand}: {check_result.get('reason')}")

    exchange_result = await exchange_for_long_lived_token(token)

    if not exchange_result.get('success'):
        return {
            "status": "refresh_failed",
            "brand": brand,
            "message": "Token exchange failed",
            "error": exchange_result.get('error')
        }

    # Update env file
    update_result = update_env_file(brand, exchange_result['token'])

    if not update_result.get('success'):
        return {
            "status": "update_failed",
            "brand": brand,
            "message": "Got new token but failed to update env file",
            "error": update_result.get('error'),
            "new_token_preview": exchange_result['token'][:50] + '...'
        }

    # Log refresh
    log_token_refresh(brand, exchange_result)

    return {
        "status": "refreshed",
        "brand": brand,
        "message": f"Token refreshed successfully! Valid for {exchange_result['expires_in_days']} days",
        "expires_in_days": exchange_result['expires_in_days'],
        "expiration_date": exchange_result['expiration_date'],
        "env_file_updated": update_result.get('env_file')
    }


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
        Tool(
            name="get_s3_image",
            description="Get presigned URL for product image from AWS S3 (saleorme bucket). Returns a public URL valid for 1 hour.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "S3 object key (e.g., 'products/10560320962610-min_fd550dc6.jpg')"
                    },
                    "expires_in": {
                        "type": "integer",
                        "description": "URL expiration in seconds (default: 3600)",
                        "default": 3600
                    }
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
                    "prefix": {
                        "type": "string",
                        "description": "S3 prefix to filter (default: 'products/')",
                        "default": "products/"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max items to return (default: 20)",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="publish_facebook_photo",
            description="Publish photo post to Facebook page. Returns post_id on success.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {
                        "type": "string",
                        "enum": ["pomandi", "costume"],
                        "description": "Brand to publish to"
                    },
                    "image_url": {
                        "type": "string",
                        "description": "Public URL of the image"
                    },
                    "caption": {
                        "type": "string",
                        "description": "Post caption text"
                    }
                },
                "required": ["brand", "image_url", "caption"]
            }
        ),
        Tool(
            name="publish_instagram_photo",
            description="Publish photo to Instagram feed. Returns media_id on success.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {
                        "type": "string",
                        "enum": ["pomandi", "costume"],
                        "description": "Brand to publish to"
                    },
                    "image_url": {
                        "type": "string",
                        "description": "Public URL of the image (must be accessible)"
                    },
                    "caption": {
                        "type": "string",
                        "description": "Post caption text"
                    }
                },
                "required": ["brand", "image_url", "caption"]
            }
        ),
        Tool(
            name="get_latest_caption",
            description="Get latest caption from caption-generator agent outputs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": ["nl", "fr"],
                        "description": "Caption language (nl=Dutch for Pomandi, fr=French for Costume)"
                    }
                },
                "required": ["language"]
            }
        ),
        Tool(
            name="get_publication_status",
            description="Check today's publication status for a brand.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {
                        "type": "string",
                        "enum": ["pomandi", "costume"],
                        "description": "Brand to check"
                    }
                },
                "required": ["brand"]
            }
        ),
        # Token Management Tools
        Tool(
            name="check_token_health",
            description="Check if Meta access token is valid and when it expires. Returns status, days remaining, and whether refresh is needed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {
                        "type": "string",
                        "enum": ["pomandi", "costume"],
                        "description": "Brand to check token for"
                    }
                },
                "required": ["brand"]
            }
        ),
        Tool(
            name="refresh_token",
            description="Exchange short-lived token for long-lived token (60 days). Automatically updates env file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {
                        "type": "string",
                        "enum": ["pomandi", "costume"],
                        "description": "Brand to refresh token for"
                    },
                    "new_short_token": {
                        "type": "string",
                        "description": "Optional: New short-lived token from Graph API Explorer. If not provided, tries to exchange current token."
                    }
                },
                "required": ["brand"]
            }
        ),
        Tool(
            name="auto_refresh_all_tokens",
            description="Check all brand tokens and auto-refresh any that need it. Call this periodically (e.g., daily) to ensure tokens stay valid.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_token_refresh_history",
            description="Get token refresh history for a brand.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {
                        "type": "string",
                        "enum": ["pomandi", "costume"],
                        "description": "Brand to get history for"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to return (default: 10)",
                        "default": 10
                    }
                },
                "required": ["brand"]
            }
        ),
        # Image Analysis Tool
        Tool(
            name="view_image",
            description="View an image from S3 to analyze its content. Returns the image so you can see what's in it. Use this to verify image content matches the caption before publishing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "S3 object key (e.g., 'products/10560320962610-min_fd550dc6.jpg')"
                    }
                },
                "required": ["key"]
            }
        ),
        # Random Photo Selection Tool
        Tool(
            name="get_random_unused_photo",
            description="Get a random product photo that hasn't been published recently. Checks last 30 publications to avoid repeats. Use this instead of list_s3_products to ensure variety.",
            inputSchema={
                "type": "object",
                "properties": {
                    "brand": {
                        "type": "string",
                        "enum": ["pomandi", "costume"],
                        "description": "Brand to check for recent publications"
                    },
                    "days_lookback": {
                        "type": "integer",
                        "description": "Days to look back for used photos (default: 30)",
                        "default": 30
                    }
                },
                "required": ["brand"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")

    try:
        if name == "get_s3_image":
            key = arguments.get("key", "")
            expires_in = arguments.get("expires_in", 3600)

            if not key:
                return [TextContent(type="text", text=json.dumps({"error": "key is required"}))]

            s3 = get_s3_client()

            # Generate presigned URL
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': AWS_BUCKET_NAME, 'Key': key},
                ExpiresIn=expires_in
            )

            result = {
                "status": "success",
                "bucket": AWS_BUCKET_NAME,
                "key": key,
                "presigned_url": presigned_url,
                "expires_in": expires_in,
                "public_url": f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "list_s3_products":
            prefix = arguments.get("prefix", "products/")
            limit = arguments.get("limit", 20)

            s3 = get_s3_client()

            response = s3.list_objects_v2(
                Bucket=AWS_BUCKET_NAME,
                Prefix=prefix,
                MaxKeys=limit
            )

            files = []
            for obj in response.get('Contents', []):
                files.append({
                    "key": obj['Key'],
                    "size": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat(),
                    "public_url": f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{obj['Key']}"
                })

            result = {
                "status": "success",
                "bucket": AWS_BUCKET_NAME,
                "prefix": prefix,
                "count": len(files),
                "files": files
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "publish_facebook_photo":
            brand = arguments.get("brand", "").lower()
            image_url = arguments.get("image_url", "")
            caption = arguments.get("caption", "")

            if brand not in BRANDS:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown brand: {brand}"}))]

            brand_config = BRANDS[brand]
            access_token = get_access_token(brand)

            if not access_token:
                return [TextContent(type="text", text=json.dumps({"error": f"No access token for {brand}"}))]

            page_id = brand_config["facebook_page_id"]

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{GRAPH_API_URL}/{page_id}/photos",
                    data={
                        "url": image_url,
                        "caption": caption,
                        "access_token": access_token
                    }
                )

                data = response.json()

                if "error" in data:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "brand": brand,
                        "platform": "facebook",
                        "error": data["error"]
                    }, indent=2))]

                result = {
                    "status": "success",
                    "brand": brand,
                    "platform": "facebook",
                    "page_id": page_id,
                    "post_id": data.get("post_id") or data.get("id"),
                    "published_at": datetime.now().isoformat()
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "publish_instagram_photo":
            brand = arguments.get("brand", "").lower()
            image_url = arguments.get("image_url", "")
            caption = arguments.get("caption", "")

            if brand not in BRANDS:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown brand: {brand}"}))]

            brand_config = BRANDS[brand]
            access_token = get_access_token(brand)

            if not access_token:
                return [TextContent(type="text", text=json.dumps({"error": f"No access token for {brand}"}))]

            instagram_id = brand_config["instagram_id"]

            async with httpx.AsyncClient(timeout=120.0) as client:
                # Step 1: Create media container
                container_response = await client.post(
                    f"{GRAPH_API_URL}/{instagram_id}/media",
                    data={
                        "image_url": image_url,
                        "caption": caption,
                        "access_token": access_token
                    }
                )

                container_data = container_response.json()

                if "error" in container_data:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "brand": brand,
                        "platform": "instagram",
                        "step": "create_container",
                        "error": container_data["error"]
                    }, indent=2))]

                container_id = container_data.get("id")

                # Step 2: Wait for container to be ready (check status)
                await asyncio.sleep(5)  # Give it time to process

                # Step 3: Publish the container
                publish_response = await client.post(
                    f"{GRAPH_API_URL}/{instagram_id}/media_publish",
                    data={
                        "creation_id": container_id,
                        "access_token": access_token
                    }
                )

                publish_data = publish_response.json()

                if "error" in publish_data:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "brand": brand,
                        "platform": "instagram",
                        "step": "publish",
                        "container_id": container_id,
                        "error": publish_data["error"]
                    }, indent=2))]

                result = {
                    "status": "success",
                    "brand": brand,
                    "platform": "instagram",
                    "instagram_id": instagram_id,
                    "media_id": publish_data.get("id"),
                    "container_id": container_id,
                    "published_at": datetime.now().isoformat()
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_latest_caption":
            language = arguments.get("language", "nl")

            # Query agent_outputs database for latest caption
            import asyncpg

            conn = await asyncpg.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME
            )

            try:
                row = await conn.fetchrow("""
                    SELECT id, title, content, created_at
                    FROM agent_outputs
                    WHERE agent_name = 'caption-generator'
                    ORDER BY created_at DESC
                    LIMIT 1
                """)

                if not row:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "not_found",
                        "message": "No caption-generator output found"
                    }))]

                result = {
                    "status": "success",
                    "language": language,
                    "output_id": row["id"],
                    "title": row["title"],
                    "content": row["content"][:2000],  # Truncate for safety
                    "created_at": row["created_at"].isoformat()
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            finally:
                await conn.close()

        elif name == "get_publication_status":
            brand = arguments.get("brand", "").lower()

            if brand not in BRANDS:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown brand: {brand}"}))]

            # Query agent_outputs for today's publications
            import asyncpg

            conn = await asyncpg.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME
            )

            try:
                rows = await conn.fetch("""
                    SELECT id, title, output_type, created_at
                    FROM agent_outputs
                    WHERE agent_name = 'feed-publisher'
                    AND created_at > NOW() - INTERVAL '24 hours'
                    AND (title ILIKE $1 OR content ILIKE $1)
                    ORDER BY created_at DESC
                """, f"%{brand}%")

                publications = []
                for row in rows:
                    publications.append({
                        "id": row["id"],
                        "title": row["title"],
                        "type": row["output_type"],
                        "created_at": row["created_at"].isoformat()
                    })

                result = {
                    "status": "success",
                    "brand": brand,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "publications_today": len(publications),
                    "recent": publications[:5]
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            finally:
                await conn.close()

        # =================================================================
        # TOKEN MANAGEMENT TOOL HANDLERS
        # =================================================================

        elif name == "check_token_health":
            brand = arguments.get("brand", "").lower()

            if brand not in BRANDS:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown brand: {brand}"}))]

            token = get_access_token(brand)
            if not token:
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "brand": brand,
                    "message": "No token configured for this brand"
                }))]

            result = await check_token_expiration(token)
            result["brand"] = brand
            result["token_preview"] = token[:30] + "..."

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "refresh_token":
            brand = arguments.get("brand", "").lower()
            new_short_token = arguments.get("new_short_token")

            if brand not in BRANDS:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown brand: {brand}"}))]

            # Use provided token or current token
            token_to_exchange = new_short_token or get_access_token(brand)

            if not token_to_exchange:
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "brand": brand,
                    "message": "No token to exchange"
                }))]

            # Exchange for long-lived token
            exchange_result = await exchange_for_long_lived_token(token_to_exchange)

            if not exchange_result.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "brand": brand,
                    "message": "Token exchange failed",
                    "error": exchange_result.get("error")
                }, indent=2))]

            # Update env file
            update_result = update_env_file(brand, exchange_result["token"])

            if not update_result.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "status": "partial_success",
                    "brand": brand,
                    "message": "Got new token but failed to update env file",
                    "error": update_result.get("error"),
                    "new_token": exchange_result["token"]
                }, indent=2))]

            # Log the refresh
            log_token_refresh(brand, exchange_result)

            result = {
                "status": "success",
                "brand": brand,
                "message": f"Token refreshed! Valid for {exchange_result['expires_in_days']} days",
                "expires_in_days": exchange_result["expires_in_days"],
                "expiration_date": exchange_result["expiration_date"],
                "env_file_updated": update_result.get("env_file"),
                "token_preview": exchange_result["token"][:50] + "..."
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "auto_refresh_all_tokens":
            results = {}

            for brand in BRANDS.keys():
                result = await auto_refresh_token_if_needed(brand)
                results[brand] = result

            summary = {
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "brands_checked": len(BRANDS),
                "results": results,
                "summary": {
                    "valid": sum(1 for r in results.values() if r.get("status") == "valid"),
                    "refreshed": sum(1 for r in results.values() if r.get("status") == "refreshed"),
                    "failed": sum(1 for r in results.values() if r.get("status") in ["error", "invalid", "refresh_failed", "update_failed"])
                }
            }

            return [TextContent(type="text", text=json.dumps(summary, indent=2))]

        elif name == "get_token_refresh_history":
            brand = arguments.get("brand", "").lower()
            limit = arguments.get("limit", 10)

            if brand not in BRANDS:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown brand: {brand}"}))]

            log_file = TOKEN_LOG_PATH / f'{brand}-refresh-history.json'

            if not log_file.exists():
                return [TextContent(type="text", text=json.dumps({
                    "status": "no_history",
                    "brand": brand,
                    "message": "No refresh history found"
                }))]

            history = json.loads(log_file.read_text(encoding='utf-8'))

            result = {
                "status": "success",
                "brand": brand,
                "total_entries": len(history),
                "history": history[-limit:][::-1]  # Latest first
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # =================================================================
        # IMAGE ANALYSIS TOOL HANDLER
        # =================================================================

        elif name == "view_image":
            key = arguments.get("key", "")

            if not key:
                return [TextContent(type="text", text=json.dumps({"error": "key is required"}))]

            try:
                s3 = get_s3_client()

                # Download image from S3
                response = s3.get_object(Bucket=AWS_BUCKET_NAME, Key=key)
                image_data = response['Body'].read()

                # Determine content type
                content_type = response.get('ContentType', 'image/jpeg')
                if 'png' in key.lower():
                    content_type = 'image/png'
                elif 'gif' in key.lower():
                    content_type = 'image/gif'
                elif 'webp' in key.lower():
                    content_type = 'image/webp'

                # Encode as base64
                image_base64 = base64.b64encode(image_data).decode('utf-8')

                logger.info(f"view_image: Loaded {key}, size={len(image_data)} bytes, type={content_type}")

                # Return ImageContent so Claude can see the image
                return [
                    TextContent(type="text", text=f"Image loaded: {key} ({len(image_data)} bytes)"),
                    ImageContent(
                        type="image",
                        data=image_base64,
                        mimeType=content_type
                    )
                ]

            except Exception as e:
                logger.error(f"view_image error: {e}")
                return [TextContent(type="text", text=json.dumps({
                    "error": f"Failed to load image: {str(e)}",
                    "key": key
                }))]

        elif name == "get_random_unused_photo":
            brand = arguments.get("brand", "pomandi").lower()
            days_lookback = arguments.get("days_lookback", 30)

            try:
                # Step 1: Get all products from S3
                s3 = get_s3_client()
                response = s3.list_objects_v2(
                    Bucket=AWS_BUCKET_NAME,
                    Prefix="products/",
                    MaxKeys=500
                )

                all_photos = []
                for obj in response.get('Contents', []):
                    key = obj['Key']
                    # Only include image files
                    if key.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        all_photos.append({
                            "key": key,
                            "size": obj['Size'],
                            "public_url": f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
                        })

                if not all_photos:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error",
                        "message": "No photos found in S3 bucket"
                    }))]

                # Step 2: Get recently used photos from database
                import asyncpg
                used_keys = set()

                try:
                    conn = await asyncpg.connect(
                        host=DB_HOST,
                        port=DB_PORT,
                        user=DB_USER,
                        password=DB_PASSWORD,
                        database=DB_NAME
                    )

                    rows = await conn.fetch("""
                        SELECT content
                        FROM agent_outputs
                        WHERE agent_name = 'feed-publisher'
                        AND created_at > NOW() - INTERVAL '%s days'
                        AND (title ILIKE $1 OR content ILIKE $1)
                    """ % days_lookback, f"%{brand}%")

                    for row in rows:
                        content = row["content"]
                        # Extract S3 keys from content
                        for photo in all_photos:
                            if photo["key"] in content or photo["public_url"] in content:
                                used_keys.add(photo["key"])

                    await conn.close()

                except Exception as db_err:
                    logger.warning(f"Could not check used photos: {db_err}")

                # Step 3: Filter out used photos
                unused_photos = [p for p in all_photos if p["key"] not in used_keys]

                if not unused_photos:
                    # If all photos used, reset and use all (with random selection)
                    unused_photos = all_photos
                    logger.info(f"All photos used for {brand}, resetting to full list")

                # Step 4: Select random photo
                selected = random.choice(unused_photos)

                result = {
                    "status": "success",
                    "brand": brand,
                    "total_photos": len(all_photos),
                    "used_photos": len(used_keys),
                    "available_photos": len(unused_photos),
                    "selected": selected,
                    "note": "Random selection from unused photos" if len(used_keys) > 0 else "Random selection from all photos"
                }

                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            except Exception as e:
                logger.error(f"get_random_unused_photo error: {e}")
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "error": str(e),
                    "type": type(e).__name__
                }))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        logger.error(f"Error in {name}: {e}")
        return [TextContent(type="text", text=json.dumps({
            "status": "error",
            "tool": name,
            "error": str(e),
            "type": type(e).__name__
        }, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
