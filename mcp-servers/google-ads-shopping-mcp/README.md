# Google Ads Shopping MCP Server

MCP Server for managing Google Ads Shopping campaigns, ad groups, product groups, and negative keywords.

## Features

- **Campaign Management**: Create and manage Standard Shopping campaigns
- **Ad Group Management**: Create and configure Shopping ad groups
- **Product Groups**: Set up product partitioning and bidding structures
- **Negative Keywords**: Add and manage negative keywords to filter traffic
- **Security**: Built-in input validation and sanitization
- **Error Handling**: Comprehensive error handling with detailed messages

## Installation

1. Install dependencies:
```bash
cd google-ads-shopping-mcp
pip install -r requirements.txt
```

2. Ensure `google-ads.yaml` exists in the parent directory with your Google Ads API credentials.

## Configuration

The server uses the following configuration:
- **Config File**: `../google-ads.yaml`
- **Customer ID**: 5945647044
- **Merchant Center ID**: 5625374390

### google-ads.yaml Format

```yaml
developer_token: YOUR_DEVELOPER_TOKEN
client_id: YOUR_CLIENT_ID
client_secret: YOUR_CLIENT_SECRET
refresh_token: YOUR_REFRESH_TOKEN
login_customer_id: '5945647044'
use_proto_plus: true
```

## MCP Tools

### 1. create_shopping_campaign

Create a Standard Shopping campaign.

**Parameters:**
- `campaign_name` (string, required): Name of the campaign (1-255 characters)
- `daily_budget` (float, required): Daily budget in EUR
- `country` (string, optional): Target country (BE or NL). Default: BE
- `bidding_strategy` (string, optional): Bidding strategy. Options:
  - `MANUAL_CPC`: Manual cost-per-click
  - `MAXIMIZE_CLICKS`: Maximize clicks within budget
  - `TARGET_ROAS`: Target return on ad spend
  - `MAXIMIZE_CONVERSION_VALUE`: Maximize conversion value
  - `TARGET_CPA`: Target cost per acquisition
  - Default: MANUAL_CPC

**Example:**
```json
{
  "campaign_name": "Summer Sale - Kostuum Heren",
  "daily_budget": 50.0,
  "country": "BE",
  "bidding_strategy": "MAXIMIZE_CLICKS"
}
```

**Response:**
```json
{
  "success": true,
  "campaign_id": "12345",
  "resource_name": "customers/5945647044/campaigns/12345",
  "status": "PAUSED",
  "settings": {
    "name": "Summer Sale - Kostuum Heren",
    "daily_budget": 50.0,
    "country": "BE",
    "bidding_strategy": "MAXIMIZE_CLICKS",
    "merchant_center_id": "5625374390"
  }
}
```

### 2. get_shopping_campaigns

Retrieve all Shopping campaigns.

**Example Response:**
```json
{
  "success": true,
  "total": 3,
  "campaigns": [
    {
      "id": "12345",
      "name": "Summer Sale - Kostuum Heren",
      "status": "ENABLED",
      "daily_budget": 50.0,
      "sales_country": "BE"
    }
  ]
}
```

### 3. create_ad_group

Create a Shopping ad group within a campaign.

**Parameters:**
- `campaign_id` (string, required): ID of the parent campaign
- `ad_group_name` (string, required): Name of the ad group (1-255 characters)

**Example:**
```json
{
  "campaign_id": "12345",
  "ad_group_name": "All Products"
}
```

**Response:**
```json
{
  "success": true,
  "ad_group_id": "67890",
  "resource_name": "customers/5945647044/adGroups/67890",
  "status": "ENABLED"
}
```

### 4. get_ad_groups

Retrieve all ad groups for a campaign.

**Parameters:**
- `campaign_id` (string, required): ID of the campaign

### 5. set_product_groups

Configure product groups for bidding structure.

**Parameters:**
- `ad_group_id` (string, required): ID of the ad group
- `product_groups` (array, required): List of product group configurations

**Product Group Structure:**
```json
{
  "dimension": "brand",
  "value": "Nike",
  "bid": 2.0
}
```

**Available Dimensions:**
- `product_type`: Product category/type
- `brand`: Brand name
- `item_id`: Specific product ID
- `condition`: NEW, USED, REFURBISHED
- `custom_label_0` through `custom_label_4`: Custom labels

**Example - Simple "All Products":**
```json
{
  "ad_group_id": "67890",
  "product_groups": [
    {
      "dimension": "product_type",
      "value": null,
      "bid": 1.5
    }
  ]
}
```

**Example - By Brand:**
```json
{
  "ad_group_id": "67890",
  "product_groups": [
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
      "value": null,
      "bid": 1.0
    }
  ]
}
```

### 6. get_product_groups

Retrieve product groups for an ad group.

**Parameters:**
- `ad_group_id` (string, required): ID of the ad group

### 7. add_negative_keywords

Add negative keywords to filter traffic.

**Parameters:**
- `campaign_id` (string, required): ID of the campaign
- `keywords` (array, required): List of negative keywords (max 5000)
- `match_type` (string, optional): Match type (EXACT, PHRASE, BROAD). Default: EXACT

**Example:**
```json
{
  "campaign_id": "12345",
  "keywords": ["gratis", "goedkoop", "tweedehands", "replica"],
  "match_type": "BROAD"
}
```

### 8. get_negative_keywords

Retrieve all negative keywords for a campaign.

**Parameters:**
- `campaign_id` (string, required): ID of the campaign

### 9. remove_negative_keywords

Remove negative keywords from a campaign.

**Parameters:**
- `campaign_id` (string, required): ID of the campaign
- `criterion_ids` (array, required): List of criterion IDs to remove

## Usage with Claude Code

Add the server to Claude Code:

```bash
# Windows (from project root)
claude mcp add --transport stdio google-ads-shopping -- python -m google_ads_shopping_mcp.server

# Check status
/mcp
```

## Security Features

### Input Validation
- Campaign names: 1-255 characters, no injection characters
- Daily budget: Must be > 0 and < 1,000,000
- Country codes: Whitelist (BE, NL)
- Bidding strategies: Whitelist validation
- Keywords: Max 5000, 1-80 characters each

### Output Sanitization
- Automatic token limit enforcement (25,000 tokens)
- Truncation for large responses
- Safe JSON serialization

### Error Handling
- Validation errors with clear messages
- API error wrapping
- Comprehensive logging

## Development

### Run Tests
```bash
pytest tests/
```

### Code Style
```bash
black google_ads_shopping_mcp/
```

### Logging
Logs are written to stderr with timestamps:
```
2025-12-09 10:30:45 - google_ads_shopping_mcp.tools.campaigns - INFO - Creating campaign: Summer Sale
```

## Common Workflows

### Create a Complete Shopping Campaign

1. **Create Campaign:**
```json
{
  "tool": "create_shopping_campaign",
  "params": {
    "campaign_name": "Summer Sale - Kostuum Heren",
    "daily_budget": 50.0,
    "country": "BE",
    "bidding_strategy": "MAXIMIZE_CLICKS"
  }
}
```

2. **Create Ad Group:**
```json
{
  "tool": "create_ad_group",
  "params": {
    "campaign_id": "12345",
    "ad_group_name": "All Products"
  }
}
```

3. **Set Product Groups:**
```json
{
  "tool": "set_product_groups",
  "params": {
    "ad_group_id": "67890",
    "product_groups": [
      {
        "dimension": "product_type",
        "value": null,
        "bid": 1.5
      }
    ]
  }
}
```

4. **Add Negative Keywords:**
```json
{
  "tool": "add_negative_keywords",
  "params": {
    "campaign_id": "12345",
    "keywords": ["gratis", "goedkoop", "tweedehands"],
    "match_type": "BROAD"
  }
}
```

## Troubleshooting

### "Config file not found"
Ensure `google-ads.yaml` exists in the parent directory.

### "Invalid credentials"
Check that your refresh token is valid and not expired. Regenerate if needed.

### "Merchant Center not linked"
Verify that Merchant Center ID 5625374390 is linked to Customer ID 5945647044.

### "API quota exceeded"
Google Ads API has rate limits. Implement backoff and retry logic.

## Version

- **Version**: 1.0.0
- **MCP Tier**: 3 (Captain)
- **Date**: 2025-12-09

## License

Apache-2.0

## References

- [Google Ads API Documentation](https://developers.google.com/google-ads/api/docs/start)
- [Shopping Campaigns Guide](https://developers.google.com/google-ads/api/docs/shopping-ads/overview)
- [MCP Protocol Specification](https://modelcontextprotocol.io/specification/2025-06-18/)
