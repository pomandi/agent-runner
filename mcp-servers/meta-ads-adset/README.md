# Meta Ads Ad Set MCP Server

Creates ad sets via Meta Marketing API (Graph API v22.0) for Claude MCP tooling.

## Endpoints
- `POST https://graph.facebook.com/v22.0/act_{ad_account_id}/adsets`
- Official docs: https://developers.facebook.com/docs/marketing-api/reference/ad-set
- Targeting guide: https://developers.facebook.com/docs/marketing-api/audiences/reference
- Auth overview: https://developers.facebook.com/docs/marketing-api/access

## Env Vars
- `FACEBOOK_ACCESS_TOKEN` (required)
- `FACEBOOK_AD_ACCOUNT_ID` (required, e.g., `act_123456789012345`)

## Tools
- `create_adset`
  - required: `campaign_id`, `name`, `daily_budget`, `billing_event`, `optimization_goal`, `targeting`
  - optional: `status` (default `PAUSED`), `bid_amount`, `start_time`, `end_time`, `promoted_object`, `ad_account_id` override

## Run
```bash
pip install -r requirements.txt
python server.py
```

## Notes
- `targeting` and `promoted_object` are passed as JSON strings to the API.
- Keep ad sets paused by default; activate after creative review.
