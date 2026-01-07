"""
Create Shopping campaigns for Belgium and Netherlands.
Based on GOOGLE-SHOPPING-CAMPAIGN-GUIDE-2025.md recommendations.
"""
import asyncio
import sys
import os
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_ads_shopping_mcp.tools.campaigns import create_shopping_campaign, get_shopping_campaigns
from google_ads_shopping_mcp.tools.ad_groups import create_ad_group
from google_ads_shopping_mcp.tools.keywords import add_negative_keywords


async def main():
    print("=" * 60)
    print("Creating Google Shopping Campaigns for Pomandi")
    print("=" * 60)

    # First, check existing Shopping campaigns
    print("\n1. Checking existing Shopping campaigns...")
    existing = await get_shopping_campaigns()

    if existing.get("success"):
        print(f"   Found {existing.get('total', 0)} existing Shopping campaigns:")
        for camp in existing.get("campaigns", []):
            print(f"   - {camp['name']} (ID: {camp['id']}, Status: {camp['status']}, FeedLabel: {camp.get('feed_label', 'N/A')})")
    else:
        print(f"   Error: {existing.get('message', 'Unknown error')}")

    # Create Belgium Shopping Campaign
    print("\n2. Creating Belgium Shopping Campaign...")
    be_campaign = await create_shopping_campaign(
        campaign_name="[BE] Pomandi Shopping - Belgium",
        daily_budget=20.0,  # EUR 20/day as per guide
        country="BE",
        bidding_strategy="MANUAL_CPC"  # Start with Manual CPC for data collection
    )

    if be_campaign.get("success"):
        be_campaign_id = be_campaign.get("campaign_id")
        print(f"   SUCCESS: Belgium campaign created!")
        print(f"   - Campaign ID: {be_campaign_id}")
        print(f"   - Resource: {be_campaign.get('resource_name')}")
        print(f"   - Status: {be_campaign.get('status')} (will be PAUSED initially)")
        print(f"   - Settings: {be_campaign.get('settings')}")

        # Create Ad Group for Belgium
        print("\n3. Creating Ad Group for Belgium campaign...")
        be_ad_group = await create_ad_group(
            campaign_id=be_campaign_id,
            ad_group_name="All Products - Belgium"
        )

        if be_ad_group.get("success"):
            print(f"   SUCCESS: Ad Group created!")
            print(f"   - Ad Group ID: {be_ad_group.get('ad_group_id')}")
        else:
            print(f"   ERROR: {be_ad_group.get('message')}")

    else:
        print(f"   ERROR: {be_campaign.get('message')}")
        be_campaign_id = None

    # Create Netherlands Shopping Campaign
    print("\n4. Creating Netherlands Shopping Campaign...")
    nl_campaign = await create_shopping_campaign(
        campaign_name="[NL] Pomandi Shopping - Netherlands",
        daily_budget=20.0,  # EUR 20/day as per guide
        country="NL",
        bidding_strategy="MANUAL_CPC"  # Start with Manual CPC for data collection
    )

    if nl_campaign.get("success"):
        nl_campaign_id = nl_campaign.get("campaign_id")
        print(f"   SUCCESS: Netherlands campaign created!")
        print(f"   - Campaign ID: {nl_campaign_id}")
        print(f"   - Resource: {nl_campaign.get('resource_name')}")
        print(f"   - Status: {nl_campaign.get('status')} (will be PAUSED initially)")
        print(f"   - Settings: {nl_campaign.get('settings')}")

        # Create Ad Group for Netherlands
        print("\n5. Creating Ad Group for Netherlands campaign...")
        nl_ad_group = await create_ad_group(
            campaign_id=nl_campaign_id,
            ad_group_name="All Products - Netherlands"
        )

        if nl_ad_group.get("success"):
            print(f"   SUCCESS: Ad Group created!")
            print(f"   - Ad Group ID: {nl_ad_group.get('ad_group_id')}")
        else:
            print(f"   ERROR: {nl_ad_group.get('message')}")

    else:
        print(f"   ERROR: {nl_campaign.get('message')}")
        nl_campaign_id = None

    # Add negative keywords (based on guide recommendations)
    negative_keywords = [
        "goedkoop",
        "gratis",
        "korting",
        "uitverkoop",
        "2dehands",
        "tweedehands",
        "huren",
        "verhuur",
        "vacature",
        "baan",
        "werk",
        "salaris",
        "dames",
        "vrouwen",
        "kinderen",
        "vintage",
        "carnaval",
        "halloween"
    ]

    # Add negative keywords to Belgium campaign
    if be_campaign_id:
        print("\n6. Adding negative keywords to Belgium campaign...")
        be_negatives = await add_negative_keywords(
            campaign_id=be_campaign_id,
            keywords=negative_keywords,
            match_type="BROAD"
        )

        if be_negatives.get("success"):
            print(f"   SUCCESS: Added {be_negatives.get('added_count', 0)} negative keywords")
        else:
            print(f"   ERROR: {be_negatives.get('message')}")

    # Add negative keywords to Netherlands campaign
    if nl_campaign_id:
        print("\n7. Adding negative keywords to Netherlands campaign...")
        nl_negatives = await add_negative_keywords(
            campaign_id=nl_campaign_id,
            keywords=negative_keywords,
            match_type="BROAD"
        )

        if nl_negatives.get("success"):
            print(f"   SUCCESS: Added {nl_negatives.get('added_count', 0)} negative keywords")
        else:
            print(f"   ERROR: {nl_negatives.get('message')}")

    # Final verification
    print("\n" + "=" * 60)
    print("Final Verification - All Shopping Campaigns")
    print("=" * 60)

    final_check = await get_shopping_campaigns()
    if final_check.get("success"):
        print(f"\nTotal Shopping campaigns: {final_check.get('total', 0)}")
        for camp in final_check.get("campaigns", []):
            status_icon = "✅" if camp['status'] == 'ENABLED' else "⏸️"
            print(f"  {status_icon} {camp['name']}")
            print(f"     - ID: {camp['id']}")
            print(f"     - Country: {camp.get('sales_country', 'N/A')}")
            print(f"     - Budget: EUR {camp.get('daily_budget', 0)}/day")
            print(f"     - Status: {camp['status']}")

    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("1. Go to Google Ads UI and enable campaigns when ready")
    print("2. Verify Merchant Center feed is linked correctly")
    print("3. Monitor search terms after 24-48 hours")
    print("4. Add more negative keywords as needed")
    print("5. After 15+ conversions, consider switching to Maximize Clicks")
    print("6. After 30+ conversions, consider Target ROAS strategy")


if __name__ == "__main__":
    asyncio.run(main())
