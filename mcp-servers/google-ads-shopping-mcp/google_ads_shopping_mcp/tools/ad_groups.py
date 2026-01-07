"""Tools for managing Google Ads Shopping ad groups."""
import logging
from typing import Dict, Any
from google.ads.googleads.client import GoogleAdsClient

from ..coordinator import mcp
from ..config import load_google_ads_client, get_customer_id
from ..security import (
    ValidationError,
    validate_ad_group_name,
    validate_campaign_id,
    sanitize_output
)

logger = logging.getLogger(__name__)

@mcp.tool()
async def create_ad_group(
    campaign_id: str,
    ad_group_name: str
) -> Dict[str, Any]:
    """
    Create a Shopping ad group within a campaign.

    For Shopping campaigns, the ad group contains product groups that determine
    which products from your Merchant Center feed are shown.

    Args:
        campaign_id: ID of the parent campaign
        ad_group_name: Name of the ad group (1-255 characters)

    Returns:
        Dictionary containing:
            - ad_group_id: ID of the created ad group
            - resource_name: Full resource name
            - status: Ad group status

    Raises:
        ValidationError: If input validation fails
        Exception: If API call fails

    Example:
        create_ad_group(
            campaign_id="12345",
            ad_group_name="All Products"
        )
    """
    logger.info(f"Creating ad group: {ad_group_name} in campaign {campaign_id}")

    try:
        # Validate inputs
        validate_campaign_id(campaign_id)
        validate_ad_group_name(ad_group_name)

        # Load Google Ads client
        client = load_google_ads_client()
        customer_id = get_customer_id()

        # Get service
        ad_group_service = client.get_service("AdGroupService")

        # Create ad group operation
        ad_group_operation = client.get_type("AdGroupOperation")
        ad_group = ad_group_operation.create

        # Build campaign resource name
        campaign_resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

        # Set ad group properties
        ad_group.name = ad_group_name
        ad_group.campaign = campaign_resource_name
        ad_group.type_ = client.enums.AdGroupTypeEnum.SHOPPING_PRODUCT_ADS
        ad_group.status = client.enums.AdGroupStatusEnum.ENABLED

        # For Shopping, CPC bid is optional (can use campaign-level bidding)
        # Setting a default CPC bid of 1 EUR
        ad_group.cpc_bid_micros = 1_000_000  # 1 EUR in micros

        # Add ad group
        response = ad_group_service.mutate_ad_groups(
            customer_id=customer_id,
            operations=[ad_group_operation]
        )

        ad_group_resource_name = response.results[0].resource_name
        ad_group_id = ad_group_resource_name.split('/')[-1]

        logger.info(f"Created ad group: {ad_group_resource_name}")

        result = {
            "success": True,
            "ad_group_id": ad_group_id,
            "resource_name": ad_group_resource_name,
            "campaign_id": campaign_id,
            "status": "ENABLED",
            "settings": {
                "name": ad_group_name,
                "type": "SHOPPING_PRODUCT_ADS",
                "default_cpc_bid": 1.0
            },
            "next_steps": [
                "Use set_product_groups to configure which products to show",
                "Product groups determine the bidding structure"
            ]
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
        logger.error(f"Error creating ad group: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }

@mcp.tool()
async def get_ad_groups(campaign_id: str) -> Dict[str, Any]:
    """
    Retrieve all ad groups for a specific campaign.

    Args:
        campaign_id: ID of the campaign

    Returns:
        Dictionary containing:
            - ad_groups: List of ad group details
            - total: Total number of ad groups

    Example response:
        {
            "total": 2,
            "ad_groups": [
                {
                    "id": "67890",
                    "name": "All Products",
                    "status": "ENABLED",
                    "type": "SHOPPING_PRODUCT_ADS"
                }
            ]
        }
    """
    logger.info(f"Fetching ad groups for campaign {campaign_id}")

    try:
        # Validate input
        validate_campaign_id(campaign_id)

        # Load Google Ads client
        client = load_google_ads_client()
        customer_id = get_customer_id()

        # Get Google Ads service
        ga_service = client.get_service("GoogleAdsService")

        # Build campaign resource name
        campaign_resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

        # Query to get ad groups
        query = f"""
            SELECT
                ad_group.id,
                ad_group.name,
                ad_group.status,
                ad_group.type,
                ad_group.cpc_bid_micros
            FROM ad_group
            WHERE ad_group.campaign = '{campaign_resource_name}'
            ORDER BY ad_group.name
        """

        # Execute search
        response = ga_service.search(customer_id=customer_id, query=query)

        ad_groups = []
        for row in response:
            ag = row.ad_group

            ad_groups.append({
                "id": str(ag.id),
                "name": ag.name,
                "status": ag.status.name,
                "type": ag.type_.name,
                "cpc_bid": ag.cpc_bid_micros / 1_000_000 if ag.cpc_bid_micros else None
            })

        result = {
            "success": True,
            "campaign_id": campaign_id,
            "total": len(ad_groups),
            "ad_groups": ad_groups
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
        logger.error(f"Error fetching ad groups: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }
