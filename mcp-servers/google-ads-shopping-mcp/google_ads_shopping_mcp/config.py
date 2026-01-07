"""Configuration module for Google Ads API client."""
import os
import yaml
from pathlib import Path
from google.ads.googleads.client import GoogleAdsClient

# Default config file path
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "google-ads.yaml"

# Constants from user requirements
CUSTOMER_ID = "5945647044"
MERCHANT_CENTER_ID = "5625374390"

def load_google_ads_client(config_path: str = None) -> GoogleAdsClient:
    """
    Load Google Ads client from YAML configuration.

    Args:
        config_path: Path to google-ads.yaml file. If None, uses default location.

    Returns:
        GoogleAdsClient instance

    Raises:
        FileNotFoundError: If config file not found
        ValueError: If config file is invalid
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Google Ads config file not found at: {config_path}\n"
            f"Please ensure google-ads.yaml exists."
        )

    try:
        # Load YAML config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Validate required fields
        required_fields = ['developer_token', 'client_id', 'client_secret', 'refresh_token']
        missing_fields = [field for field in required_fields if field not in config]

        if missing_fields:
            raise ValueError(
                f"Missing required fields in config: {', '.join(missing_fields)}"
            )

        # Create client from dict
        return GoogleAdsClient.load_from_dict(config)

    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file: {e}")
    except Exception as e:
        raise ValueError(f"Error loading Google Ads client: {e}")

def get_customer_id() -> str:
    """Get the customer ID without hyphens."""
    return CUSTOMER_ID.replace("-", "")

def get_merchant_center_id() -> str:
    """Get the Merchant Center ID."""
    return MERCHANT_CENTER_ID
