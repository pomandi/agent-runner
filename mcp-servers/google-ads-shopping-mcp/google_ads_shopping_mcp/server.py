#!/usr/bin/env python3
"""
Entry point for the Google Ads Shopping MCP server.

This MCP server provides tools for managing Google Ads Shopping campaigns,
including campaign creation, ad group management, product groups, and negative keywords.
"""
import logging

from google_ads_shopping_mcp.coordinator import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# The following imports are necessary to register the tools with the `mcp`
# object, even though they are not directly used in this file.
# The `# noqa: F401` comment tells the linter to ignore the "unused import"
# warning.
from google_ads_shopping_mcp.tools import campaigns  # noqa: F401
from google_ads_shopping_mcp.tools import ad_groups  # noqa: F401
from google_ads_shopping_mcp.tools import product_groups  # noqa: F401
from google_ads_shopping_mcp.tools import keywords  # noqa: F401


def run_server() -> None:
    """
    Runs the MCP server.

    Serves as the entrypoint for the 'google-ads-shopping-mcp' command.
    """
    mcp.run()


if __name__ == "__main__":
    run_server()
