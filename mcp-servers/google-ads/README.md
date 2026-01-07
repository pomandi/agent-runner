# Google Ads MCP Server

MCP (Model Context Protocol) server for Google Ads API integration with Claude Code.

## Features

- Campaign performance metrics
- Ad group analysis
- Keyword performance with quality scores
- Search terms reports
- Geographic performance
- Device performance breakdown
- Conversion tracking
- Custom GAQL queries

## Installation

```bash
cd mcp-tools/servers/google-ads
pip install -r requirements.txt
```

## Configuration

### 1. Google Ads API Credentials

Create `~/.claude/config/google-ads.yaml`:

```yaml
developer_token: YOUR_DEVELOPER_TOKEN
client_id: YOUR_CLIENT_ID
client_secret: YOUR_CLIENT_SECRET
refresh_token: YOUR_REFRESH_TOKEN
login_customer_id: YOUR_MCC_ID
use_proto_plus: true
```

### 2. Environment Variables (Optional)

```bash
export GOOGLE_ADS_YAML_PATH=/path/to/google-ads.yaml
export GOOGLE_ADS_CUSTOMER_ID=1234567890
```

### 3. Claude Code Settings

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "python",
      "args": ["/path/to/mcp-tools/servers/google-ads/server.py"],
      "env": {
        "GOOGLE_ADS_YAML_PATH": "/path/to/google-ads.yaml",
        "GOOGLE_ADS_CUSTOMER_ID": "5945647044"
      }
    }
  }
}
```

## Available Tools

### get_campaigns
Get Search campaign performance data.

```
Parameters:
- start_date: Start date (YYYY-MM-DD)
- end_date: End date (YYYY-MM-DD)
- days: Alternative - number of days back (default: 7)
```

### get_ad_groups
Get ad group performance data.

```
Parameters:
- start_date: Start date (YYYY-MM-DD)
- end_date: End date (YYYY-MM-DD)
- campaign_id: Optional campaign filter
```

### get_keywords
Get keyword performance with quality scores.

```
Parameters:
- start_date: Start date (YYYY-MM-DD)
- end_date: End date (YYYY-MM-DD)
- campaign_id: Optional campaign filter
- min_impressions: Minimum impressions (default: 0)
- limit: Max results (default: 1000)
```

### get_search_terms
Get search terms report.

```
Parameters:
- start_date: Start date (YYYY-MM-DD)
- end_date: End date (YYYY-MM-DD)
- campaign_id: Optional campaign filter
- min_impressions: Minimum impressions (default: 1)
- limit: Max results (default: 500)
```

### get_ads
Get ad performance including RSA details.

```
Parameters:
- start_date: Start date (YYYY-MM-DD)
- end_date: End date (YYYY-MM-DD)
- campaign_id: Optional campaign filter
```

### get_geo_performance
Get geographic performance breakdown.

```
Parameters:
- start_date: Start date (YYYY-MM-DD)
- end_date: End date (YYYY-MM-DD)
- campaign_id: Optional campaign filter
```

### get_device_performance
Get device performance breakdown.

```
Parameters:
- start_date: Start date (YYYY-MM-DD)
- end_date: End date (YYYY-MM-DD)
```

### get_conversions
Get conversion actions configuration.

```
No parameters required.
```

### run_gaql_query
Run custom GAQL query.

```
Parameters:
- query: GAQL query string (required)
```

## Usage Examples

After setup, use in Claude Code:

```
# Get last 7 days campaign performance
mcp__google-ads__get_campaigns(days=7)

# Get search terms for specific campaign
mcp__google-ads__get_search_terms(start_date="2025-11-01", end_date="2025-11-30", campaign_id="12345678")

# Run custom query
mcp__google-ads__run_gaql_query(query="SELECT campaign.name, metrics.clicks FROM campaign WHERE campaign.status = 'ENABLED'")
```

## Troubleshooting

### Authentication Error
- Check google-ads.yaml credentials
- Verify refresh token is valid
- Ensure developer token has API access

### No Data Returned
- Verify customer ID is correct
- Check date range has data
- Ensure campaigns exist and are not REMOVED

### Rate Limits
- Google Ads API has rate limits
- Use date range filters to reduce data
- Implement caching for frequent queries

## Version History

- **1.0.0** - Initial release with 9 tools
