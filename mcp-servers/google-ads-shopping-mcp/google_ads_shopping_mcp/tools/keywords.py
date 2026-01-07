"""Tools for managing negative keywords in Google Ads Shopping campaigns."""
import logging
from typing import Dict, Any, List
from google.ads.googleads.client import GoogleAdsClient

from ..coordinator import mcp
from ..config import load_google_ads_client, get_customer_id
from ..security import (
    ValidationError,
    validate_campaign_id,
    validate_keywords,
    sanitize_output
)

logger = logging.getLogger(__name__)

@mcp.tool()
async def add_negative_keywords(
    campaign_id: str,
    keywords: List[str],
    match_type: str = "EXACT"
) -> Dict[str, Any]:
    """
    Add negative keywords to a Shopping campaign.

    Negative keywords prevent your ads from showing for specific search terms.
    This is important for Shopping campaigns to exclude irrelevant searches.

    Args:
        campaign_id: ID of the campaign
        keywords: List of negative keywords to add (max 5000)
        match_type: Keyword match type. Options:
            - EXACT: Exact match only
            - PHRASE: Phrase match
            - BROAD: Broad match (default for negatives)
            Default: EXACT

    Returns:
        Dictionary containing:
            - success: Boolean
            - keywords_added: Number of keywords added
            - details: List of added keywords with their match types

    Raises:
        ValidationError: If input validation fails
        Exception: If API call fails

    Example:
        add_negative_keywords(
            campaign_id="12345",
            keywords=["gratis", "goedkoop", "tweedehands"],
            match_type="BROAD"
        )
    """
    logger.info(f"Adding {len(keywords)} negative keywords to campaign {campaign_id}")

    try:
        # Validate inputs
        validate_campaign_id(campaign_id)
        validate_keywords(keywords)

        # Validate match type
        valid_match_types = ["EXACT", "PHRASE", "BROAD"]
        match_type_upper = match_type.upper()
        if match_type_upper not in valid_match_types:
            raise ValidationError(
                f"Match type must be one of: {', '.join(valid_match_types)}"
            )

        # Load Google Ads client
        client = load_google_ads_client()
        customer_id = get_customer_id()

        # Get service
        campaign_criterion_service = client.get_service("CampaignCriterionService")

        # Build campaign resource name
        campaign_resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

        # Create operations for each keyword
        operations = []
        keyword_details = []

        for keyword in keywords:
            # Clean keyword
            keyword_text = keyword.strip().lower()

            if not keyword_text:
                continue

            # Create campaign criterion operation
            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create

            criterion.campaign = campaign_resource_name
            criterion.negative = True  # This is a negative keyword
            criterion.status = client.enums.CampaignCriterionStatusEnum.ENABLED

            # Set keyword
            criterion.keyword.text = keyword_text

            # Set match type
            if match_type_upper == "EXACT":
                criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
            elif match_type_upper == "PHRASE":
                criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
            elif match_type_upper == "BROAD":
                criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.BROAD

            operations.append(operation)

            keyword_details.append({
                "keyword": keyword_text,
                "match_type": match_type_upper
            })

        # Execute operations
        if operations:
            response = campaign_criterion_service.mutate_campaign_criteria(
                customer_id=customer_id,
                operations=operations
            )

            logger.info(f"Added {len(response.results)} negative keywords")

            result = {
                "success": True,
                "campaign_id": campaign_id,
                "keywords_added": len(response.results),
                "details": keyword_details,
                "message": f"Successfully added {len(response.results)} negative keywords"
            }
        else:
            result = {
                "success": False,
                "error": "No valid keywords",
                "message": "No valid keywords to add after cleaning"
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
        logger.error(f"Error adding negative keywords: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }

@mcp.tool()
async def get_negative_keywords(campaign_id: str) -> Dict[str, Any]:
    """
    Retrieve all negative keywords for a campaign.

    Args:
        campaign_id: ID of the campaign

    Returns:
        Dictionary containing:
            - success: Boolean
            - total: Total number of negative keywords
            - keywords: List of negative keyword details

    Example response:
        {
            "success": True,
            "campaign_id": "12345",
            "total": 15,
            "keywords": [
                {
                    "criterion_id": "789",
                    "keyword": "gratis",
                    "match_type": "BROAD",
                    "status": "ENABLED"
                }
            ]
        }
    """
    logger.info(f"Fetching negative keywords for campaign {campaign_id}")

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

        # Query to get negative keywords
        query = f"""
            SELECT
                campaign_criterion.criterion_id,
                campaign_criterion.keyword.text,
                campaign_criterion.keyword.match_type,
                campaign_criterion.status,
                campaign_criterion.negative
            FROM campaign_criterion
            WHERE campaign_criterion.campaign = '{campaign_resource_name}'
                AND campaign_criterion.type = 'KEYWORD'
                AND campaign_criterion.negative = TRUE
            ORDER BY campaign_criterion.keyword.text
        """

        # Execute search
        response = ga_service.search(customer_id=customer_id, query=query)

        keywords = []
        for row in response:
            criterion = row.campaign_criterion

            keywords.append({
                "criterion_id": str(criterion.criterion_id),
                "keyword": criterion.keyword.text,
                "match_type": criterion.keyword.match_type.name,
                "status": criterion.status.name,
                "negative": criterion.negative
            })

        result = {
            "success": True,
            "campaign_id": campaign_id,
            "total": len(keywords),
            "keywords": keywords
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
        logger.error(f"Error fetching negative keywords: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }

@mcp.tool()
async def remove_negative_keywords(
    campaign_id: str,
    criterion_ids: List[str]
) -> Dict[str, Any]:
    """
    Remove negative keywords from a campaign.

    Args:
        campaign_id: ID of the campaign
        criterion_ids: List of criterion IDs to remove

    Returns:
        Dictionary containing:
            - success: Boolean
            - keywords_removed: Number of keywords removed

    Example:
        remove_negative_keywords(
            campaign_id="12345",
            criterion_ids=["789", "790"]
        )
    """
    logger.info(f"Removing {len(criterion_ids)} negative keywords from campaign {campaign_id}")

    try:
        # Validate inputs
        validate_campaign_id(campaign_id)

        if not isinstance(criterion_ids, list) or len(criterion_ids) == 0:
            raise ValidationError("criterion_ids must be a non-empty list")

        # Load Google Ads client
        client = load_google_ads_client()
        customer_id = get_customer_id()

        # Get service
        campaign_criterion_service = client.get_service("CampaignCriterionService")

        # Create remove operations
        operations = []
        for criterion_id in criterion_ids:
            operation = client.get_type("CampaignCriterionOperation")
            operation.remove = f"customers/{customer_id}/campaignCriteria/{campaign_id}~{criterion_id}"
            operations.append(operation)

        # Execute operations
        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=operations
        )

        logger.info(f"Removed {len(response.results)} negative keywords")

        result = {
            "success": True,
            "campaign_id": campaign_id,
            "keywords_removed": len(response.results),
            "message": f"Successfully removed {len(response.results)} negative keywords"
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
        logger.error(f"Error removing negative keywords: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": type(e).__name__,
            "message": str(e)
        }
