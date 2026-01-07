# Meta Ads Campaign MCP Server

Creates campaigns via Meta Marketing API (Graph API v22.0) for Claude MCP tooling.

## Endpoints
- `POST https://graph.facebook.com/v22.0/act_{ad_account_id}/campaigns`
- Official docs: https://developers.facebook.com/docs/marketing-api/reference/ad-campaign-group/
- Auth overview: https://developers.facebook.com/docs/marketing-api/access

## Env Vars
- `FACEBOOK_ACCESS_TOKEN` (required)
- `FACEBOOK_AD_ACCOUNT_ID` (required, e.g., `act_123456789012345`)

## Tools
- `create_campaign`
  - required: `name`, `objective`, `daily_budget`
  - optional: `status` (default `PAUSED`), `special_ad_categories` (default `["NONE"]`), `bid_strategy`, `start_time`, `stop_time`, `ad_account_id` override

## Run
```bash
pip install -r requirements.txt
python server.py
```

## Notes
- Sends `special_ad_categories` as JSON array string per API requirements.
- Keep tokens short-lived; refresh outside MCP or rotate via meta-token-refresher.
