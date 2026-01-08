"""
Social media activities - wraps MCP tools as Temporal activities.
"""
from temporalio import activity
from typing import Dict, Any, Optional
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

        # Generate public URL (without signature - required for Meta APIs)
        # Meta (Facebook/Instagram) APIs require clean URLs without query params
        region = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
        if region == 'us-east-1':
            # US East 1 uses different URL format
            public_url = f"https://{bucket}.s3.amazonaws.com/{selected_key}"
        else:
            public_url = f"https://{bucket}.s3.{region}.amazonaws.com/{selected_key}"

        # URL encode the key parts (spaces, special chars)
        from urllib.parse import quote
        encoded_key = quote(selected_key, safe='/')
        if region == 'us-east-1':
            public_url = f"https://{bucket}.s3.amazonaws.com/{encoded_key}"
        else:
            public_url = f"https://{bucket}.s3.{region}.amazonaws.com/{encoded_key}"

        activity.logger.info(f"Generated public URL: {public_url}")

        result = {
            "key": selected_key,
            "url": public_url,  # Use public URL instead of presigned
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
async def generate_caption(
    image_description: str,
    brand: str,
    language: str = "nl",
    image_url: Optional[str] = None
) -> str:
    """
    Generate social media caption using Claude.

    This is an AI task - might take 10-30 seconds.
    """
    activity.logger.info(f"Generating {language} caption for {brand}")

    try:
        from claude_agent_sdk import query, ClaudeAgentOptions

        # Build prompt with product description
        prompt = f"""Write a compelling social media caption in {language.upper()} for this product.

Brand: {brand}
Description: {image_description}
Link: https://pomandi.com/default-channel/appointment?locale={language}

CRITICAL RULES:
1. Output ONLY the caption text in {language.upper()}
2. NO English words. NO explanations. NO meta-text.
3. Start IMMEDIATELY with {language.upper()} text
4. Make it engaging and promotional
5. Include relevant emojis

Example START (for {language}):
{'"✨ Ontdek deze prachtige..." (if nl)' if language == 'nl' else '"✨ Découvrez ce magnifique..." (if fr)'}
"""

        # Build message content with image if available
        if image_url:
            # Download image and encode for Claude
            import httpx
            import base64

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(image_url)
                response.raise_for_status()
                image_data = response.content
                image_base64 = base64.b64encode(image_data).decode('utf-8')

            # Determine image type
            if image_url.lower().endswith('.png'):
                media_type = "image/png"
            elif image_url.lower().endswith('.webp'):
                media_type = "image/webp"
            else:
                media_type = "image/jpeg"

            # Create message with image
            message_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_base64,
                    }
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        else:
            message_content = prompt

        options = ClaudeAgentOptions(
            system_prompt=f"""You are a {language.upper()} social media copywriter.
Output ONLY {language.upper()} caption text. Nothing else.
NO English. NO meta-text. NO introductions. NO questions.
Your FIRST word MUST be in {language.upper()} language.
DO NOT ask to see images. DO NOT explain. Just write the caption.""",
            max_turns=1,
        )

        caption = ""
        async for message in query(prompt=message_content, options=options):
            if hasattr(message, 'content'):
                for block in message.content:
                    if hasattr(block, 'text'):
                        caption += block.text

        activity.heartbeat("Caption generated")

        # Post-processing: Remove common meta-text patterns
        caption_clean = caption.strip()

        # Remove English and Dutch/French meta-text if found
        meta_patterns = [
            "I need to see",
            "Here's a caption",
            "Based on the product",
            "I've created",
            "Here is",
            "Let me create",
            "I'll create",
            "Could you please",
            "Ik zie dat",  # Dutch: "I see that"
            "Ik heb",  # Dutch: "I have"
            "Je kunt",  # Dutch: "You can"
            "maar er is geen",  # Dutch: "but there is no"
            "Zou je",  # Dutch: "Would you"
            "Je vois que",  # French: "I see that"
            "J'ai besoin",  # French: "I need"
        ]

        for pattern in meta_patterns:
            if caption_clean.startswith(pattern):
                # Find the first line break or period after meta-text
                lines = caption_clean.split('\n', 1)
                if len(lines) > 1:
                    caption_clean = lines[1].strip()
                    activity.logger.warning(f"Removed meta-text starting with: {pattern}")
                    break

        # Extra safety: If caption starts with English and we want NL/FR, it's likely meta-text
        if caption_clean and not caption_clean[0].isalpha():
            # Starts with emoji/special char, probably ok
            pass
        elif language in ['nl', 'fr'] and caption_clean[:50].count('I ') > 0:
            # Contains English "I " pronouns in first 50 chars - likely meta-text
            activity.logger.warning("Detected English meta-text in non-English caption, attempting cleanup")
            # Try to find actual caption after first paragraph
            paragraphs = caption_clean.split('\n\n')
            if len(paragraphs) > 1:
                caption_clean = paragraphs[-1].strip()

        return caption_clean
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
                "user_access_token": os.getenv("META_ACCESS_TOKEN_POMANDI")
            },
            "costume": {
                "page_id": os.getenv("META_PAGE_ID_COSTUME", "101071881743506"),
                "user_access_token": os.getenv("META_ACCESS_TOKEN_COSTUME")
            }
        }

        config = brand_config.get(brand.lower())
        if not config or not config["user_access_token"]:
            raise ValueError(f"Missing Facebook configuration for brand: {brand}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Get page access token from user access token
            activity.logger.info("Fetching page access token...")
            accounts_response = await client.get(
                f"https://graph.facebook.com/v21.0/me/accounts",
                params={"access_token": config["user_access_token"]}
            )
            accounts_response.raise_for_status()
            accounts_data = accounts_response.json()

            # Find the page access token for our page ID
            page_access_token = None
            for page in accounts_data.get("data", []):
                if page["id"] == config["page_id"]:
                    page_access_token = page["access_token"]
                    activity.logger.info(f"Found page access token for {page['name']}")
                    break

            if not page_access_token:
                raise ValueError(f"Page ID {config['page_id']} not found in accessible pages")

            # Step 2: Publish to Facebook Page using page access token
            activity.logger.info(f"Publishing photo to Facebook: {image_url[:100]}...")
            response = await client.post(
                f"https://graph.facebook.com/v21.0/{config['page_id']}/photos",
                data={
                    "url": image_url,
                    "caption": caption,
                    "access_token": page_access_token
                }
            )

            # Log error details before raising
            if response.status_code != 200:
                error_body = response.text
                activity.logger.error(f"Facebook API error {response.status_code}: {error_body}")
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
                "page_id": os.getenv("META_PAGE_ID_POMANDI", "335388637037718"),
                "instagram_id": os.getenv("META_IG_ACCOUNT_ID_POMANDI", "17841406855004574"),
                "user_access_token": os.getenv("META_ACCESS_TOKEN_POMANDI")
            },
            "costume": {
                "page_id": os.getenv("META_PAGE_ID_COSTUME", "101071881743506"),
                "instagram_id": os.getenv("META_IG_ACCOUNT_ID_COSTUME", "17841441106266856"),
                "user_access_token": os.getenv("META_ACCESS_TOKEN_COSTUME")
            }
        }

        config = brand_config.get(brand.lower())
        if not config or not config["user_access_token"]:
            raise ValueError(f"Missing Instagram configuration for brand: {brand}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 0: Get page access token from user access token
            activity.logger.info("Fetching page access token...")
            accounts_response = await client.get(
                f"https://graph.facebook.com/v21.0/me/accounts",
                params={"access_token": config["user_access_token"]}
            )
            accounts_response.raise_for_status()
            accounts_data = accounts_response.json()

            # Find the page access token for our page ID
            page_access_token = None
            for page in accounts_data.get("data", []):
                if page["id"] == config["page_id"]:
                    page_access_token = page["access_token"]
                    activity.logger.info(f"Found page access token for {page['name']}")
                    break

            if not page_access_token:
                raise ValueError(f"Page ID {config['page_id']} not found in accessible pages")

            # Step 1: Create media container
            activity.logger.info(f"Creating Instagram media container for image: {image_url[:100]}...")
            create_response = await client.post(
                f"https://graph.facebook.com/v21.0/{config['instagram_id']}/media",
                data={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": page_access_token
                }
            )

            # Log error details before raising
            if create_response.status_code != 200:
                error_body = create_response.text
                activity.logger.error(f"Instagram API error {create_response.status_code}: {error_body}")
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
                    "access_token": page_access_token
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
