"""
Social media activities - wraps MCP tools as Temporal activities.
"""
from temporalio import activity
from typing import Dict, Any
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from temporal_app.monitoring import observe_activity

logger = logging.getLogger(__name__)

@activity.defn
async def get_random_unused_photo(brand: str) -> Dict[str, Any]:
    """
    Get random unused product photo from S3.

    Wraps: mcp__feed-publisher-mcp__get_random_unused_photo
    """
    activity.logger.info(f"Getting random photo for brand: {brand}")

    try:
        import boto3
        import random
        from botocore.config import Config
        import psycopg2

        # AWS S3 config
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
            config=Config(signature_version='s3v4')
        )

        bucket = os.getenv('AWS_STORAGE_BUCKET_NAME', 'saleorme')

        # List product images from S3
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix='products/',
            MaxKeys=1000
        )

        if 'Contents' not in response:
            raise ValueError("No product images found in S3")

        # Filter image files
        image_keys = [
            obj['Key'] for obj in response['Contents']
            if obj['Key'].lower().endswith(('.jpg', '.jpeg', '.png'))
        ]

        # Get recently used photos from database (last 15 days)
        try:
            conn = psycopg2.connect(
                host=os.getenv('POSTGRES_HOST', '127.0.0.1'),
                port=int(os.getenv('POSTGRES_PORT', 5433)),
                database=os.getenv('POSTGRES_DB', 'postgres'),
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD'),
            )
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT content->>'photo_key' as photo_key
                FROM agent_outputs
                WHERE agent_name = 'feed-publisher'
                  AND created_at > NOW() - INTERVAL '15 days'
                  AND content->>'brand' = %s
                  AND content->>'photo_key' IS NOT NULL
            """, (brand,))

            used_keys = {row[0] for row in cursor.fetchall()}
            cursor.close()
            conn.close()
        except Exception as e:
            activity.logger.warning(f"Could not check used photos: {e}")
            used_keys = set()

        # Filter out recently used photos
        available_keys = [k for k in image_keys if k not in used_keys]

        if not available_keys:
            activity.logger.warning("No unused photos, using all photos")
            available_keys = image_keys

        # Select random photo
        selected_key = random.choice(available_keys)

        # Generate presigned URL
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': selected_key},
            ExpiresIn=3600
        )

        result = {
            "key": selected_key,
            "url": url,
            "brand": brand
        }

        activity.heartbeat(f"Photo selected: {selected_key}")

        return result
    except Exception as e:
        activity.logger.error(f"Failed to get random photo: {e}")
        raise

@activity.defn
async def view_image(s3_key: str) -> Dict[str, Any]:
    """
    View/analyze image from S3 using Claude vision.

    Wraps: mcp__feed-publisher-mcp__view_image
    """
    activity.logger.info(f"Viewing image: {s3_key}")

    try:
        import boto3
        from botocore.config import Config
        import base64

        # Get image from S3
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
            config=Config(signature_version='s3v4')
        )

        bucket = os.getenv('AWS_STORAGE_BUCKET_NAME', 'saleorme')

        # Download image
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        image_data = response['Body'].read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        # Determine image type
        content_type = response.get('ContentType', 'image/jpeg')

        # Use Claude SDK to analyze image
        from claude_agent_sdk import query, ClaudeAgentOptions

        prompt = f"""Analyze this product image and describe it in detail for social media marketing.

Focus on:
- Product type (suit, dress, accessories)
- Colors and patterns
- Style and occasion
- Notable features or details

Provide a concise, marketing-focused description (2-3 sentences)."""

        options = ClaudeAgentOptions(
            system_prompt="You are a fashion expert analyzing product images for social media marketing.",
            max_turns=1,
        )

        description = ""
        async for message in query(prompt=prompt, options=options):
            if hasattr(message, 'content'):
                for block in message.content:
                    if hasattr(block, 'text'):
                        description += block.text

        result = {
            "description": description.strip() or "Product image",
            "key": s3_key
        }

        return result
    except Exception as e:
        activity.logger.error(f"Failed to view image: {e}")
        # Fallback to basic description
        return {
            "description": f"Product from {s3_key}",
            "key": s3_key
        }

@activity.defn
@observe_activity
async def generate_caption(
    image_description: str,
    brand: str,
    language: str = "nl"
) -> str:
    """
    Generate social media caption using Claude.

    This is an AI task - might take 10-30 seconds.
    """
    activity.logger.info(f"Generating {language} caption for {brand}")

    try:
        from claude_agent_sdk import query, ClaudeAgentOptions

        prompt = f"""Create a compelling {language.upper()} social media caption for this product:

Product: {image_description}
Brand: {brand}
Language: {language}

Requirements:
- Engaging and authentic
- Include product highlights
- Add call-to-action
- Include appointment link: https://pomandi.com/default-channel/appointment?locale={language}
- Max 2200 characters
- Natural and conversational tone

Return ONLY the caption text, no explanations.
"""

        options = ClaudeAgentOptions(
            system_prompt="You are a social media marketing expert specializing in fashion and formal wear.",
            max_turns=1,
        )

        caption = ""
        async for message in query(prompt=prompt, options=options):
            if hasattr(message, 'content'):
                for block in message.content:
                    if hasattr(block, 'text'):
                        caption += block.text

        activity.heartbeat("Caption generated")

        return caption.strip()
    except Exception as e:
        activity.logger.error(f"Failed to generate caption: {e}")
        raise

@activity.defn
async def publish_facebook_photo(
    brand: str,
    image_url: str,
    caption: str
) -> Dict[str, Any]:
    """
    Publish photo to Facebook.

    Wraps: mcp__feed-publisher-mcp__publish_facebook_photo
    """
    activity.logger.info(f"Publishing to Facebook for {brand}")

    try:
        import httpx

        # Brand configuration
        brand_config = {
            "pomandi": {
                "page_id": os.getenv("META_PAGE_ID_POMANDI", "335388637037718"),
                "access_token": os.getenv("META_ACCESS_TOKEN_POMANDI")
            },
            "costume": {
                "page_id": os.getenv("META_PAGE_ID_COSTUME", "101071881743506"),
                "access_token": os.getenv("META_ACCESS_TOKEN_COSTUME")
            }
        }

        config = brand_config.get(brand.lower())
        if not config or not config["access_token"]:
            raise ValueError(f"Missing Facebook configuration for brand: {brand}")

        # Publish to Facebook Page
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://graph.facebook.com/v21.0/{config['page_id']}/photos",
                data={
                    "url": image_url,
                    "caption": caption,
                    "access_token": config["access_token"]
                }
            )

            response.raise_for_status()
            data = response.json()

        result = {
            "success": True,
            "post_id": data.get("post_id") or data.get("id"),
            "brand": brand
        }

        activity.heartbeat(f"FB post created: {result.get('post_id')}")

        return result
    except Exception as e:
        activity.logger.error(f"Failed to publish to Facebook: {e}")
        raise

@activity.defn
async def publish_instagram_photo(
    brand: str,
    image_url: str,
    caption: str
) -> Dict[str, Any]:
    """
    Publish photo to Instagram.

    Wraps: mcp__feed-publisher-mcp__publish_instagram_photo
    """
    activity.logger.info(f"Publishing to Instagram for {brand}")

    try:
        import httpx
        import asyncio

        # Brand configuration
        brand_config = {
            "pomandi": {
                "instagram_id": os.getenv("META_IG_ACCOUNT_ID_POMANDI", "17841406855004574"),
                "access_token": os.getenv("META_ACCESS_TOKEN_POMANDI")
            },
            "costume": {
                "instagram_id": os.getenv("META_IG_ACCOUNT_ID_COSTUME", "17841441106266856"),
                "access_token": os.getenv("META_ACCESS_TOKEN_COSTUME")
            }
        }

        config = brand_config.get(brand.lower())
        if not config or not config["access_token"]:
            raise ValueError(f"Missing Instagram configuration for brand: {brand}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: Create media container
            activity.logger.info("Creating Instagram media container...")
            create_response = await client.post(
                f"https://graph.facebook.com/v21.0/{config['instagram_id']}/media",
                data={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": config["access_token"]
                }
            )

            create_response.raise_for_status()
            create_data = create_response.json()
            container_id = create_data.get("id")

            if not container_id:
                raise ValueError("Failed to create Instagram media container")

            activity.heartbeat(f"Container created: {container_id}")

            # Step 2: Wait for container to be ready (usually takes 5-10 seconds)
            activity.logger.info("Waiting for container to be ready...")
            await asyncio.sleep(10)

            # Step 3: Publish the container
            activity.logger.info("Publishing Instagram post...")
            publish_response = await client.post(
                f"https://graph.facebook.com/v21.0/{config['instagram_id']}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": config["access_token"]
                }
            )

            publish_response.raise_for_status()
            publish_data = publish_response.json()

        result = {
            "success": True,
            "media_id": publish_data.get("id"),
            "brand": brand
        }

        activity.heartbeat(f"IG post created: {result.get('media_id')}")

        return result
    except Exception as e:
        activity.logger.error(f"Failed to publish to Instagram: {e}")
        raise

@activity.defn
async def save_publication_report(
    brand: str,
    photo_key: str,
    facebook_post_id: str,
    instagram_media_id: str,
    caption: str
) -> Dict[str, Any]:
    """
    Save publication report to database.

    Wraps: mcp__agent-outputs-mcp__save_output
    """
    activity.logger.info("Saving publication report")

    try:
        import json
        from datetime import datetime
        import psycopg2

        content = {
            "brand": brand,
            "photo_key": photo_key,
            "facebook_post_id": facebook_post_id,
            "instagram_media_id": instagram_media_id,
            "caption_preview": caption[:100] + "..." if len(caption) > 100 else caption,
            "published_at": datetime.utcnow().isoformat()
        }

        # Save to agent_outputs database
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', '127.0.0.1'),
            port=int(os.getenv('POSTGRES_PORT', 5433)),
            database=os.getenv('POSTGRES_DB', 'postgres'),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD'),
        )
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_outputs (
                id SERIAL PRIMARY KEY,
                agent_name VARCHAR(255) NOT NULL,
                output_type VARCHAR(50) NOT NULL,
                title VARCHAR(500),
                content JSONB,
                metadata JSONB,
                tags TEXT[],
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert report
        cursor.execute("""
            INSERT INTO agent_outputs (agent_name, output_type, title, content, tags)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (
            'feed-publisher',
            'report',
            f'{brand.capitalize()} - Social Media Post',
            json.dumps(content),
            [brand, 'social-media', 'feed-post']
        ))

        report_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        result = {
            "success": True,
            "report_id": str(report_id),
            "content": content
        }

        activity.logger.info(f"Report saved with ID: {report_id}")

        return result
    except Exception as e:
        activity.logger.error(f"Failed to save report: {e}")
        raise
