#!/usr/bin/env python3
"""
Backfill Embeddings
==================

Migrate existing data from PostgreSQL to Qdrant with embeddings.

Imports:
- Invoices from retouche database
- Social posts from agent_outputs database
- Ad reports from agent_outputs database

Usage:
    python scripts/backfill_embeddings.py --collection invoices --limit 100
    python scripts/backfill_embeddings.py --collection social_posts
    python scripts/backfill_embeddings.py --all

Options:
    --collection: Specific collection to backfill (invoices, social_posts, ad_reports)
    --limit: Max number of records to process (default: 1000)
    --all: Backfill all collections
    --dry-run: Test without saving to Qdrant
"""

import asyncio
import argparse
import os
import sys
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncpg
from memory import MemoryManager
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger(__name__)


async def fetch_invoices(limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Fetch invoices from retouche database.

    Returns:
        List of invoice dicts with content and metadata
    """
    print(f"Fetching invoices from retouche database (limit: {limit})...")

    # Connect to retouche database
    retouche_db_url = os.getenv("RETOUCHE_DATABASE_URL")
    if not retouche_db_url:
        print("  ✗ RETOUCHE_DATABASE_URL not set")
        return []

    try:
        conn = await asyncpg.connect(retouche_db_url)

        # Query invoices (adjust table/column names based on actual schema)
        query = """
        SELECT
            id,
            vendor_name,
            amount,
            invoice_date,
            description,
            file_path,
            matched
        FROM invoices
        WHERE amount IS NOT NULL
        ORDER BY invoice_date DESC
        LIMIT $1
        """

        rows = await conn.fetch(query, limit)
        await conn.close()

        # Convert to format for memory
        items = []
        for row in rows:
            # Build content for embedding
            content = f"Invoice from {row['vendor_name']} for €{row['amount']:.2f}"
            if row['description']:
                content += f" - {row['description']}"

            items.append({
                "id": row['id'],
                "content": content,
                "metadata": {
                    "invoice_id": row['id'],
                    "vendor_name": row['vendor_name'],
                    "amount": float(row['amount']),
                    "date": row['invoice_date'].isoformat() if row['invoice_date'] else None,
                    "description": row['description'] or "",
                    "file_path": row['file_path'] or "",
                    "matched": row['matched'] or False
                }
            })

        print(f"  ✓ Fetched {len(items)} invoices")
        return items

    except Exception as e:
        print(f"  ✗ Failed to fetch invoices: {e}")
        return []


async def fetch_social_posts(limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Fetch social media posts from agent_outputs database.

    Returns:
        List of post dicts with content and metadata
    """
    print(f"Fetching social posts from agent_outputs database (limit: {limit})...")

    # Connect to agent_outputs database
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    if not all([db_host, db_name, db_user, db_password]):
        print("  ✗ Database credentials not set (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)")
        return []

    try:
        conn = await asyncpg.connect(
            host=db_host,
            port=int(db_port),
            database=db_name,
            user=db_user,
            password=db_password
        )

        # Query social posts (adjust based on actual schema)
        query = """
        SELECT
            id,
            brand,
            platform,
            caption,
            published_at,
            engagement_rate,
            photo_key
        FROM social_media_posts
        WHERE caption IS NOT NULL
        ORDER BY published_at DESC
        LIMIT $1
        """

        rows = await conn.fetch(query, limit)
        await conn.close()

        # Convert to format for memory
        items = []
        for row in rows:
            items.append({
                "id": f"post_{row['id']}",
                "content": row['caption'],
                "metadata": {
                    "post_id": str(row['id']),
                    "brand": row['brand'] or "",
                    "platform": row['platform'] or "",
                    "caption": row['caption'],
                    "published_at": row['published_at'].isoformat() if row['published_at'] else None,
                    "engagement_rate": float(row['engagement_rate']) if row['engagement_rate'] else 0.0,
                    "photo_key": row['photo_key'] or ""
                }
            })

        print(f"  ✓ Fetched {len(items)} social posts")
        return items

    except Exception as e:
        print(f"  ✗ Failed to fetch social posts: {e}")
        logger.exception("fetch_social_posts_error")
        return []


async def fetch_ad_reports(limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Fetch ad reports from agent_outputs database.

    Returns:
        List of report dicts with content and metadata
    """
    print(f"Fetching ad reports from agent_outputs database (limit: {limit})...")

    # Connect to agent_outputs database
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    if not all([db_host, db_name, db_user, db_password]):
        print("  ✗ Database credentials not set")
        return []

    try:
        conn = await asyncpg.connect(
            host=db_host,
            port=int(db_port),
            database=db_name,
            user=db_user,
            password=db_password
        )

        # Query ad reports (adjust based on actual schema)
        query = """
        SELECT
            id,
            campaign_id,
            campaign_name,
            report_date,
            spend,
            conversions,
            roas,
            insights
        FROM ad_reports
        WHERE insights IS NOT NULL
        ORDER BY report_date DESC
        LIMIT $1
        """

        rows = await conn.fetch(query, limit)
        await conn.close()

        # Convert to format for memory
        items = []
        for row in rows:
            # Build content from insights
            content = f"Campaign {row['campaign_name']} - {row['insights']}"

            items.append({
                "id": f"ad_report_{row['id']}",
                "content": content,
                "metadata": {
                    "campaign_id": row['campaign_id'] or "",
                    "campaign_name": row['campaign_name'] or "",
                    "date": row['report_date'].isoformat() if row['report_date'] else None,
                    "spend": float(row['spend']) if row['spend'] else 0.0,
                    "conversions": int(row['conversions']) if row['conversions'] else 0,
                    "roas": float(row['roas']) if row['roas'] else 0.0,
                    "insights": row['insights']
                }
            })

        print(f"  ✓ Fetched {len(items)} ad reports")
        return items

    except Exception as e:
        print(f"  ✗ Failed to fetch ad reports: {e}")
        logger.exception("fetch_ad_reports_error")
        return []


async def backfill_collection(
    collection: str,
    items: List[Dict[str, Any]],
    dry_run: bool = False
) -> int:
    """
    Backfill a collection with items.

    Args:
        collection: Collection name
        items: Items to import
        dry_run: If True, don't actually save

    Returns:
        Number of items processed
    """
    if not items:
        print(f"No items to backfill for {collection}")
        return 0

    print(f"\nBackfilling '{collection}' collection...")
    print(f"  Items to process: {len(items)}")

    if dry_run:
        print("  (DRY RUN - not saving to Qdrant)")
        return len(items)

    # Initialize memory manager
    manager = MemoryManager()
    await manager.initialize()

    try:
        # Estimate cost first
        contents = [item["content"] for item in items]
        cost_estimate = await manager.embedding_generator.estimate_cost(contents)

        print(f"  Estimated cost:")
        print(f"    - Total tokens: {cost_estimate['total_tokens']:,}")
        print(f"    - Estimated USD: ${cost_estimate['estimated_usd']:.4f}")
        print(f"    - Avg tokens/item: {cost_estimate['avg_tokens_per_text']:.1f}")

        # Confirm before proceeding
        response = input("\n  Proceed with backfill? (y/n): ")
        if response.lower() != 'y':
            print("  Cancelled by user")
            await manager.close()
            return 0

        # Batch save
        count = await manager.batch_save(collection, items)

        print(f"  ✓ Successfully backfilled {count} items")

        # Show stats
        stats = await manager.get_collection_stats(collection)
        print(f"  Collection now has {stats.get('points_count', 0)} total items")

        await manager.close()
        return count

    except Exception as e:
        print(f"  ✗ Backfill failed: {e}")
        logger.exception("backfill_error")
        await manager.close()
        return 0


async def main():
    """Main backfill script."""
    parser = argparse.ArgumentParser(description="Backfill embeddings to Qdrant")
    parser.add_argument(
        "--collection",
        choices=["invoices", "social_posts", "ad_reports"],
        help="Specific collection to backfill"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Max records to process (default: 1000)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Backfill all collections"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test without saving to Qdrant"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Backfill Embeddings to Qdrant")
    print("=" * 60)
    print()

    collections_to_process = []

    if args.all:
        collections_to_process = ["invoices", "social_posts", "ad_reports"]
    elif args.collection:
        collections_to_process = [args.collection]
    else:
        print("Error: Specify --collection or --all")
        parser.print_help()
        sys.exit(1)

    total_processed = 0

    for collection_name in collections_to_process:
        print(f"\nProcessing collection: {collection_name}")
        print("-" * 60)

        # Fetch data
        if collection_name == "invoices":
            items = await fetch_invoices(args.limit)
        elif collection_name == "social_posts":
            items = await fetch_social_posts(args.limit)
        elif collection_name == "ad_reports":
            items = await fetch_ad_reports(args.limit)
        else:
            print(f"Unknown collection: {collection_name}")
            continue

        # Backfill
        count = await backfill_collection(collection_name, items, dry_run=args.dry_run)
        total_processed += count

    print()
    print("=" * 60)
    print(f"Backfill complete: {total_processed} items processed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
