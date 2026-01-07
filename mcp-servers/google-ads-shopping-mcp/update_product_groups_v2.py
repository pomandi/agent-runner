"""
Update Shopping campaigns to only show Kostuum Heren (Men's Suits) products.
Uses "Default Category" as that's where suits are in the current feed.
"""
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_ads_shopping_mcp.config import load_google_ads_client, get_customer_id


def get_existing_listing_groups(client, customer_id, ad_group_id):
    """Get existing listing group criteria for an ad group."""
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            ad_group_criterion.resource_name,
            ad_group_criterion.criterion_id,
            ad_group_criterion.listing_group.type
        FROM ad_group_criterion
        WHERE ad_group.id = {ad_group_id}
        AND ad_group_criterion.type = 'LISTING_GROUP'
    """

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        criteria = []
        for row in response:
            criteria.append({
                "resource_name": row.ad_group_criterion.resource_name,
                "criterion_id": row.ad_group_criterion.criterion_id,
                "type": row.ad_group_criterion.listing_group.type.name
            })
        return criteria
    except Exception as e:
        print(f"   Warning: Could not fetch listing groups: {e}")
        return []


def remove_all_listing_groups(client, customer_id, ad_group_id, criteria):
    """Remove all existing listing group criteria."""
    if not criteria:
        print("   No listing groups to remove")
        return True

    ad_group_criterion_service = client.get_service("AdGroupCriterionService")

    # Remove in order: UNIT first, then SUBDIVISION (parent)
    units = [c for c in criteria if c["type"] == "UNIT"]
    subdivisions = [c for c in criteria if c["type"] == "SUBDIVISION"]

    # Remove UNITs first
    for criterion in units:
        try:
            operation = client.get_type("AdGroupCriterionOperation")
            operation.remove = criterion["resource_name"]
            response = ad_group_criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id,
                operations=[operation]
            )
            print(f"   Removed UNIT: {criterion['criterion_id']}")
        except Exception as e:
            print(f"   Warning: Could not remove UNIT {criterion['criterion_id']}: {e}")

    # Then remove SUBDIVISIONs
    for criterion in subdivisions:
        try:
            operation = client.get_type("AdGroupCriterionOperation")
            operation.remove = criterion["resource_name"]
            response = ad_group_criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id,
                operations=[operation]
            )
            print(f"   Removed SUBDIVISION: {criterion['criterion_id']}")
        except Exception as e:
            print(f"   Warning: Could not remove SUBDIVISION {criterion['criterion_id']}: {e}")

    return True


def create_default_category_product_groups(client, customer_id, ad_group_id, cpc_bid_eur=0.50):
    """
    Create product groups that include "Default Category" (where suits are) and exclude others.
    """
    ad_group_criterion_service = client.get_service("AdGroupCriterionService")
    ad_group_resource = f"customers/{customer_id}/adGroups/{ad_group_id}"

    operations = []

    # Temporary IDs
    root_temp_id = -1
    suit_temp_id = -2
    other_temp_id = -3

    # 1. Root node (SUBDIVISION by product_type)
    root_op = client.get_type("AdGroupCriterionOperation")
    root = root_op.create
    root.ad_group = ad_group_resource
    root.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    root.listing_group.type_ = client.enums.ListingGroupTypeEnum.SUBDIVISION
    root.resource_name = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{root_temp_id}"
    operations.append(root_op)

    # 2. "Default Category" node (where suits are) - UNIT with bid
    suit_op = client.get_type("AdGroupCriterionOperation")
    suit = suit_op.create
    suit.ad_group = ad_group_resource
    suit.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    suit.cpc_bid_micros = int(cpc_bid_eur * 1_000_000)
    suit.listing_group.type_ = client.enums.ListingGroupTypeEnum.UNIT
    suit.listing_group.parent_ad_group_criterion = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{root_temp_id}"
    suit.listing_group.case_value.product_type.level = client.enums.ProductTypeLevelEnum.LEVEL1
    suit.listing_group.case_value.product_type.value = "Default Category"
    suit.resource_name = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{suit_temp_id}"
    operations.append(suit_op)

    # 3. "Everything Else" node - excluded (negative)
    other_op = client.get_type("AdGroupCriterionOperation")
    other = other_op.create
    other.ad_group = ad_group_resource
    other.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    other.negative = True  # Exclude everything else
    other.listing_group.type_ = client.enums.ListingGroupTypeEnum.UNIT
    other.listing_group.parent_ad_group_criterion = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{root_temp_id}"
    other.listing_group.case_value.product_type.level = client.enums.ProductTypeLevelEnum.LEVEL1
    # Empty value = "Everything Else"
    other.resource_name = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{other_temp_id}"
    operations.append(other_op)

    # Execute
    response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id,
        operations=operations
    )

    print(f"   Created {len(response.results)} product group criteria")
    return True


def main():
    print("=" * 60)
    print("Updating Product Groups for Suits Only")
    print("(Using 'Default Category' - where suits are in the feed)")
    print("=" * 60)

    client = load_google_ads_client()
    customer_id = get_customer_id()

    campaigns = [
        {"name": "[BE] Pomandi Shopping - Belgium", "ad_group_id": "191479387404"},
        {"name": "[NL] Pomandi Shopping - Netherlands", "ad_group_id": "187661918537"}
    ]

    for campaign in campaigns:
        print(f"\n{campaign['name']}")
        print("-" * 40)

        ad_group_id = campaign['ad_group_id']

        # Step 1: Get existing listing groups
        print("1. Checking existing listing groups...")
        existing = get_existing_listing_groups(client, customer_id, ad_group_id)
        print(f"   Found {len(existing)} listing group(s)")

        # Step 2: Remove existing listing groups
        if existing:
            print("2. Removing existing listing groups...")
            remove_all_listing_groups(client, customer_id, ad_group_id, existing)
        else:
            print("2. No existing listing groups to remove")

        # Step 3: Create new product groups
        print("3. Creating product groups for 'Default Category' (suits)...")
        try:
            create_default_category_product_groups(client, customer_id, ad_group_id, cpc_bid_eur=0.50)
            print("   SUCCESS!")
        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)
    print("\nCampaigns are now configured to show only 'Default Category' products.")
    print("This includes: Herenpak, Kostuum, Blazer, Smoking, etc.")
    print("\nExcluded: ServiceSet, Belts, and other categories.")


if __name__ == "__main__":
    main()
