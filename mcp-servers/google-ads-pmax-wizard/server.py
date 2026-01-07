#!/usr/bin/env python3
"""
Google Ads Performance Max Wizard MCP Server
=============================================
Step-by-step MCP Server for creating Performance Max campaigns.

Each step is a separate tool, giving full control and visibility:
- Step 1: Create Budget
- Step 2: Create Campaign
- Step 3: Set Targeting (Location + Language)
- Step 4: Create Asset Group
- Step 5a: Add Headlines
- Step 5b: Add Descriptions
- Step 5c: Add Images (optional)
- Step 5d: Add Audience Signals (optional)
- Step 6: Activate Campaign

Plus helper tools:
- Get Campaign Status
- Validate Assets
- List Available Locations
- Delete Campaign

Version: 1.0.0
API Version: Google Ads API v22
Last Updated: 2025-12-20
"""

import asyncio
import json
import os
import sys
import logging
from typing import Any, Optional, List
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# ============================================================================
# LOGGING
# ============================================================================

LOG_DIR = Path("/workspace/server-data/logs/mcp-servers")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "pmax-wizard-mcp.log"

logger = logging.getLogger("pmax-wizard")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
logger.addHandler(file_handler)

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Google Ads API
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# Geo targets
from geo_targets import (
    COUNTRIES, LANGUAGES, BE_PROVINCES, BE_CITIES, BE_REGIONS,
    NL_PROVINCES, NL_CITIES, search_locations, get_pomandi_default_targeting
)

# ============================================================================
# SERVER SETUP
# ============================================================================

SERVER_NAME = "google-ads-pmax-wizard"
SERVER_VERSION = "1.0.0"

server = Server(SERVER_NAME)
_client: Optional[GoogleAdsClient] = None


def get_client() -> GoogleAdsClient:
    global _client
    if _client is None:
        config_path = os.getenv("GOOGLE_ADS_YAML_PATH", "/workspace/server-data/google-ads.yaml")
        _client = GoogleAdsClient.load_from_storage(config_path)
    return _client


def get_customer_id() -> str:
    return os.getenv("GOOGLE_ADS_CUSTOMER_ID", "5945647044")


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

TOOLS = [
    # ========== STEP 1: BUDGET ==========
    Tool(
        name="pmax_step1_create_budget",
        description="""STEP 1: Create a campaign budget for Performance Max.

This is the first step in creating a PMax campaign.
Returns a budget_id that you'll use in Step 2.

Example:
  daily_budget_eur: 50.0
  budget_name: "Pomandi PMax Budget" (optional)
""",
        inputSchema={
            "type": "object",
            "properties": {
                "daily_budget_eur": {
                    "type": "number",
                    "description": "Daily budget in EUR (e.g., 50.0)"
                },
                "budget_name": {
                    "type": "string",
                    "description": "Optional: Custom budget name"
                }
            },
            "required": ["daily_budget_eur"]
        }
    ),

    # ========== STEP 2: CAMPAIGN ==========
    Tool(
        name="pmax_step2_create_campaign",
        description="""STEP 2: Create the Performance Max campaign.

Requires budget_id from Step 1.
Returns campaign_id for subsequent steps.

Bidding strategies:
- MAXIMIZE_CONVERSIONS: When not tracking conversion values
- MAXIMIZE_CONVERSION_VALUE: When tracking conversion values (can set target_roas)
""",
        inputSchema={
            "type": "object",
            "properties": {
                "budget_id": {
                    "type": "string",
                    "description": "Budget ID from Step 1"
                },
                "campaign_name": {
                    "type": "string",
                    "description": "Name for the campaign"
                },
                "business_name": {
                    "type": "string",
                    "description": "Business name for brand guidelines (e.g., 'Pomandi')"
                },
                "bidding_strategy": {
                    "type": "string",
                    "enum": ["MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE"],
                    "description": "Bidding strategy (default: MAXIMIZE_CONVERSIONS)"
                },
                "target_cpa_eur": {
                    "type": "number",
                    "description": "Optional: Target CPA in EUR (for MAXIMIZE_CONVERSIONS)"
                },
                "target_roas": {
                    "type": "number",
                    "description": "Optional: Target ROAS (e.g., 3.5 = 350%)"
                }
            },
            "required": ["budget_id", "campaign_name", "business_name"]
        }
    ),

    # ========== STEP 3: TARGETING ==========
    Tool(
        name="pmax_step3_set_targeting",
        description="""STEP 3: Set location and language targeting.

Requires campaign_id from Step 2.

You can target:
- Countries: BE, NL, DE, FR, LU
- Provinces: Use list_available_locations to see all
- Cities: Use list_available_locations to see all
- Languages: nl (Dutch), fr (French), de (German), en (English)

Example for Pomandi:
  countries: ["BE", "NL"]
  provinces: ["antwerp", "limburg_be"]
  cities: ["brasschaat", "genk"]
  languages: ["nl"]
""",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID from Step 2"
                },
                "countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Country codes: BE, NL, DE, FR, LU"
                },
                "provinces": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Province keys (use list_available_locations)"
                },
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "City keys (use list_available_locations)"
                },
                "languages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Language codes: nl, fr, de, en"
                }
            },
            "required": ["campaign_id"]
        }
    ),

    # ========== STEP 4: ASSET GROUP ==========
    Tool(
        name="pmax_step4_create_asset_group",
        description="""STEP 4: Create an asset group.

Requires campaign_id from Step 2.
Returns asset_group_id for adding assets.

Each asset group should have a specific theme/product focus.
You can create multiple asset groups per campaign.
""",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID from Step 2"
                },
                "asset_group_name": {
                    "type": "string",
                    "description": "Name for the asset group"
                },
                "final_url": {
                    "type": "string",
                    "description": "Landing page URL"
                },
                "path1": {
                    "type": "string",
                    "description": "Optional: Display URL path 1 (max 15 chars)"
                },
                "path2": {
                    "type": "string",
                    "description": "Optional: Display URL path 2 (max 15 chars)"
                }
            },
            "required": ["campaign_id", "asset_group_name", "final_url"]
        }
    ),

    # ========== STEP 5a: HEADLINES ==========
    Tool(
        name="pmax_step5a_add_headlines",
        description="""STEP 5a: Add headlines to an asset group.

Requires asset_group_id from Step 4.

Rules:
- Minimum: 3 headlines
- Maximum: 15 headlines
- Each headline: max 30 characters
- Recommended: 5+ headlines for better optimization
""",
        inputSchema={
            "type": "object",
            "properties": {
                "asset_group_id": {
                    "type": "string",
                    "description": "Asset Group ID from Step 4"
                },
                "headlines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of headlines (3-15, each max 30 chars)"
                }
            },
            "required": ["asset_group_id", "headlines"]
        }
    ),

    # ========== STEP 5b: DESCRIPTIONS ==========
    Tool(
        name="pmax_step5b_add_descriptions",
        description="""STEP 5b: Add descriptions to an asset group.

Requires asset_group_id from Step 4.

Rules:
- Minimum: 2 descriptions
- Maximum: 5 descriptions
- Each description: max 90 characters
- Recommended: 4+ descriptions
""",
        inputSchema={
            "type": "object",
            "properties": {
                "asset_group_id": {
                    "type": "string",
                    "description": "Asset Group ID from Step 4"
                },
                "descriptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of descriptions (2-5, each max 90 chars)"
                }
            },
            "required": ["asset_group_id", "descriptions"]
        }
    ),

    # ========== STEP 5c: IMAGES ==========
    Tool(
        name="pmax_step5c_add_images",
        description="""STEP 5c: Add images to an asset group (OPTIONAL but recommended).

Requires asset_group_id from Step 4.

Image types:
- marketing_images: 1200x628 (landscape 1.91:1)
- square_images: 1200x1200 (1:1)
- logo: 1200x1200 (1:1)
- landscape_logo: 1200x300 (4:1)
""",
        inputSchema={
            "type": "object",
            "properties": {
                "asset_group_id": {
                    "type": "string",
                    "description": "Asset Group ID from Step 4"
                },
                "marketing_image_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URLs for marketing images (1200x628)"
                },
                "square_image_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URLs for square images (1200x1200)"
                },
                "logo_url": {
                    "type": "string",
                    "description": "URL for logo (1200x1200)"
                },
                "landscape_logo_url": {
                    "type": "string",
                    "description": "URL for landscape logo (1200x300)"
                }
            },
            "required": ["asset_group_id"]
        }
    ),

    # ========== STEP 5d: AUDIENCE SIGNALS ==========
    Tool(
        name="pmax_step5d_add_audience_signals",
        description="""STEP 5d: Add audience signals / search themes (OPTIONAL but recommended).

Requires asset_group_id from Step 4.

Search themes help Google understand what your customers search for.
Maximum 25 search themes per asset group.
""",
        inputSchema={
            "type": "object",
            "properties": {
                "asset_group_id": {
                    "type": "string",
                    "description": "Asset Group ID from Step 4"
                },
                "search_themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Search theme keywords (max 25)"
                }
            },
            "required": ["asset_group_id", "search_themes"]
        }
    ),

    # ========== STEP 6: ACTIVATE ==========
    Tool(
        name="pmax_step6_activate_campaign",
        description="""STEP 6: Activate the campaign (FINAL STEP).

This will change the campaign status from PAUSED to ENABLED.
The campaign will start serving ads immediately.

Make sure all required assets are added before activating!
""",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID to activate"
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Set to true to confirm activation"
                }
            },
            "required": ["campaign_id", "confirm"]
        }
    ),

    # ========== HELPER: CAMPAIGN STATUS ==========
    Tool(
        name="pmax_get_campaign_status",
        description="""Get detailed status of a PMax campaign.

Shows:
- Campaign info and status
- Budget details
- Targeting settings
- Asset groups and their assets
- Whether it's ready to activate
""",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID to check"
                }
            },
            "required": ["campaign_id"]
        }
    ),

    # ========== HELPER: LIST LOCATIONS ==========
    Tool(
        name="pmax_list_available_locations",
        description="""List available locations for targeting.

Filter by:
- country: 'BE' or 'NL'
- type: 'provinces', 'cities', or 'all'
- search: search by name

Returns location keys and IDs that can be used in step3.
""",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "enum": ["BE", "NL"],
                    "description": "Filter by country"
                },
                "location_type": {
                    "type": "string",
                    "enum": ["provinces", "cities", "all"],
                    "description": "Type of locations to list"
                },
                "search": {
                    "type": "string",
                    "description": "Search by name"
                }
            }
        }
    ),

    # ========== HELPER: VALIDATE ASSETS ==========
    Tool(
        name="pmax_validate_assets",
        description="""Validate assets before adding them.

Checks:
- Headline count and length
- Description count and length
- Returns issues and warnings
""",
        inputSchema={
            "type": "object",
            "properties": {
                "headlines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Headlines to validate"
                },
                "descriptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Descriptions to validate"
                }
            }
        }
    ),

    # ========== HELPER: PAUSE CAMPAIGN ==========
    Tool(
        name="pmax_pause_campaign",
        description="""Pause an active campaign.""",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID to pause"
                }
            },
            "required": ["campaign_id"]
        }
    ),

    # ========== HELPER: DELETE CAMPAIGN ==========
    Tool(
        name="pmax_delete_campaign",
        description="""Delete (remove) a campaign. This action cannot be undone.""",
        inputSchema={
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign ID to delete"
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Set to true to confirm deletion"
                }
            },
            "required": ["campaign_id", "confirm"]
        }
    ),

    # ========== HELPER: LIST CAMPAIGNS ==========
    Tool(
        name="pmax_list_campaigns",
        description="""List all Performance Max campaigns.""",
        inputSchema={
            "type": "object",
            "properties": {
                "include_removed": {
                    "type": "boolean",
                    "description": "Include removed campaigns (default: false)"
                }
            }
        }
    ),
]


# ============================================================================
# TOOL HANDLERS
# ============================================================================

async def handle_step1_create_budget(daily_budget_eur: float, budget_name: str = None) -> dict:
    """Step 1: Create campaign budget"""
    logger.info(f"Step 1: Creating budget €{daily_budget_eur}/day")

    client = get_client()
    customer_id = get_customer_id()

    budget_service = client.get_service("CampaignBudgetService")
    budget_operation = client.get_type("CampaignBudgetOperation")
    budget = budget_operation.create

    budget.name = budget_name or f"PMax Budget - {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    budget.amount_micros = int(daily_budget_eur * 1_000_000)
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.explicitly_shared = False  # PMax cannot use shared budgets

    try:
        response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id,
            operations=[budget_operation]
        )

        budget_resource = response.results[0].resource_name
        budget_id = budget_resource.split("/")[-1]

        return {
            "success": True,
            "step": 1,
            "budget_id": budget_id,
            "budget_resource_name": budget_resource,
            "daily_budget_eur": daily_budget_eur,
            "budget_name": budget.name,
            "next_step": "Use pmax_step2_create_campaign with this budget_id"
        }

    except GoogleAdsException as ex:
        error = ex.failure.errors[0] if ex.failure.errors else None
        return {
            "success": False,
            "step": 1,
            "error": error.message if error else str(ex),
            "error_code": str(error.error_code) if error else None
        }


async def handle_step2_create_campaign(
    budget_id: str,
    campaign_name: str,
    business_name: str,
    bidding_strategy: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_eur: float = None,
    target_roas: float = None
) -> dict:
    """Step 2: Create campaign with brand guidelines"""
    logger.info(f"Step 2: Creating campaign '{campaign_name}'")

    client = get_client()
    customer_id = get_customer_id()

    operations = []

    # Services
    campaign_service = client.get_service("CampaignService")
    budget_service = client.get_service("CampaignBudgetService")
    asset_service = client.get_service("AssetService")

    # Temporary IDs
    campaign_temp_id = -1
    business_name_temp_id = -2

    # 1. Create Business Name Asset
    bn_op = client.get_type("MutateOperation")
    bn_asset = bn_op.asset_operation.create
    bn_asset.text_asset.text = business_name
    bn_asset.resource_name = asset_service.asset_path(customer_id, business_name_temp_id)
    operations.append(bn_op)

    # 2. Create Campaign
    campaign_op = client.get_type("MutateOperation")
    campaign = campaign_op.campaign_operation.create

    campaign.name = campaign_name
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    campaign.brand_guidelines_enabled = True

    # Budget
    campaign.campaign_budget = budget_service.campaign_budget_path(customer_id, budget_id)

    # Bidding
    if bidding_strategy == "MAXIMIZE_CONVERSION_VALUE":
        campaign.bidding_strategy_type = client.enums.BiddingStrategyTypeEnum.MAXIMIZE_CONVERSION_VALUE
        if target_roas:
            campaign.maximize_conversion_value.target_roas = target_roas
    else:
        campaign.bidding_strategy_type = client.enums.BiddingStrategyTypeEnum.MAXIMIZE_CONVERSIONS
        if target_cpa_eur:
            campaign.maximize_conversions.target_cpa_micros = int(target_cpa_eur * 1_000_000)

    campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_temp_id)
    operations.append(campaign_op)

    # 3. Link Business Name to Campaign
    bn_link_op = client.get_type("MutateOperation")
    bn_link = bn_link_op.campaign_asset_operation.create
    bn_link.campaign = campaign_service.campaign_path(customer_id, campaign_temp_id)
    bn_link.asset = asset_service.asset_path(customer_id, business_name_temp_id)
    bn_link.field_type = client.enums.AssetFieldTypeEnum.BUSINESS_NAME
    operations.append(bn_link_op)

    try:
        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=operations,
            partial_failure=False
        )

        campaign_id = None
        for op_response in response.mutate_operation_responses:
            if op_response.campaign_result.resource_name:
                campaign_id = op_response.campaign_result.resource_name.split("/")[-1]

        return {
            "success": True,
            "step": 2,
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "business_name": business_name,
            "bidding_strategy": bidding_strategy,
            "status": "PAUSED",
            "next_step": "Use pmax_step3_set_targeting with this campaign_id"
        }

    except GoogleAdsException as ex:
        error = ex.failure.errors[0] if ex.failure.errors else None
        return {
            "success": False,
            "step": 2,
            "error": error.message if error else str(ex)
        }


async def handle_step3_set_targeting(
    campaign_id: str,
    countries: List[str] = None,
    provinces: List[str] = None,
    cities: List[str] = None,
    languages: List[str] = None
) -> dict:
    """Step 3: Set location and language targeting"""
    logger.info(f"Step 3: Setting targeting for campaign {campaign_id}")

    client = get_client()
    customer_id = get_customer_id()

    operations = []
    campaign_service = client.get_service("CampaignService")
    geo_service = client.get_service("GeoTargetConstantService")
    lang_service = client.get_service("LanguageConstantService")

    campaign_resource = campaign_service.campaign_path(customer_id, campaign_id)

    locations_added = []
    languages_added = []

    # Add countries
    if countries:
        for code in countries:
            if code.upper() in COUNTRIES:
                geo_id = COUNTRIES[code.upper()]["id"]
                criterion_op = client.get_type("CampaignCriterionOperation")
                criterion = criterion_op.create
                criterion.campaign = campaign_resource
                criterion.location.geo_target_constant = geo_service.geo_target_constant_path(geo_id)
                operations.append(criterion_op)
                locations_added.append({"type": "country", "code": code, "id": geo_id})

    # Add provinces
    if provinces:
        all_provinces = {**BE_PROVINCES, **NL_PROVINCES}
        for key in provinces:
            if key in all_provinces:
                geo_id = all_provinces[key]["id"]
                criterion_op = client.get_type("CampaignCriterionOperation")
                criterion = criterion_op.create
                criterion.campaign = campaign_resource
                criterion.location.geo_target_constant = geo_service.geo_target_constant_path(geo_id)
                operations.append(criterion_op)
                locations_added.append({"type": "province", "key": key, "id": geo_id})

    # Add cities
    if cities:
        all_cities = {**BE_CITIES, **NL_CITIES}
        for key in cities:
            if key in all_cities:
                geo_id = all_cities[key]["id"]
                criterion_op = client.get_type("CampaignCriterionOperation")
                criterion = criterion_op.create
                criterion.campaign = campaign_resource
                criterion.location.geo_target_constant = geo_service.geo_target_constant_path(geo_id)
                operations.append(criterion_op)
                locations_added.append({"type": "city", "key": key, "id": geo_id})

    # Add languages
    if languages:
        for code in languages:
            if code.lower() in LANGUAGES:
                lang_id = LANGUAGES[code.lower()]["id"]
                criterion_op = client.get_type("CampaignCriterionOperation")
                criterion = criterion_op.create
                criterion.campaign = campaign_resource
                criterion.language.language_constant = lang_service.language_constant_path(lang_id)
                operations.append(criterion_op)
                languages_added.append({"code": code, "id": lang_id})

    if not operations:
        return {
            "success": False,
            "step": 3,
            "error": "No valid locations or languages specified"
        }

    try:
        criterion_service = client.get_service("CampaignCriterionService")
        response = criterion_service.mutate_campaign_criteria(
            customer_id=customer_id,
            operations=operations
        )

        return {
            "success": True,
            "step": 3,
            "campaign_id": campaign_id,
            "locations_added": locations_added,
            "languages_added": languages_added,
            "criteria_count": len(response.results),
            "next_step": "Use pmax_step4_create_asset_group with this campaign_id"
        }

    except GoogleAdsException as ex:
        error = ex.failure.errors[0] if ex.failure.errors else None
        return {
            "success": False,
            "step": 3,
            "error": error.message if error else str(ex)
        }


async def handle_step4_create_asset_group(
    campaign_id: str,
    asset_group_name: str,
    final_url: str,
    path1: str = None,
    path2: str = None
) -> dict:
    """Step 4: Create asset group"""
    logger.info(f"Step 4: Creating asset group '{asset_group_name}'")

    client = get_client()
    customer_id = get_customer_id()

    campaign_service = client.get_service("CampaignService")
    asset_group_service = client.get_service("AssetGroupService")

    operation = client.get_type("AssetGroupOperation")
    asset_group = operation.create

    asset_group.name = asset_group_name
    asset_group.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    asset_group.final_urls.append(final_url)
    asset_group.status = client.enums.AssetGroupStatusEnum.ENABLED

    if path1:
        asset_group.path1 = path1[:15]
    if path2:
        asset_group.path2 = path2[:15]

    try:
        response = asset_group_service.mutate_asset_groups(
            customer_id=customer_id,
            operations=[operation]
        )

        asset_group_id = response.results[0].resource_name.split("/")[-1]

        return {
            "success": True,
            "step": 4,
            "asset_group_id": asset_group_id,
            "asset_group_name": asset_group_name,
            "campaign_id": campaign_id,
            "final_url": final_url,
            "next_step": "Use pmax_step5a_add_headlines with this asset_group_id"
        }

    except GoogleAdsException as ex:
        error = ex.failure.errors[0] if ex.failure.errors else None
        return {
            "success": False,
            "step": 4,
            "error": error.message if error else str(ex)
        }


async def handle_step5a_add_headlines(asset_group_id: str, headlines: List[str]) -> dict:
    """Step 5a: Add headlines"""
    logger.info(f"Step 5a: Adding {len(headlines)} headlines")

    # Validate
    if len(headlines) < 3:
        return {"success": False, "step": "5a", "error": f"Minimum 3 headlines required (provided: {len(headlines)})"}
    if len(headlines) > 15:
        return {"success": False, "step": "5a", "error": f"Maximum 15 headlines allowed (provided: {len(headlines)})"}

    issues = []
    for i, h in enumerate(headlines):
        if len(h) > 30:
            issues.append(f"Headline {i+1} too long: {len(h)} chars (max 30)")

    if issues:
        return {"success": False, "step": "5a", "error": "Validation failed", "issues": issues}

    client = get_client()
    customer_id = get_customer_id()

    operations = []
    asset_service = client.get_service("AssetService")
    asset_group_service = client.get_service("AssetGroupService")

    temp_id_counter = -100

    for headline in headlines:
        temp_id = temp_id_counter
        temp_id_counter -= 1

        # Create asset
        asset_op = client.get_type("MutateOperation")
        asset = asset_op.asset_operation.create
        asset.text_asset.text = headline
        asset.resource_name = asset_service.asset_path(customer_id, temp_id)
        operations.append(asset_op)

        # Link to asset group
        link_op = client.get_type("MutateOperation")
        link = link_op.asset_group_asset_operation.create
        link.asset_group = asset_group_service.asset_group_path(customer_id, asset_group_id)
        link.asset = asset_service.asset_path(customer_id, temp_id)
        link.field_type = client.enums.AssetFieldTypeEnum.HEADLINE
        operations.append(link_op)

    try:
        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=operations,
            partial_failure=False
        )

        return {
            "success": True,
            "step": "5a",
            "asset_group_id": asset_group_id,
            "headlines_added": len(headlines),
            "headlines": headlines,
            "next_step": "Use pmax_step5b_add_descriptions with this asset_group_id"
        }

    except GoogleAdsException as ex:
        error = ex.failure.errors[0] if ex.failure.errors else None
        return {
            "success": False,
            "step": "5a",
            "error": error.message if error else str(ex)
        }


async def handle_step5b_add_descriptions(asset_group_id: str, descriptions: List[str]) -> dict:
    """Step 5b: Add descriptions"""
    logger.info(f"Step 5b: Adding {len(descriptions)} descriptions")

    # Validate
    if len(descriptions) < 2:
        return {"success": False, "step": "5b", "error": f"Minimum 2 descriptions required (provided: {len(descriptions)})"}
    if len(descriptions) > 5:
        return {"success": False, "step": "5b", "error": f"Maximum 5 descriptions allowed (provided: {len(descriptions)})"}

    issues = []
    for i, d in enumerate(descriptions):
        if len(d) > 90:
            issues.append(f"Description {i+1} too long: {len(d)} chars (max 90)")

    if issues:
        return {"success": False, "step": "5b", "error": "Validation failed", "issues": issues}

    client = get_client()
    customer_id = get_customer_id()

    operations = []
    asset_service = client.get_service("AssetService")
    asset_group_service = client.get_service("AssetGroupService")

    temp_id_counter = -200

    for desc in descriptions:
        temp_id = temp_id_counter
        temp_id_counter -= 1

        # Create asset
        asset_op = client.get_type("MutateOperation")
        asset = asset_op.asset_operation.create
        asset.text_asset.text = desc
        asset.resource_name = asset_service.asset_path(customer_id, temp_id)
        operations.append(asset_op)

        # Link to asset group
        link_op = client.get_type("MutateOperation")
        link = link_op.asset_group_asset_operation.create
        link.asset_group = asset_group_service.asset_group_path(customer_id, asset_group_id)
        link.asset = asset_service.asset_path(customer_id, temp_id)
        link.field_type = client.enums.AssetFieldTypeEnum.DESCRIPTION
        operations.append(link_op)

    try:
        ga_service = client.get_service("GoogleAdsService")
        response = ga_service.mutate(
            customer_id=customer_id,
            mutate_operations=operations,
            partial_failure=False
        )

        return {
            "success": True,
            "step": "5b",
            "asset_group_id": asset_group_id,
            "descriptions_added": len(descriptions),
            "descriptions": descriptions,
            "next_step": "Continue with pmax_step5c_add_images (optional) or pmax_step6_activate_campaign"
        }

    except GoogleAdsException as ex:
        error = ex.failure.errors[0] if ex.failure.errors else None
        return {
            "success": False,
            "step": "5b",
            "error": error.message if error else str(ex)
        }


async def handle_step5c_add_images(
    asset_group_id: str,
    marketing_image_urls: List[str] = None,
    square_image_urls: List[str] = None,
    logo_url: str = None,
    landscape_logo_url: str = None
) -> dict:
    """Step 5c: Add images"""
    # For now, return a placeholder - image handling requires downloading and encoding
    return {
        "success": False,
        "step": "5c",
        "message": "Image upload not yet implemented. Skip this step and proceed to Step 6.",
        "next_step": "Use pmax_step5d_add_audience_signals (optional) or pmax_step6_activate_campaign"
    }


async def handle_step5d_add_audience_signals(asset_group_id: str, search_themes: List[str]) -> dict:
    """Step 5d: Add audience signals"""
    logger.info(f"Step 5d: Adding {len(search_themes)} search themes")

    if len(search_themes) > 25:
        return {"success": False, "step": "5d", "error": f"Maximum 25 search themes allowed (provided: {len(search_themes)})"}

    client = get_client()
    customer_id = get_customer_id()

    operations = []
    asset_group_service = client.get_service("AssetGroupService")
    asset_group_resource = asset_group_service.asset_group_path(customer_id, asset_group_id)

    for theme in search_themes:
        signal_op = client.get_type("AssetGroupSignalOperation")
        signal = signal_op.create
        signal.asset_group = asset_group_resource
        signal.search_theme.text = theme
        operations.append(signal_op)

    try:
        signal_service = client.get_service("AssetGroupSignalService")
        response = signal_service.mutate_asset_group_signals(
            customer_id=customer_id,
            operations=operations
        )

        return {
            "success": True,
            "step": "5d",
            "asset_group_id": asset_group_id,
            "search_themes_added": len(search_themes),
            "search_themes": search_themes,
            "next_step": "Use pmax_step6_activate_campaign to launch the campaign"
        }

    except GoogleAdsException as ex:
        error = ex.failure.errors[0] if ex.failure.errors else None
        return {
            "success": False,
            "step": "5d",
            "error": error.message if error else str(ex)
        }


async def handle_step6_activate_campaign(campaign_id: str, confirm: bool = False) -> dict:
    """Step 6: Activate campaign"""
    logger.info(f"Step 6: Activating campaign {campaign_id}")

    if not confirm:
        return {
            "success": False,
            "step": 6,
            "error": "Confirmation required. Set confirm=true to activate."
        }

    client = get_client()
    customer_id = get_customer_id()

    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("CampaignOperation")
    campaign = operation.update

    campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
    campaign.status = client.enums.CampaignStatusEnum.ENABLED

    field_mask = client.get_type("FieldMask")
    field_mask.paths.append("status")
    operation.update_mask.CopyFrom(field_mask)

    try:
        response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[operation]
        )

        return {
            "success": True,
            "step": 6,
            "campaign_id": campaign_id,
            "previous_status": "PAUSED",
            "new_status": "ENABLED",
            "message": "Campaign is now LIVE! Ads will start serving."
        }

    except GoogleAdsException as ex:
        error = ex.failure.errors[0] if ex.failure.errors else None
        return {
            "success": False,
            "step": 6,
            "error": error.message if error else str(ex)
        }


async def handle_get_campaign_status(campaign_id: str) -> dict:
    """Get detailed campaign status"""
    client = get_client()
    customer_id = get_customer_id()
    ga_service = client.get_service("GoogleAdsService")

    # Get campaign info
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.bidding_strategy_type,
            campaign_budget.amount_micros,
            campaign.advertising_channel_type
        FROM campaign
        WHERE campaign.id = {campaign_id}
    """

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        campaign_info = None
        for row in response:
            campaign_info = {
                "id": row.campaign.id,
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "bidding_strategy": row.campaign.bidding_strategy_type.name,
                "daily_budget_eur": row.campaign_budget.amount_micros / 1_000_000,
                "channel_type": row.campaign.advertising_channel_type.name
            }

        if not campaign_info:
            return {"success": False, "error": f"Campaign {campaign_id} not found"}

        # Get asset groups
        ag_query = f"""
            SELECT
                asset_group.id,
                asset_group.name,
                asset_group.status,
                asset_group.final_urls
            FROM asset_group
            WHERE asset_group.campaign = 'customers/{customer_id}/campaigns/{campaign_id}'
        """

        asset_groups = []
        response = ga_service.search(customer_id=customer_id, query=ag_query)
        for row in response:
            asset_groups.append({
                "id": row.asset_group.id,
                "name": row.asset_group.name,
                "status": row.asset_group.status.name,
                "final_urls": list(row.asset_group.final_urls)
            })

        return {
            "success": True,
            "campaign": campaign_info,
            "asset_groups": asset_groups,
            "asset_group_count": len(asset_groups)
        }

    except GoogleAdsException as ex:
        return {"success": False, "error": str(ex)}


async def handle_list_available_locations(
    country: str = None,
    location_type: str = "all",
    search: str = None
) -> dict:
    """List available locations for targeting"""

    results = []

    if search:
        results = search_locations(search)
    else:
        if country == "BE" or country is None:
            if location_type in ["provinces", "all"]:
                for key, data in BE_PROVINCES.items():
                    results.append({"type": "be_province", "key": key, **data})
                for key, data in BE_REGIONS.items():
                    results.append({"type": "be_region", "key": key, **data})
            if location_type in ["cities", "all"]:
                for key, data in BE_CITIES.items():
                    results.append({"type": "be_city", "key": key, **data})

        if country == "NL" or country is None:
            if location_type in ["provinces", "all"]:
                for key, data in NL_PROVINCES.items():
                    results.append({"type": "nl_province", "key": key, **data})
            if location_type in ["cities", "all"]:
                for key, data in NL_CITIES.items():
                    results.append({"type": "nl_city", "key": key, **data})

    return {
        "success": True,
        "count": len(results),
        "filter": {"country": country, "type": location_type, "search": search},
        "locations": results,
        "countries_available": list(COUNTRIES.keys()),
        "languages_available": list(LANGUAGES.keys())
    }


async def handle_validate_assets(headlines: List[str] = None, descriptions: List[str] = None) -> dict:
    """Validate assets"""
    issues = []
    warnings = []

    if headlines:
        if len(headlines) < 3:
            issues.append(f"Minimum 3 headlines required (provided: {len(headlines)})")
        elif len(headlines) < 5:
            warnings.append(f"Recommended: 5+ headlines (provided: {len(headlines)})")
        if len(headlines) > 15:
            issues.append(f"Maximum 15 headlines allowed (provided: {len(headlines)})")

        for i, h in enumerate(headlines):
            if len(h) > 30:
                issues.append(f"Headline {i+1} too long: {len(h)} chars (max 30)")
            elif len(h) > 25:
                warnings.append(f"Headline {i+1} near limit: {len(h)}/30 chars")

    if descriptions:
        if len(descriptions) < 2:
            issues.append(f"Minimum 2 descriptions required (provided: {len(descriptions)})")
        elif len(descriptions) < 4:
            warnings.append(f"Recommended: 4+ descriptions (provided: {len(descriptions)})")
        if len(descriptions) > 5:
            issues.append(f"Maximum 5 descriptions allowed (provided: {len(descriptions)})")

        for i, d in enumerate(descriptions):
            if len(d) > 90:
                issues.append(f"Description {i+1} too long: {len(d)} chars (max 90)")
            elif len(d) > 80:
                warnings.append(f"Description {i+1} near limit: {len(d)}/90 chars")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "summary": {
            "headlines": len(headlines) if headlines else 0,
            "descriptions": len(descriptions) if descriptions else 0
        }
    }


async def handle_pause_campaign(campaign_id: str) -> dict:
    """Pause a campaign"""
    client = get_client()
    customer_id = get_customer_id()

    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("CampaignOperation")
    campaign = operation.update

    campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
    campaign.status = client.enums.CampaignStatusEnum.PAUSED

    field_mask = client.get_type("FieldMask")
    field_mask.paths.append("status")
    operation.update_mask.CopyFrom(field_mask)

    try:
        response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[operation]
        )

        return {
            "success": True,
            "campaign_id": campaign_id,
            "new_status": "PAUSED"
        }

    except GoogleAdsException as ex:
        return {"success": False, "error": str(ex)}


async def handle_delete_campaign(campaign_id: str, confirm: bool = False) -> dict:
    """Delete a campaign"""
    if not confirm:
        return {"success": False, "error": "Confirmation required. Set confirm=true to delete."}

    client = get_client()
    customer_id = get_customer_id()

    campaign_service = client.get_service("CampaignService")
    operation = client.get_type("CampaignOperation")
    operation.remove = campaign_service.campaign_path(customer_id, campaign_id)

    try:
        response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[operation]
        )

        return {
            "success": True,
            "campaign_id": campaign_id,
            "status": "REMOVED"
        }

    except GoogleAdsException as ex:
        return {"success": False, "error": str(ex)}


async def handle_list_campaigns(include_removed: bool = False) -> dict:
    """List all PMax campaigns"""
    client = get_client()
    customer_id = get_customer_id()
    ga_service = client.get_service("GoogleAdsService")

    status_filter = "" if include_removed else "AND campaign.status != 'REMOVED'"

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.bidding_strategy_type,
            campaign_budget.amount_micros
        FROM campaign
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
        {status_filter}
        ORDER BY campaign.name
    """

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        campaigns = []
        for row in response:
            campaigns.append({
                "id": str(row.campaign.id),
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "bidding_strategy": row.campaign.bidding_strategy_type.name,
                "daily_budget_eur": row.campaign_budget.amount_micros / 1_000_000
            })

        return {
            "success": True,
            "total": len(campaigns),
            "campaigns": campaigns
        }

    except GoogleAdsException as ex:
        return {"success": False, "error": str(ex)}


# ============================================================================
# TOOL HANDLER MAPPING
# ============================================================================

TOOL_HANDLERS = {
    "pmax_step1_create_budget": handle_step1_create_budget,
    "pmax_step2_create_campaign": handle_step2_create_campaign,
    "pmax_step3_set_targeting": handle_step3_set_targeting,
    "pmax_step4_create_asset_group": handle_step4_create_asset_group,
    "pmax_step5a_add_headlines": handle_step5a_add_headlines,
    "pmax_step5b_add_descriptions": handle_step5b_add_descriptions,
    "pmax_step5c_add_images": handle_step5c_add_images,
    "pmax_step5d_add_audience_signals": handle_step5d_add_audience_signals,
    "pmax_step6_activate_campaign": handle_step6_activate_campaign,
    "pmax_get_campaign_status": handle_get_campaign_status,
    "pmax_list_available_locations": handle_list_available_locations,
    "pmax_validate_assets": handle_validate_assets,
    "pmax_pause_campaign": handle_pause_campaign,
    "pmax_delete_campaign": handle_delete_campaign,
    "pmax_list_campaigns": handle_list_campaigns,
}


# ============================================================================
# MCP SERVER HANDLERS
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info(f"Tool: {name} | Args: {json.dumps(arguments, default=str)}")

    if name not in TOOL_HANDLERS:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        handler = TOOL_HANDLERS[name]
        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str, ensure_ascii=False))]
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


# ============================================================================
# MAIN
# ============================================================================

async def main():
    logger.info("Starting PMax Wizard MCP Server...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
