"""
Update Shopping campaigns to only show Kostuum Heren (Men's Suits) products.
This script configures product groups to filter by product type.
"""
import asyncio
import sys
import os
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_ads_shopping_mcp.config import load_google_ads_client, get_customer_id


def get_existing_listing_groups(client, customer_id, ad_group_id):
    """Get existing listing group criteria for an ad group."""
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            ad_group_criterion.resource_name,
            ad_group_criterion.criterion_id,
            ad_group_criterion.listing_group.type,
            ad_group_criterion.listing_group.parent_ad_group_criterion,
            ad_group_criterion.cpc_bid_micros,
            ad_group_criterion.status
        FROM ad_group_criterion
        WHERE ad_group.id = {ad_group_id}
        AND ad_group_criterion.type = 'LISTING_GROUP'
    """

    response = ga_service.search(customer_id=customer_id, query=query)

    criteria = []
    for row in response:
        criteria.append({
            "resource_name": row.ad_group_criterion.resource_name,
            "criterion_id": row.ad_group_criterion.criterion_id,
            "type": row.ad_group_criterion.listing_group.type.name,
            "parent": row.ad_group_criterion.listing_group.parent_ad_group_criterion,
            "cpc_bid_micros": row.ad_group_criterion.cpc_bid_micros
        })

    return criteria


def remove_existing_listing_groups(client, customer_id, ad_group_id, criteria):
    """Remove existing listing group criteria."""
    if not criteria:
        return

    ad_group_criterion_service = client.get_service("AdGroupCriterionService")

    operations = []
    for criterion in criteria:
        operation = client.get_type("AdGroupCriterionOperation")
        operation.remove = criterion["resource_name"]
        operations.append(operation)

    if operations:
        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id,
            operations=operations
        )
        print(f"   Removed {len(operations)} existing listing group(s)")


def create_kostuum_heren_product_groups(client, customer_id, ad_group_id, cpc_bid_eur=0.50):
    """
    Create product groups that only include Kostuum Heren (Men's Suits).

    Structure:
    - Root (SUBDIVISION)
      ├── Kostuum Heren (UNIT) - with bid
      └── Everything Else (UNIT) - excluded (negative, no bid)
    """
    ad_group_criterion_service = client.get_service("AdGroupCriterionService")
    ad_group_resource = f"customers/{customer_id}/adGroups/{ad_group_id}"

    operations = []

    # Temporary IDs for nodes (must be negative)
    root_temp_id = -1
    kostuum_temp_id = -2
    other_temp_id = -3

    # 1. Create Root node (SUBDIVISION by product_type)
    root_operation = client.get_type("AdGroupCriterionOperation")
    root_criterion = root_operation.create
    root_criterion.ad_group = ad_group_resource
    root_criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    root_criterion.listing_group.type_ = client.enums.ListingGroupTypeEnum.SUBDIVISION
    # Root has no case_value - it's the top level
    root_criterion.resource_name = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{root_temp_id}"
    operations.append(root_operation)

    # 2. Create "Default Category" node (UNIT with bid) - This is where suits are
    # Note: Most suit products in the feed have product_type="Default Category"
    # This targets: Herenpak, Kostuum, Blazer, Smoking, etc.
    kostuum_operation = client.get_type("AdGroupCriterionOperation")
    kostuum_criterion = kostuum_operation.create
    kostuum_criterion.ad_group = ad_group_resource
    kostuum_criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    kostuum_criterion.cpc_bid_micros = int(cpc_bid_eur * 1_000_000)
    kostuum_criterion.listing_group.type_ = client.enums.ListingGroupTypeEnum.UNIT
    kostuum_criterion.listing_group.parent_ad_group_criterion = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{root_temp_id}"
    kostuum_criterion.listing_group.case_value.product_type.level = client.enums.ProductTypeLevelEnum.LEVEL1
    kostuum_criterion.listing_group.case_value.product_type.value = "Default Category"  # Suits are here in feed
    kostuum_criterion.resource_name = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{kostuum_temp_id}"
    operations.append(kostuum_operation)

    # 3. Create "Everything Else" node (UNIT - with $0 bid to exclude)
    # This is the required "others" case - set negative=True to exclude
    other_operation = client.get_type("AdGroupCriterionOperation")
    other_criterion = other_operation.create
    other_criterion.ad_group = ad_group_resource
    other_criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    other_criterion.negative = True  # This excludes "Everything Else" from showing
    other_criterion.listing_group.type_ = client.enums.ListingGroupTypeEnum.UNIT
    other_criterion.listing_group.parent_ad_group_criterion = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{root_temp_id}"
    # For "others" case, we need to set product_type with empty value
    other_criterion.listing_group.case_value.product_type.level = client.enums.ProductTypeLevelEnum.LEVEL1
    # Empty string value means "Everything Else" in this dimension
    other_criterion.resource_name = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{other_temp_id}"
    operations.append(other_operation)

    # Execute all operations
    response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id,
        operations=operations
    )

    print(f"   Created {len(response.results)} product group criteria")
    for result in response.results:
        print(f"   - {result.resource_name}")

    return response


async def main():
    print("=" * 60)
    print("Updating Product Groups for Kostuum Heren Only")
    print("=" * 60)

    client = load_google_ads_client()
    customer_id = get_customer_id()

    # Campaign and Ad Group IDs
    campaigns = [
        {"name": "[BE] Pomandi Shopping - Belgium", "campaign_id": "23348931268", "ad_group_id": "191479387404"},
        {"name": "[NL] Pomandi Shopping - Netherlands", "campaign_id": "23348931286", "ad_group_id": "187661918537"}
    ]

    for campaign in campaigns:
        print(f"\n{campaign['name']}")
        print("-" * 40)

        ad_group_id = campaign['ad_group_id']

        # Step 1: Get existing listing groups
        print("1. Checking existing listing groups...")
        existing = get_existing_listing_groups(client, customer_id, ad_group_id)
        print(f"   Found {len(existing)} existing listing group(s)")

        # Step 2: Remove existing listing groups
        print("2. Removing existing listing groups...")
        if existing:
            remove_existing_listing_groups(client, customer_id, ad_group_id, existing)
        else:
            print("   No existing listing groups to remove")

        # Step 3: Create new product groups for Kostuum Heren
        print("3. Creating Kostuum Heren product groups...")
        try:
            create_kostuum_heren_product_groups(client, customer_id, ad_group_id, cpc_bid_eur=0.50)
            print("   SUCCESS!")
        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)
    print("\nProduct groups are now configured to show only 'Kostuum Heren' products.")
    print("Other product types will be excluded from these campaigns.")
    print("\nNote: Make sure your Merchant Center feed has 'product_type' field set to")
    print("'Kostuum Heren' for men's suit products.")


if __name__ == "__main__":
    asyncio.run(main())
