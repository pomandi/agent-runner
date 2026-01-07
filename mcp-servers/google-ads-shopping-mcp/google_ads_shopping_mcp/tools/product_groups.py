"""Tools for managing Google Ads Shopping product groups."""
import logging
from typing import Dict, Any, List
from google.ads.googleads.client import GoogleAdsClient

from ..coordinator import mcp
from ..config import load_google_ads_client, get_customer_id
from ..security import (
    ValidationError,
    validate_ad_group_id,
    validate_product_groups,
    sanitize_output
)

logger = logging.getLogger(__name__)

@mcp.tool()
async def set_product_groups(
    ad_group_id: str,
    product_groups: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Configure product groups for a Shopping ad group.

    Product groups determine which products from your Merchant Center feed are included
    in the ad group and how they are organized for bidding.

    Args:
        ad_group_id: ID of the ad group
        product_groups: List of product group configurations. Each group should have:
            - dimension: Product dimension to partition by (e.g., 'product_type', 'brand')
            - value: Optional value to filter by (if None, creates "Everything else")
            - bid: Optional CPC bid in EUR for this product group

    Product dimensions available:
        - product_type: Product category/type
        - brand: Brand name
        - item_id: Specific product ID
        - condition: NEW, USED, REFURBISHED
        - custom_label_0 through custom_label_4: Custom labels from feed

    Returns:
        Dictionary containing:
            - success: Boolean
            - product_groups_created: Number of groups created
            - details: List of created product group details

    Raises:
        ValidationError: If input validation fails
        Exception: If API call fails

    Example:
        # Create a simple "All Products" subdivision
        set_product_groups(
            ad_group_id="67890",
            product_groups=[
                {
                    "dimension": "product_type",
                    "value": None,  # All products
                    "bid": 1.5
                }
            ]
        )

        # Create groups by brand
        set_product_groups(
            ad_group_id="67890",
            product_groups=[
                {
                    "dimension": "brand",
                    "value": "Nike",
                    "bid": 2.0
                },
                {
                    "dimension": "brand",
                    "value": "Adidas",
                    "bid": 1.8
                },
                {
                    "dimension": "brand",
                    "value": None,  # Everything else
                    "bid": 1.0
                }
            ]
        )
    """
    logger.info(f"Setting product groups for ad group {ad_group_id}")

    try:
        # Validate inputs
        validate_ad_group_id(ad_group_id)
        validate_product_groups(product_groups)

        # Load Google Ads client
        client = load_google_ads_client()
        customer_id = get_customer_id()

        # Get services
        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        ga_service = client.get_service("GoogleAdsService")

        # Build ad group resource name
        ad_group_resource_name = f"customers/{customer_id}/adGroups/{ad_group_id}"

        # First, get existing product groups to find the root
        query = f"""
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.listing_group.type,
                ad_group_criterion.listing_group.parent_ad_group_criterion
            FROM ad_group_criterion
            WHERE ad_group_criterion.ad_group = '{ad_group_resource_name}'
                AND ad_group_criterion.type = 'LISTING_GROUP'
        """

        search_response = ga_service.search(customer_id=customer_id, query=query)

        # Check if root exists
        has_root = False
        root_criterion_id = None

        for row in search_response:
            criterion = row.ad_group_criterion
            if criterion.listing_group.type.name == "UNIT" and not criterion.listing_group.parent_ad_group_criterion:
                has_root = True
                root_criterion_id = criterion.criterion_id
                break

        operations = []

        # If no root exists, create one
        if not has_root:
            # Create root "All products" subdivision
            root_operation = client.get_type("AdGroupCriterionOperation")
            root_criterion = root_operation.create
            root_criterion.ad_group = ad_group_resource_name
            root_criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
            root_criterion.listing_group.type_ = client.enums.ListingGroupTypeEnum.SUBDIVISION

            operations.append(root_operation)

            # Use a temporary ID for the root (will be replaced by Google Ads)
            root_criterion_id = -1

        # Create product groups based on configuration
        created_groups = []

        for idx, pg in enumerate(product_groups):
            dimension = pg.get("dimension")
            value = pg.get("value")
            bid = pg.get("bid", 1.0)

            # Create product group operation
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.create

            criterion.ad_group = ad_group_resource_name
            criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED

            # Set as UNIT (biddable) if this is a leaf node
            criterion.listing_group.type_ = client.enums.ListingGroupTypeEnum.UNIT

            # Set parent (root)
            if root_criterion_id:
                parent_resource = f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{root_criterion_id}"
                criterion.listing_group.parent_ad_group_criterion = parent_resource

            # Set dimension
            if dimension == "product_type":
                if value:
                    criterion.listing_group.case_value.product_type.value = value
                # else: Everything else (no case value)
            elif dimension == "brand":
                if value:
                    criterion.listing_group.case_value.product_brand.value = value
            elif dimension == "item_id":
                if value:
                    criterion.listing_group.case_value.product_item_id.value = value
            elif dimension == "condition":
                if value:
                    condition_enum = client.enums.ProductConditionEnum[value.upper()]
                    criterion.listing_group.case_value.product_condition.condition = condition_enum
            elif dimension.startswith("custom_label_"):
                label_num = dimension.split("_")[-1]
                if value:
                    if label_num == "0":
                        criterion.listing_group.case_value.product_custom_attribute.value = value
                        criterion.listing_group.case_value.product_custom_attribute.index = (
                            client.enums.ProductCustomAttributeIndexEnum.INDEX0
                        )
                    # Add other custom labels as needed

            # Set bid
            criterion.cpc_bid_micros = int(bid * 1_000_000)

            operations.append(operation)

            created_groups.append({
                "dimension": dimension,
                "value": value if value else "Everything else",
                "bid": bid
            })

        # Execute operations
        if operations:
            response = ad_group_criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id,
                operations=operations
            )

            logger.info(f"Created {len(response.results)} product groups")

        result = {
            "success": True,
            "ad_group_id": ad_group_id,
            "product_groups_created": len(created_groups),
            "details": created_groups,
            "message": "Product groups configured successfully"
        }

        return result

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "success": False,
            "error": "Validation Error",
            "message": str(e)
        }
    except Exception as e:
        logger.error(f"Error setting product groups: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }

@mcp.tool()
async def get_product_groups(ad_group_id: str) -> Dict[str, Any]:
    """
    Retrieve product groups for a Shopping ad group.

    Args:
        ad_group_id: ID of the ad group

    Returns:
        Dictionary containing product group structure and bids

    Example response:
        {
            "success": True,
            "ad_group_id": "67890",
            "product_groups": [
                {
                    "criterion_id": "123",
                    "type": "UNIT",
                    "dimension": "brand",
                    "value": "Nike",
                    "bid": 2.0,
                    "status": "ENABLED"
                }
            ]
        }
    """
    logger.info(f"Fetching product groups for ad group {ad_group_id}")

    try:
        # Validate input
        validate_ad_group_id(ad_group_id)

        # Load Google Ads client
        client = load_google_ads_client()
        customer_id = get_customer_id()

        # Get Google Ads service
        ga_service = client.get_service("GoogleAdsService")

        # Build ad group resource name
        ad_group_resource_name = f"customers/{customer_id}/adGroups/{ad_group_id}"

        # Query to get product groups
        query = f"""
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.listing_group.type,
                ad_group_criterion.listing_group.case_value.product_type.value,
                ad_group_criterion.listing_group.case_value.product_brand.value,
                ad_group_criterion.listing_group.case_value.product_item_id.value,
                ad_group_criterion.cpc_bid_micros,
                ad_group_criterion.status
            FROM ad_group_criterion
            WHERE ad_group_criterion.ad_group = '{ad_group_resource_name}'
                AND ad_group_criterion.type = 'LISTING_GROUP'
            ORDER BY ad_group_criterion.criterion_id
        """

        # Execute search
        response = ga_service.search(customer_id=customer_id, query=query)

        product_groups = []
        for row in response:
            criterion = row.ad_group_criterion
            listing_group = criterion.listing_group

            # Determine dimension and value
            dimension = None
            value = None

            if listing_group.case_value.product_type.value:
                dimension = "product_type"
                value = listing_group.case_value.product_type.value
            elif listing_group.case_value.product_brand.value:
                dimension = "brand"
                value = listing_group.case_value.product_brand.value
            elif listing_group.case_value.product_item_id.value:
                dimension = "item_id"
                value = listing_group.case_value.product_item_id.value

            product_groups.append({
                "criterion_id": str(criterion.criterion_id),
                "type": listing_group.type.name,
                "dimension": dimension,
                "value": value if value else "All products / Everything else",
                "bid": criterion.cpc_bid_micros / 1_000_000 if criterion.cpc_bid_micros else None,
                "status": criterion.status.name
            })

        result = {
            "success": True,
            "ad_group_id": ad_group_id,
            "total": len(product_groups),
            "product_groups": product_groups
        }

        return result

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "success": False,
            "error": "Validation Error",
            "message": str(e)
        }
    except Exception as e:
        logger.error(f"Error fetching product groups: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }
