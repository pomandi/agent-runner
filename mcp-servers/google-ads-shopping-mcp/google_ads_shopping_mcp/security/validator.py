"""Input validation for Google Ads Shopping MCP Server."""
from typing import Any, Dict, List
import re

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

def validate_campaign_name(name: str) -> bool:
    """
    Validate campaign name.

    Args:
        name: Campaign name to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not name or not isinstance(name, str):
        raise ValidationError("Campaign name must be a non-empty string")

    if len(name) < 1 or len(name) > 255:
        raise ValidationError("Campaign name must be between 1 and 255 characters")

    # Google Ads allows most characters including brackets, but prevent potential injection
    if any(char in name for char in ['<', '>', '{', '}']):
        raise ValidationError("Campaign name contains invalid characters")

    return True

def validate_daily_budget(budget: float) -> bool:
    """
    Validate daily budget amount.

    Args:
        budget: Daily budget in currency units

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(budget, (int, float)):
        raise ValidationError("Daily budget must be a number")

    if budget <= 0:
        raise ValidationError("Daily budget must be greater than 0")

    if budget > 1000000:
        raise ValidationError("Daily budget exceeds maximum allowed (1,000,000)")

    return True

def validate_country_code(country: str) -> bool:
    """
    Validate country code.

    Args:
        country: Two-letter country code (BE or NL)

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not country or not isinstance(country, str):
        raise ValidationError("Country code must be a non-empty string")

    valid_countries = ["BE", "NL"]
    country_upper = country.upper()

    if country_upper not in valid_countries:
        raise ValidationError(
            f"Country code must be one of: {', '.join(valid_countries)}"
        )

    return True

def validate_bidding_strategy(strategy: str) -> bool:
    """
    Validate bidding strategy type.

    Args:
        strategy: Bidding strategy name

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not strategy or not isinstance(strategy, str):
        raise ValidationError("Bidding strategy must be a non-empty string")

    valid_strategies = [
        "MANUAL_CPC",
        "MAXIMIZE_CLICKS",
        "TARGET_ROAS",
        "MAXIMIZE_CONVERSION_VALUE",
        "TARGET_CPA"
    ]

    strategy_upper = strategy.upper()

    if strategy_upper not in valid_strategies:
        raise ValidationError(
            f"Bidding strategy must be one of: {', '.join(valid_strategies)}"
        )

    return True

def validate_ad_group_name(name: str) -> bool:
    """
    Validate ad group name.

    Args:
        name: Ad group name to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not name or not isinstance(name, str):
        raise ValidationError("Ad group name must be a non-empty string")

    if len(name) < 1 or len(name) > 255:
        raise ValidationError("Ad group name must be between 1 and 255 characters")

    if any(char in name for char in ['<', '>', '{', '}']):
        raise ValidationError("Ad group name contains invalid characters")

    return True

def validate_campaign_id(campaign_id: str) -> bool:
    """
    Validate campaign ID format.

    Args:
        campaign_id: Campaign ID to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not campaign_id or not isinstance(campaign_id, str):
        raise ValidationError("Campaign ID must be a non-empty string")

    # Campaign ID should be numeric
    if not re.match(r'^\d+$', campaign_id):
        raise ValidationError("Campaign ID must be numeric")

    return True

def validate_ad_group_id(ad_group_id: str) -> bool:
    """
    Validate ad group ID format.

    Args:
        ad_group_id: Ad group ID to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not ad_group_id or not isinstance(ad_group_id, str):
        raise ValidationError("Ad group ID must be a non-empty string")

    # Ad group ID should be numeric
    if not re.match(r'^\d+$', ad_group_id):
        raise ValidationError("Ad group ID must be numeric")

    return True

def validate_keywords(keywords: List[str]) -> bool:
    """
    Validate negative keywords list.

    Args:
        keywords: List of negative keywords

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(keywords, list):
        raise ValidationError("Keywords must be a list")

    if len(keywords) == 0:
        raise ValidationError("Keywords list cannot be empty")

    if len(keywords) > 5000:
        raise ValidationError("Too many keywords (max: 5000)")

    for keyword in keywords:
        if not isinstance(keyword, str):
            raise ValidationError("Each keyword must be a string")

        if len(keyword) < 1 or len(keyword) > 80:
            raise ValidationError("Keyword length must be between 1 and 80 characters")

        # Prevent injection attempts
        if any(char in keyword for char in ['<', '>', '{', '}', '[', ']', ';']):
            raise ValidationError(f"Keyword contains invalid characters: {keyword}")

    return True

def validate_product_groups(product_groups: List[Dict[str, Any]]) -> bool:
    """
    Validate product groups configuration.

    Args:
        product_groups: List of product group configurations

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(product_groups, list):
        raise ValidationError("Product groups must be a list")

    if len(product_groups) == 0:
        raise ValidationError("Product groups list cannot be empty")

    for pg in product_groups:
        if not isinstance(pg, dict):
            raise ValidationError("Each product group must be a dictionary")

        # Validate required fields
        if "dimension" not in pg:
            raise ValidationError("Product group must have 'dimension' field")

        valid_dimensions = [
            "product_type",
            "brand",
            "item_id",
            "condition",
            "custom_label_0",
            "custom_label_1",
            "custom_label_2",
            "custom_label_3",
            "custom_label_4"
        ]

        if pg["dimension"] not in valid_dimensions:
            raise ValidationError(
                f"Product group dimension must be one of: {', '.join(valid_dimensions)}"
            )

    return True

def sanitize_output(data: Any, max_tokens: int = 25000) -> str:
    """
    Sanitize and limit output to prevent token overflow.

    Args:
        data: Data to sanitize
        max_tokens: Maximum token limit (default: 25000)

    Returns:
        Sanitized string output
    """
    import json

    try:
        output = json.dumps(data, indent=2, default=str)
    except Exception:
        output = str(data)

    # Approximate 4 chars per token
    max_chars = max_tokens * 4

    if len(output) > max_chars:
        output = output[:max_chars] + "\n\n... (output truncated to fit token limit)"

    return output
