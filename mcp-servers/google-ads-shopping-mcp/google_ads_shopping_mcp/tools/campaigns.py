"""Tools for managing Google Ads Shopping campaigns."""
import logging
from typing import Dict, Any
from google.ads.googleads.client import GoogleAdsClient
from google.api_core import protobuf_helpers

from ..coordinator import mcp
from ..config import load_google_ads_client, get_customer_id, get_merchant_center_id
from ..security import (
    ValidationError,
    validate_campaign_name,
    validate_daily_budget,
    validate_country_code,
    validate_bidding_strategy,
    sanitize_output
)

logger = logging.getLogger(__name__)

@mcp.tool()
async def create_shopping_campaign(
    campaign_name: str,
    daily_budget: float,
    country: str = "BE",
    bidding_strategy: str = "MANUAL_CPC"
) -> Dict[str, Any]:
    """
    Create a Standard Shopping campaign in Google Ads.

    This tool creates a new Shopping campaign with the specified settings.
    The campaign will be created with PAUSED status by default for safety.

    Args:
        campaign_name: Name of the campaign (1-255 characters)
        daily_budget: Daily budget in EUR (must be > 0)
        country: Target country code (BE or NL). Default: BE
        bidding_strategy: Bidding strategy type. Options:
            - MANUAL_CPC: Manual cost-per-click bidding
            - MAXIMIZE_CLICKS: Automatically maximize clicks within budget
            - TARGET_ROAS: Target return on ad spend
            - MAXIMIZE_CONVERSION_VALUE: Maximize conversion value
            - TARGET_CPA: Target cost per acquisition
            Default: MANUAL_CPC

    Returns:
        Dictionary containing:
            - campaign_id: ID of the created campaign
            - resource_name: Full resource name
            - status: Campaign status
            - settings: Campaign settings

    Raises:
        ValidationError: If input validation fails
        Exception: If API call fails

    Example:
        create_shopping_campaign(
            campaign_name="Summer Sale - Kostuum Heren",
            daily_budget=50.0,
            country="BE",
            bidding_strategy="MAXIMIZE_CLICKS"
        )
    """
    logger.info(f"Creating shopping campaign: {campaign_name}")

    try:
        # Validate inputs
        validate_campaign_name(campaign_name)
        validate_daily_budget(daily_budget)
        validate_country_code(country)
        validate_bidding_strategy(bidding_strategy)

        # Load Google Ads client
        client = load_google_ads_client()
        customer_id = get_customer_id()
        merchant_center_id = get_merchant_center_id()

        # Get services
        campaign_service = client.get_service("CampaignService")
        campaign_budget_service = client.get_service("CampaignBudgetService")

        # Create campaign budget with unique name using timestamp
        import time
        timestamp = int(time.time())
        budget_operation = client.get_type("CampaignBudgetOperation")
        budget = budget_operation.create
        budget.name = f"Budget-{timestamp}-{campaign_name}"
        budget.amount_micros = int(daily_budget * 1_000_000)  # Convert to micros
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD

        # Add budget
        budget_response = campaign_budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[budget_operation]
        )
        budget_resource_name = budget_response.results[0].resource_name

        logger.info(f"Created budget: {budget_resource_name}")

        # Create campaign
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.create
        campaign.name = campaign_name
        campaign.status = client.enums.CampaignStatusEnum.PAUSED  # Start paused for safety
        campaign.campaign_budget = budget_resource_name

        # Set advertising channel type to SHOPPING
        campaign.advertising_channel_type = (
            client.enums.AdvertisingChannelTypeEnum.SHOPPING
        )

        # Configure Shopping settings
        # Note: sales_country is deprecated in v21, use feed_label instead
        shopping_setting = campaign.shopping_setting
        shopping_setting.merchant_id = int(merchant_center_id)
        shopping_setting.feed_label = country.upper()  # Use country as feed label
        shopping_setting.campaign_priority = 0  # Low priority
        shopping_setting.enable_local = True  # Enable local inventory ads

        # Set bidding strategy
        bidding_strategy_upper = bidding_strategy.upper()
        if bidding_strategy_upper == "MANUAL_CPC":
            campaign.manual_cpc.enhanced_cpc_enabled = True
        elif bidding_strategy_upper == "MAXIMIZE_CLICKS":
            campaign.maximize_clicks.CopyFrom(
                client.get_type("MaximizeClicks")
            )
        elif bidding_strategy_upper == "TARGET_ROAS":
            campaign.target_roas.CopyFrom(
                client.get_type("TargetRoas")
            )
        elif bidding_strategy_upper == "MAXIMIZE_CONVERSION_VALUE":
            campaign.maximize_conversion_value.CopyFrom(
                client.get_type("MaximizeConversionValue")
            )
        elif bidding_strategy_upper == "TARGET_CPA":
            campaign.target_cpa.CopyFrom(
                client.get_type("TargetCpa")
            )

        # Set network settings
        campaign.network_settings.target_google_search = True
        campaign.network_settings.target_search_network = True
        campaign.network_settings.target_content_network = False
        campaign.network_settings.target_partner_search_network = False

        # EU Political Advertising declaration (required for EU countries in v21+)
        # This is required since September 3, 2025 for all campaigns targeting EU
        # Set to DOES_NOT_CONTAIN since we're running e-commerce ads, not political ads
        campaign.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )

        # Add campaign
        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[campaign_operation]
        )

        campaign_resource_name = campaign_response.results[0].resource_name
        campaign_id = campaign_resource_name.split('/')[-1]

        logger.info(f"Created campaign: {campaign_resource_name}")

        result = {
            "success": True,
            "campaign_id": campaign_id,
            "resource_name": campaign_resource_name,
            "budget_resource_name": budget_resource_name,
            "status": "PAUSED",
            "settings": {
                "name": campaign_name,
                "daily_budget": daily_budget,
                "country": country.upper(),
                "bidding_strategy": bidding_strategy_upper,
                "merchant_center_id": merchant_center_id,
                "advertising_channel": "SHOPPING"
            },
            "next_steps": [
                "Use create_ad_group to add an ad group to this campaign",
                "Enable campaign when ready (status will be PAUSED initially)"
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
        logger.error(f"Error creating campaign: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }

@mcp.tool()
async def get_shopping_campaigns() -> Dict[str, Any]:
    """
    Retrieve all Shopping campaigns for the account.

    Returns:
        Dictionary containing:
            - campaigns: List of campaign details
            - total: Total number of campaigns

    Example response:
        {
            "total": 3,
            "campaigns": [
                {
                    "id": "12345",
                    "name": "Summer Sale - Kostuum Heren",
                    "status": "ENABLED",
                    "budget": 50.0,
                    "country": "BE"
                }
            ]
        }
    """
    logger.info("Fetching shopping campaigns")

    try:
        # Load Google Ads client
        client = load_google_ads_client()
        customer_id = get_customer_id()

        # Get Google Ads service
        ga_service = client.get_service("GoogleAdsService")

        # Query to get Shopping campaigns
        # Note: sales_country was deprecated, use feed_label instead
        query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign_budget.amount_micros,
                campaign.shopping_setting.merchant_id,
                campaign.shopping_setting.feed_label,
                campaign.shopping_setting.campaign_priority
            FROM campaign
            WHERE campaign.advertising_channel_type = 'SHOPPING'
            ORDER BY campaign.name
        """

        # Execute search
        response = ga_service.search(customer_id=customer_id, query=query)

        campaigns = []
        for row in response:
            campaign = row.campaign
            budget = row.campaign_budget

            campaigns.append({
                "id": str(campaign.id),
                "name": campaign.name,
                "status": campaign.status.name,
                "advertising_channel_type": campaign.advertising_channel_type.name,
                "daily_budget": budget.amount_micros / 1_000_000,
                "merchant_id": str(campaign.shopping_setting.merchant_id),
                "feed_label": campaign.shopping_setting.feed_label,
                "campaign_priority": campaign.shopping_setting.campaign_priority
            })

        result = {
            "success": True,
            "total": len(campaigns),
            "campaigns": campaigns,
            "customer_id": customer_id
        }

        return result

    except Exception as e:
        logger.error(f"Error fetching campaigns: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }
