#!/usr/bin/env python3
"""Test script to verify MCP server functionality."""
import sys
import json
import asyncio
from google_ads_shopping_mcp.config import load_google_ads_client, get_customer_id, get_merchant_center_id

async def test_connection():
    """Test Google Ads API connection."""
    print("=" * 60)
    print("Testing Google Ads Shopping MCP Server")
    print("=" * 60)
    print()

    try:
        # Test 1: Load config
        print("Test 1: Loading Google Ads configuration...")
        client = load_google_ads_client()
        print("[OK] Configuration loaded successfully")
        print()

        # Test 2: Get credentials
        print("Test 2: Getting credentials...")
        customer_id = get_customer_id()
        merchant_id = get_merchant_center_id()
        print(f"[OK] Customer ID: {customer_id}")
        print(f"[OK] Merchant Center ID: {merchant_id}")
        print()

        # Test 3: Test API connection by fetching campaigns
        print("Test 3: Testing API connection...")
        ga_service = client.get_service("GoogleAdsService")

        query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type
            FROM campaign
            WHERE campaign.status != 'REMOVED'
            LIMIT 5
        """

        response = ga_service.search(customer_id=customer_id, query=query)
        campaigns = []

        for row in response:
            campaigns.append({
                "id": str(row.campaign.id),
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "type": row.campaign.advertising_channel_type.name
            })

        print(f"[OK] API connection successful")
        print(f"[OK] Found {len(campaigns)} campaigns")
        print()

        if campaigns:
            print("Sample campaigns:")
            for camp in campaigns[:3]:
                print(f"  - {camp['name']} (ID: {camp['id']}, Status: {camp['status']}, Type: {camp['type']})")
        print()

        # Test 4: Validate tool imports
        print("Test 4: Validating tool imports...")
        from google_ads_shopping_mcp.tools import campaigns
        from google_ads_shopping_mcp.tools import ad_groups
        from google_ads_shopping_mcp.tools import product_groups
        from google_ads_shopping_mcp.tools import keywords
        print("[OK] All tool modules imported successfully")
        print()

        # Test 5: Validate security module
        print("Test 5: Validating security module...")
        from google_ads_shopping_mcp.security import (
            validate_campaign_name,
            validate_daily_budget,
            validate_country_code,
            validate_bidding_strategy
        )

        # Test validation functions
        validate_campaign_name("Test Campaign")
        validate_daily_budget(50.0)
        validate_country_code("BE")
        validate_bidding_strategy("MANUAL_CPC")
        print("[OK] Security validation working")
        print()

        # Test 6: Check MCP coordinator
        print("Test 6: Checking MCP coordinator...")
        from google_ads_shopping_mcp.coordinator import mcp
        print(f"[OK] MCP server name: {mcp.name}")
        print()

        print("=" * 60)
        print("SUCCESS: ALL TESTS PASSED")
        print("=" * 60)
        print()
        print("The MCP server is ready to use!")
        print()
        print("To add to Claude Code, run:")
        print('  claude mcp add --transport stdio google-ads-shopping -- python -m google_ads_shopping_mcp.server')
        print()

        return True

    except FileNotFoundError as e:
        print(f"[ERROR] Configuration file not found: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Run async test
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
