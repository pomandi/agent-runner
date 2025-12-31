#!/usr/bin/env python3
"""
Nightly Invoice Pre-fetch Cron Job

Runs invoice pre-fetch and match generation.
Designed to be called by system cron or Coolify scheduled task.

Usage:
  # Run directly
  python3 cron_prefetch.py

  # Via cron (every night at 3 AM)
  0 3 * * * cd /app && python3 cron_prefetch.py >> /app/logs/cron.log 2>&1

  # Via Coolify scheduled task
  Set schedule: 0 3 * * *
  Command: python3 /app/cron_prefetch.py
"""

import os
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [CRON] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    """Main cron job function."""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("Starting nightly invoice pre-fetch cron job")
    logger.info("=" * 60)

    # Import prefetch module
    try:
        from invoice_prefetch import run_prefetch
    except ImportError as e:
        logger.error(f"Failed to import invoice_prefetch: {e}")
        sys.exit(1)

    # Run pre-fetch
    try:
        logger.info("Phase 1: Running invoice pre-fetch...")
        result = run_prefetch(
            days_back=7,  # Check last 7 days for new emails
            triggered_by="cron",
            email_accounts=["godaddy", "outlook"]
        )

        logger.info(f"Pre-fetch completed:")
        logger.info(f"  - Emails scanned: {result.emails_scanned}")
        logger.info(f"  - Attachments found: {result.attachments_found}")
        logger.info(f"  - Invoices created: {result.invoices_created}")
        logger.info(f"  - Duplicates skipped: {result.duplicates_skipped}")
        logger.info(f"  - Errors: {result.errors_count}")

        if result.error_details:
            for err in result.error_details[:5]:
                logger.warning(f"  Error: {err}")

    except Exception as e:
        logger.error(f"Pre-fetch failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # Run match generation
    try:
        logger.info("")
        logger.info("Phase 2: Running match generation...")

        # Call the expense-tracker API for match generation
        import requests

        expense_tracker_url = os.environ.get(
            "EXPENSE_TRACKER_URL",
            "https://fin.pomandi.com"
        )

        response = requests.post(
            f"{expense_tracker_url}/api/invoices/match/generate",
            timeout=60
        )

        if response.ok:
            data = response.json()
            logger.info(f"Match generation completed:")
            logger.info(f"  - New suggestions: {data.get('newSuggestions', 0)}")
            logger.info(f"  - Existing suggestions: {data.get('existingSuggestions', 0)}")
            logger.info(f"  - Unmatched invoices: {data.get('unmatchedInvoices', 0)}")
            logger.info(f"  - Unmatched transactions: {data.get('unmatchedTransactions', 0)}")
        else:
            logger.error(f"Match generation API call failed: {response.status_code}")
            logger.error(f"Response: {response.text[:500]}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Match generation API error: {e}")
    except Exception as e:
        logger.error(f"Match generation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # Summary
    duration = datetime.now() - start_time
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"Cron job completed in {duration.total_seconds():.1f} seconds")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
