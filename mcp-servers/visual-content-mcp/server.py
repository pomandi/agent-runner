#!/usr/bin/env python3
"""
Visual Content MCP Server
Image and video manipulation for social media publishing.
Uses Pillow for images, FFmpeg for video, with quality control validation.
"""
import os
import sys
import json
import asyncio
import tempfile
import subprocess
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional
import urllib.request
import ssl

# MCP SDK
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent
from mcp.server.stdio import stdio_server

# Image processing
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# AWS S3
try:
    import boto3
    from botocore.config import Config
    BOTO_AVAILABLE = True
except ImportError:
    BOTO_AVAILABLE = False

# ============================================================================
# PLATFORM SPECIFICATIONS
# ============================================================================

PLATFORM_SPECS = {
    # Instagram
    "instagram_feed_square": {
        "width": 1080, "height": 1080, "aspect": "1:1",
        "description": "Instagram Feed Square"
    },
    "instagram_feed_portrait": {
        "width": 1080, "height": 1350, "aspect": "4:5",
        "description": "Instagram Feed Portrait (recommended)"
    },
    "instagram_feed_landscape": {
        "width": 1080, "height": 566, "aspect": "1.91:1",
        "description": "Instagram Feed Landscape"
    },
    "instagram_story": {
        "width": 1080, "height": 1920, "aspect": "9:16",
        "description": "Instagram Story / Reels"
    },

    # Facebook
    "facebook_feed": {
        "width": 1200, "height": 630, "aspect": "1.91:1",
        "description": "Facebook Feed (link preview)"
    },
    "facebook_feed_square": {
        "width": 1080, "height": 1080, "aspect": "1:1",
        "description": "Facebook Feed Square"
    },
    "facebook_story": {
        "width": 1080, "height": 1920, "aspect": "9:16",
        "description": "Facebook Story"
    },

    # General
    "square": {
        "width": 1080, "height": 1080, "aspect": "1:1",
        "description": "Square (works everywhere)"
    },
    "story": {
        "width": 1080, "height": 1920, "aspect": "9:16",
        "description": "Story format (IG/FB Story)"
    }
}

# ============================================================================
# QUALITY CONTROL RULES
# ============================================================================

QUALITY_RULES = {
    "instagram_story": {
        "min_width": 1080,
        "min_height": 1920,
        "aspect_ratio": (9, 16),
        "aspect_tolerance": 0.01,
        "max_file_size_mb": 30,
        "allowed_formats": ["jpg", "jpeg", "png"]
    },
    "instagram_feed": {
        "min_width": 1080,
        "min_height": 566,
        "aspect_ratio_options": [(1, 1), (4, 5), (1.91, 1)],
        "aspect_tolerance": 0.02,
        "max_file_size_mb": 30,
        "allowed_formats": ["jpg", "jpeg", "png"]
    },
    "facebook_story": {
        "min_width": 1080,
        "min_height": 1920,
        "aspect_ratio": (9, 16),
        "aspect_tolerance": 0.01,
        "max_file_size_mb": 30,
        "allowed_formats": ["jpg", "jpeg", "png"]
    },
    "facebook_feed": {
        "min_width": 600,
        "min_height": 315,
        "max_file_size_mb": 30,
        "allowed_formats": ["jpg", "jpeg", "png", "gif"]
    }
}

# ============================================================================
# SERVER SETUP
# ============================================================================

server = Server("visual-content-mcp")

# Temp directory for processing
TEMP_DIR = Path(tempfile.gettempdir()) / "visual-content"
TEMP_DIR.mkdir(exist_ok=True)

# Output directory (persistent)
OUTPUT_DIR = Path("/app/data/visual-content") if Path("/app").exists() else Path.home() / ".visual-content"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# S3 client
s3_client = None
if BOTO_AVAILABLE:
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
            config=Config(signature_version='s3v4')
        )
    except Exception:
        s3_client = None

BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', 'saleorme')

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def download_image(url_or_key: str) -> Path:
    """Download image from URL or S3 key."""
    local_path = TEMP_DIR / f"input_{datetime.now().strftime('%H%M%S')}.jpg"

    if url_or_key.startswith(('http://', 'https://')):
        # Download from URL
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        urllib.request.urlretrieve(url_or_key, local_path)
    elif s3_client and not url_or_key.startswith('/'):
        # Download from S3
        key = url_or_key
        if not key.startswith('products/'):
            key = f"products/{key}"
        s3_client.download_file(BUCKET_NAME, key, str(local_path))
    else:
        # Local file
        local_path = Path(url_or_key)

    return local_path


def upload_to_s3(local_path: Path, prefix: str = "enhanced") -> dict:
    """Upload processed image to S3 and return URLs."""
    if not s3_client:
        return {"error": "S3 not configured", "local_path": str(local_path)}

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{prefix}_{timestamp}_{local_path.name}"
    s3_key = f"enhanced/{filename}"

    # Upload
    content_type = "image/jpeg" if local_path.suffix.lower() in ['.jpg', '.jpeg'] else "image/png"
    s3_client.upload_file(
        str(local_path),
        BUCKET_NAME,
        s3_key,
        ExtraArgs={'ContentType': content_type}
    )

    # Generate presigned URL
    presigned_url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': BUCKET_NAME, 'Key': s3_key},
        ExpiresIn=86400  # 24 hours
    )

    return {
        "s3_key": s3_key,
        "presigned_url": presigned_url,
        "bucket": BUCKET_NAME
    }


def get_font(size: int = 48, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Get a font, falling back to default if custom fonts not available."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]

    for font_path in font_paths:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue

    # Fallback to default
    return ImageFont.load_default()


def validate_image_quality(image_path: Path, platform: str) -> dict:
    """Validate image meets platform requirements."""
    if not PIL_AVAILABLE:
        return {"valid": False, "error": "PIL not available"}

    rules = QUALITY_RULES.get(platform)
    if not rules:
        return {"valid": True, "warning": f"No rules defined for {platform}"}

    issues = []
    warnings = []

    with Image.open(image_path) as img:
        width, height = img.size
        file_size_mb = image_path.stat().st_size / (1024 * 1024)
        file_format = image_path.suffix.lower().replace('.', '')

        # Check dimensions
        if width < rules.get("min_width", 0):
            issues.append(f"Width {width}px < minimum {rules['min_width']}px")

        if height < rules.get("min_height", 0):
            issues.append(f"Height {height}px < minimum {rules['min_height']}px")

        # Check aspect ratio
        if "aspect_ratio" in rules:
            target_w, target_h = rules["aspect_ratio"]
            target_ratio = target_w / target_h
            actual_ratio = width / height
            tolerance = rules.get("aspect_tolerance", 0.02)

            if abs(actual_ratio - target_ratio) > tolerance:
                issues.append(f"Aspect ratio {width}:{height} ({actual_ratio:.2f}) != required {target_w}:{target_h} ({target_ratio:.2f})")

        # Check file size
        if file_size_mb > rules.get("max_file_size_mb", 30):
            issues.append(f"File size {file_size_mb:.1f}MB > maximum {rules['max_file_size_mb']}MB")

        # Check format
        allowed_formats = rules.get("allowed_formats", ["jpg", "jpeg", "png"])
        if file_format not in allowed_formats:
            warnings.append(f"Format {file_format} not in recommended: {allowed_formats}")

    return {
        "valid": len(issues) == 0,
        "platform": platform,
        "dimensions": f"{width}x{height}",
        "aspect_ratio": f"{width/height:.2f}",
        "file_size_mb": round(file_size_mb, 2),
        "format": file_format,
        "issues": issues,
        "warnings": warnings
    }


# ============================================================================
# MCP TOOLS
# ============================================================================

@server.list_tools()
async def list_tools():
    return [
        # Image Manipulation
        Tool(
            name="add_price_banner",
            description="Add a price banner/tag to an image. Positions: top-left, top-right, bottom-left, bottom-right. Colors: red, green, blue, gold, black.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "description": "S3 key (e.g., 'products/image.jpg'), URL, or local path"
                    },
                    "price": {
                        "type": "string",
                        "description": "Price text (e.g., '\u20ac320', '$299', '\u20ac199.99')"
                    },
                    "position": {
                        "type": "string",
                        "enum": ["top-left", "top-right", "bottom-left", "bottom-right"],
                        "default": "top-right"
                    },
                    "color": {
                        "type": "string",
                        "enum": ["red", "green", "blue", "gold", "black", "white"],
                        "default": "red"
                    },
                    "upload_to_s3": {
                        "type": "boolean",
                        "default": True
                    }
                },
                "required": ["image_source", "price"]
            }
        ),

        Tool(
            name="add_text_overlay",
            description="Add custom text overlay to an image. Good for 'NIEUW!', 'SALE -30%', 'Gratis verzending', etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "description": "S3 key, URL, or local path"
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to add"
                    },
                    "position": {
                        "type": "string",
                        "enum": ["top", "center", "bottom", "top-left", "top-right", "bottom-left", "bottom-right"],
                        "default": "bottom"
                    },
                    "font_size": {
                        "type": "integer",
                        "default": 48
                    },
                    "text_color": {
                        "type": "string",
                        "default": "white"
                    },
                    "background_color": {
                        "type": "string",
                        "default": "rgba(0,0,0,0.7)"
                    },
                    "upload_to_s3": {
                        "type": "boolean",
                        "default": True
                    }
                },
                "required": ["image_source", "text"]
            }
        ),

        Tool(
            name="add_logo_watermark",
            description="Add brand logo as watermark. Supports Pomandi and Costume logos, or custom logo URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "description": "S3 key, URL, or local path"
                    },
                    "brand": {
                        "type": "string",
                        "enum": ["pomandi", "costume", "custom"],
                        "default": "pomandi"
                    },
                    "logo_url": {
                        "type": "string",
                        "description": "Custom logo URL (only if brand='custom')"
                    },
                    "position": {
                        "type": "string",
                        "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"],
                        "default": "bottom-right"
                    },
                    "opacity": {
                        "type": "number",
                        "minimum": 0.1,
                        "maximum": 1.0,
                        "default": 0.7
                    },
                    "size_percent": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 50,
                        "default": 15,
                        "description": "Logo size as percentage of image width"
                    },
                    "upload_to_s3": {
                        "type": "boolean",
                        "default": True
                    }
                },
                "required": ["image_source"]
            }
        ),

        Tool(
            name="resize_for_platform",
            description="Resize and crop image for specific social media platform. Automatically handles aspect ratios.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "description": "S3 key, URL, or local path"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["instagram_feed_square", "instagram_feed_portrait", "instagram_feed_landscape", "instagram_story", "facebook_feed", "facebook_feed_square", "facebook_story", "square", "story"],
                        "description": "Target platform format"
                    },
                    "fit_mode": {
                        "type": "string",
                        "enum": ["cover", "contain", "stretch"],
                        "default": "cover",
                        "description": "cover=crop to fill, contain=fit with padding, stretch=distort"
                    },
                    "background_color": {
                        "type": "string",
                        "default": "white",
                        "description": "Background color for 'contain' mode"
                    },
                    "upload_to_s3": {
                        "type": "boolean",
                        "default": True
                    }
                },
                "required": ["image_source", "platform"]
            }
        ),

        Tool(
            name="apply_filter",
            description="Apply visual filters to enhance image. Adjust brightness, contrast, saturation, or apply blur/sharpen.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "description": "S3 key, URL, or local path"
                    },
                    "brightness": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 2.0,
                        "default": 1.0,
                        "description": "1.0 = no change, >1 = brighter, <1 = darker"
                    },
                    "contrast": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 2.0,
                        "default": 1.0
                    },
                    "saturation": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 2.0,
                        "default": 1.0,
                        "description": "0 = grayscale, 1 = normal, 2 = very saturated"
                    },
                    "sharpen": {
                        "type": "boolean",
                        "default": False
                    },
                    "blur": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                        "default": 0,
                        "description": "Blur radius (0 = no blur)"
                    },
                    "upload_to_s3": {
                        "type": "boolean",
                        "default": True
                    }
                },
                "required": ["image_source"]
            }
        ),

        Tool(
            name="add_border",
            description="Add a colored border/frame around the image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "description": "S3 key, URL, or local path"
                    },
                    "border_width": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20
                    },
                    "border_color": {
                        "type": "string",
                        "default": "white",
                        "description": "Color name or hex (e.g., 'gold', '#FFD700')"
                    },
                    "upload_to_s3": {
                        "type": "boolean",
                        "default": True
                    }
                },
                "required": ["image_source"]
            }
        ),

        Tool(
            name="create_slideshow",
            description="Create a video slideshow from multiple images using FFmpeg.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of S3 keys, URLs, or local paths"
                    },
                    "duration_per_image": {
                        "type": "number",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 3,
                        "description": "Seconds per image"
                    },
                    "transition": {
                        "type": "string",
                        "enum": ["none", "fade", "slide"],
                        "default": "fade"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["mp4", "gif"],
                        "default": "mp4"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["instagram_story", "instagram_feed_square", "facebook_feed"],
                        "default": "instagram_feed_square"
                    },
                    "upload_to_s3": {
                        "type": "boolean",
                        "default": True
                    }
                },
                "required": ["image_sources"]
            }
        ),

        Tool(
            name="validate_for_platform",
            description="QUALITY CONTROL: Validate that an image meets platform requirements (dimensions, aspect ratio, file size). ALWAYS call this before publishing!",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "description": "S3 key, URL, or local path"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["instagram_story", "instagram_feed", "facebook_story", "facebook_feed"],
                        "description": "Target platform to validate against"
                    }
                },
                "required": ["image_source", "platform"]
            }
        ),

        Tool(
            name="get_platform_specs",
            description="Get dimension and format specifications for all supported platforms.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),

        Tool(
            name="view_image",
            description="View/preview an image from S3 or URL. Returns the image for visual inspection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "description": "S3 key, URL, or local path"
                    }
                },
                "required": ["image_source"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        # ----------------------------------------------------------------
        # ADD PRICE BANNER
        # ----------------------------------------------------------------
        if name == "add_price_banner":
            if not PIL_AVAILABLE:
                return [TextContent(type="text", text="Error: PIL not available")]

            image_path = download_image(arguments["image_source"])
            price = arguments["price"]
            position = arguments.get("position", "top-right")
            color = arguments.get("color", "red")
            upload = arguments.get("upload_to_s3", True)

            # Color mapping
            colors = {
                "red": ("#FF0000", "white"),
                "green": ("#00AA00", "white"),
                "blue": ("#0066CC", "white"),
                "gold": ("#FFD700", "black"),
                "black": ("#000000", "white"),
                "white": ("#FFFFFF", "black")
            }
            bg_color, text_color = colors.get(color, ("#FF0000", "white"))

            with Image.open(image_path) as img:
                img = img.convert("RGBA")
                draw = ImageDraw.Draw(img)

                # Calculate banner size
                font = get_font(size=max(36, img.width // 15))
                bbox = draw.textbbox((0, 0), price, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                padding = 20

                # Position
                positions = {
                    "top-left": (10, 10),
                    "top-right": (img.width - text_width - padding * 2 - 10, 10),
                    "bottom-left": (10, img.height - text_height - padding * 2 - 10),
                    "bottom-right": (img.width - text_width - padding * 2 - 10, img.height - text_height - padding * 2 - 10)
                }
                x, y = positions.get(position, positions["top-right"])

                # Draw banner background
                draw.rectangle(
                    [x, y, x + text_width + padding * 2, y + text_height + padding * 2],
                    fill=bg_color
                )

                # Draw text
                draw.text((x + padding, y + padding), price, font=font, fill=text_color)

                # Save
                output_path = TEMP_DIR / f"price_{datetime.now().strftime('%H%M%S')}.png"
                img.save(output_path, "PNG")

            result = {"local_path": str(output_path), "price": price, "position": position}

            if upload:
                s3_result = upload_to_s3(output_path, "price")
                result.update(s3_result)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ----------------------------------------------------------------
        # ADD TEXT OVERLAY
        # ----------------------------------------------------------------
        elif name == "add_text_overlay":
            if not PIL_AVAILABLE:
                return [TextContent(type="text", text="Error: PIL not available")]

            image_path = download_image(arguments["image_source"])
            text = arguments["text"]
            position = arguments.get("position", "bottom")
            font_size = arguments.get("font_size", 48)
            text_color = arguments.get("text_color", "white")
            bg_color = arguments.get("background_color", "rgba(0,0,0,0.7)")
            upload = arguments.get("upload_to_s3", True)

            with Image.open(image_path) as img:
                img = img.convert("RGBA")

                # Create overlay layer
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)

                font = get_font(size=font_size)
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                padding = 15

                # Calculate position
                if position == "top":
                    x = (img.width - text_width) // 2
                    y = 20
                elif position == "center":
                    x = (img.width - text_width) // 2
                    y = (img.height - text_height) // 2
                elif position == "bottom":
                    x = (img.width - text_width) // 2
                    y = img.height - text_height - 40
                elif position == "top-left":
                    x, y = 20, 20
                elif position == "top-right":
                    x = img.width - text_width - 20
                    y = 20
                elif position == "bottom-left":
                    x = 20
                    y = img.height - text_height - 40
                elif position == "bottom-right":
                    x = img.width - text_width - 20
                    y = img.height - text_height - 40
                else:
                    x = (img.width - text_width) // 2
                    y = img.height - text_height - 40

                # Draw background rectangle
                draw.rectangle(
                    [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
                    fill=(0, 0, 0, 180)
                )

                # Draw text
                draw.text((x, y), text, font=font, fill=text_color)

                # Composite
                img = Image.alpha_composite(img, overlay)

                output_path = TEMP_DIR / f"text_{datetime.now().strftime('%H%M%S')}.png"
                img.save(output_path, "PNG")

            result = {"local_path": str(output_path), "text": text, "position": position}

            if upload:
                s3_result = upload_to_s3(output_path, "text")
                result.update(s3_result)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ----------------------------------------------------------------
        # ADD LOGO WATERMARK
        # ----------------------------------------------------------------
        elif name == "add_logo_watermark":
            if not PIL_AVAILABLE:
                return [TextContent(type="text", text="Error: PIL not available")]

            image_path = download_image(arguments["image_source"])
            brand = arguments.get("brand", "pomandi")
            position = arguments.get("position", "bottom-right")
            opacity = arguments.get("opacity", 0.7)
            size_percent = arguments.get("size_percent", 15)
            upload = arguments.get("upload_to_s3", True)

            with Image.open(image_path) as img:
                img = img.convert("RGBA")

                # Create a simple text-based logo
                logo_size = int(img.width * size_percent / 100)
                logo = Image.new("RGBA", (logo_size, logo_size // 2), (0, 0, 0, 0))
                draw = ImageDraw.Draw(logo)
                font = get_font(size=logo_size // 4)
                brand_text = brand.upper() if brand != "custom" else "LOGO"
                draw.text((10, 10), brand_text, font=font, fill=(255, 255, 255, int(255 * opacity)))

                # Position
                positions = {
                    "top-left": (10, 10),
                    "top-right": (img.width - logo_size - 10, 10),
                    "bottom-left": (10, img.height - logo_size // 2 - 10),
                    "bottom-right": (img.width - logo_size - 10, img.height - logo_size // 2 - 10),
                    "center": ((img.width - logo_size) // 2, (img.height - logo_size // 2) // 2)
                }
                x, y = positions.get(position, positions["bottom-right"])

                # Paste logo
                img.paste(logo, (x, y), logo)

                output_path = TEMP_DIR / f"logo_{datetime.now().strftime('%H%M%S')}.png"
                img.save(output_path, "PNG")

            result = {"local_path": str(output_path), "brand": brand, "position": position}

            if upload:
                s3_result = upload_to_s3(output_path, "logo")
                result.update(s3_result)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ----------------------------------------------------------------
        # RESIZE FOR PLATFORM
        # ----------------------------------------------------------------
        elif name == "resize_for_platform":
            if not PIL_AVAILABLE:
                return [TextContent(type="text", text="Error: PIL not available")]

            image_path = download_image(arguments["image_source"])
            platform = arguments["platform"]
            fit_mode = arguments.get("fit_mode", "cover")
            bg_color = arguments.get("background_color", "white")
            upload = arguments.get("upload_to_s3", True)

            specs = PLATFORM_SPECS.get(platform)
            if not specs:
                return [TextContent(type="text", text=f"Error: Unknown platform {platform}")]

            target_w, target_h = specs["width"], specs["height"]

            with Image.open(image_path) as img:
                img = img.convert("RGB")
                orig_w, orig_h = img.size

                if fit_mode == "cover":
                    # Crop to fill
                    ratio = max(target_w / orig_w, target_h / orig_h)
                    new_w = int(orig_w * ratio)
                    new_h = int(orig_h * ratio)
                    img = img.resize((new_w, new_h), Image.LANCZOS)

                    # Center crop
                    left = (new_w - target_w) // 2
                    top = (new_h - target_h) // 2
                    img = img.crop((left, top, left + target_w, top + target_h))

                elif fit_mode == "contain":
                    # Fit inside with padding
                    ratio = min(target_w / orig_w, target_h / orig_h)
                    new_w = int(orig_w * ratio)
                    new_h = int(orig_h * ratio)
                    img = img.resize((new_w, new_h), Image.LANCZOS)

                    # Create canvas with background
                    canvas = Image.new("RGB", (target_w, target_h), bg_color)
                    x = (target_w - new_w) // 2
                    y = (target_h - new_h) // 2
                    canvas.paste(img, (x, y))
                    img = canvas

                else:  # stretch
                    img = img.resize((target_w, target_h), Image.LANCZOS)

                output_path = TEMP_DIR / f"{platform}_{datetime.now().strftime('%H%M%S')}.jpg"
                img.save(output_path, "JPEG", quality=95)

            result = {
                "local_path": str(output_path),
                "platform": platform,
                "dimensions": f"{target_w}x{target_h}",
                "aspect": specs["aspect"],
                "fit_mode": fit_mode
            }

            if upload:
                s3_result = upload_to_s3(output_path, platform)
                result.update(s3_result)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ----------------------------------------------------------------
        # APPLY FILTER
        # ----------------------------------------------------------------
        elif name == "apply_filter":
            if not PIL_AVAILABLE:
                return [TextContent(type="text", text="Error: PIL not available")]

            image_path = download_image(arguments["image_source"])
            brightness = arguments.get("brightness", 1.0)
            contrast = arguments.get("contrast", 1.0)
            saturation = arguments.get("saturation", 1.0)
            sharpen = arguments.get("sharpen", False)
            blur = arguments.get("blur", 0)
            upload = arguments.get("upload_to_s3", True)

            with Image.open(image_path) as img:
                img = img.convert("RGB")

                # Apply adjustments
                if brightness != 1.0:
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(brightness)

                if contrast != 1.0:
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(contrast)

                if saturation != 1.0:
                    enhancer = ImageEnhance.Color(img)
                    img = enhancer.enhance(saturation)

                if sharpen:
                    img = img.filter(ImageFilter.SHARPEN)

                if blur > 0:
                    img = img.filter(ImageFilter.GaussianBlur(radius=blur))

                output_path = TEMP_DIR / f"filter_{datetime.now().strftime('%H%M%S')}.jpg"
                img.save(output_path, "JPEG", quality=95)

            result = {
                "local_path": str(output_path),
                "filters_applied": {
                    "brightness": brightness,
                    "contrast": contrast,
                    "saturation": saturation,
                    "sharpen": sharpen,
                    "blur": blur
                }
            }

            if upload:
                s3_result = upload_to_s3(output_path, "filter")
                result.update(s3_result)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ----------------------------------------------------------------
        # ADD BORDER
        # ----------------------------------------------------------------
        elif name == "add_border":
            if not PIL_AVAILABLE:
                return [TextContent(type="text", text="Error: PIL not available")]

            image_path = download_image(arguments["image_source"])
            border_width = arguments.get("border_width", 20)
            border_color = arguments.get("border_color", "white")
            upload = arguments.get("upload_to_s3", True)

            with Image.open(image_path) as img:
                img = img.convert("RGB")

                # Create new image with border
                new_w = img.width + border_width * 2
                new_h = img.height + border_width * 2
                bordered = Image.new("RGB", (new_w, new_h), border_color)
                bordered.paste(img, (border_width, border_width))

                output_path = TEMP_DIR / f"border_{datetime.now().strftime('%H%M%S')}.jpg"
                bordered.save(output_path, "JPEG", quality=95)

            result = {
                "local_path": str(output_path),
                "border_width": border_width,
                "border_color": border_color,
                "new_dimensions": f"{new_w}x{new_h}"
            }

            if upload:
                s3_result = upload_to_s3(output_path, "border")
                result.update(s3_result)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ----------------------------------------------------------------
        # CREATE SLIDESHOW
        # ----------------------------------------------------------------
        elif name == "create_slideshow":
            image_sources = arguments["image_sources"]
            duration = arguments.get("duration_per_image", 3)
            transition = arguments.get("transition", "fade")
            output_format = arguments.get("output_format", "mp4")
            platform = arguments.get("platform", "instagram_feed_square")
            upload = arguments.get("upload_to_s3", True)

            # Check FFmpeg
            try:
                subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            except:
                return [TextContent(type="text", text="Error: FFmpeg not available")]

            specs = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["square"])
            target_w, target_h = specs["width"], specs["height"]

            # Download and resize all images
            temp_images = []
            for i, src in enumerate(image_sources):
                try:
                    img_path = download_image(src)

                    # Resize to target
                    with Image.open(img_path) as img:
                        img = img.convert("RGB")
                        ratio = max(target_w / img.width, target_h / img.height)
                        new_w = int(img.width * ratio)
                        new_h = int(img.height * ratio)
                        img = img.resize((new_w, new_h), Image.LANCZOS)

                        left = (new_w - target_w) // 2
                        top = (new_h - target_h) // 2
                        img = img.crop((left, top, left + target_w, top + target_h))

                        temp_path = TEMP_DIR / f"slide_{i:03d}.jpg"
                        img.save(temp_path, "JPEG", quality=95)
                        temp_images.append(temp_path)
                except Exception as e:
                    continue

            if not temp_images:
                return [TextContent(type="text", text="Error: No valid images")]

            # Create slideshow with FFmpeg
            output_path = TEMP_DIR / f"slideshow_{datetime.now().strftime('%H%M%S')}.{output_format}"

            # Build FFmpeg command
            inputs = []
            for img in temp_images:
                inputs.extend(["-loop", "1", "-t", str(duration), "-i", str(img)])

            filter_complex = ""
            if len(temp_images) > 1:
                filter_parts = []
                for i in range(len(temp_images)):
                    filter_parts.append(f"[{i}:v]scale={target_w}:{target_h},setsar=1[v{i}]")
                filter_complex = ";".join(filter_parts)
                filter_complex += f";{''.join([f'[v{i}]' for i in range(len(temp_images))])}concat=n={len(temp_images)}:v=1:a=0[out]"
            else:
                filter_complex = f"[0:v]scale={target_w}:{target_h},setsar=1[out]"

            cmd = ["ffmpeg", "-y"] + inputs + [
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                str(output_path)
            ]

            subprocess.run(cmd, capture_output=True, check=True)

            result = {
                "local_path": str(output_path),
                "images_count": len(temp_images),
                "duration_total": len(temp_images) * duration,
                "format": output_format,
                "dimensions": f"{target_w}x{target_h}"
            }

            if upload and output_path.exists():
                # Upload video to S3
                if s3_client:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    s3_key = f"videos/slideshow_{timestamp}.{output_format}"
                    s3_client.upload_file(str(output_path), BUCKET_NAME, s3_key)
                    presigned_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': BUCKET_NAME, 'Key': s3_key},
                        ExpiresIn=86400
                    )
                    result["s3_key"] = s3_key
                    result["presigned_url"] = presigned_url

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ----------------------------------------------------------------
        # VALIDATE FOR PLATFORM (QUALITY CONTROL)
        # ----------------------------------------------------------------
        elif name == "validate_for_platform":
            if not PIL_AVAILABLE:
                return [TextContent(type="text", text="Error: PIL not available")]

            image_path = download_image(arguments["image_source"])
            platform = arguments["platform"]

            validation = validate_image_quality(image_path, platform)

            # Add recommendation if not valid
            if not validation["valid"]:
                validation["recommendation"] = f"Use resize_for_platform with platform='{platform}' to fix dimensions"

            return [TextContent(type="text", text=json.dumps(validation, indent=2))]

        # ----------------------------------------------------------------
        # GET PLATFORM SPECS
        # ----------------------------------------------------------------
        elif name == "get_platform_specs":
            return [TextContent(type="text", text=json.dumps({
                "platforms": PLATFORM_SPECS,
                "quality_rules": QUALITY_RULES
            }, indent=2))]

        # ----------------------------------------------------------------
        # VIEW IMAGE
        # ----------------------------------------------------------------
        elif name == "view_image":
            image_path = download_image(arguments["image_source"])

            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()

            # Get image info
            if PIL_AVAILABLE:
                with Image.open(image_path) as img:
                    info = {
                        "dimensions": f"{img.width}x{img.height}",
                        "format": img.format,
                        "mode": img.mode
                    }
            else:
                info = {"path": str(image_path)}

            return [
                ImageContent(type="image", data=image_data, mimeType="image/jpeg"),
                TextContent(type="text", text=json.dumps(info, indent=2))
            ]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        import traceback
        return [TextContent(type="text", text=f"Error: {str(e)}\n{traceback.format_exc()}")]


# ============================================================================
# MAIN
# ============================================================================

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
