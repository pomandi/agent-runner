# Meta Ads Ad MCP Server

Creates ads via Meta Marketing API (Graph API v22.0) for Claude MCP tooling.

## Endpoints
- `POST https://graph.facebook.com/v22.0/act_{ad_account_id}/ads`
- Official docs: https://developers.facebook.com/docs/marketing-api/reference/ad
- Creative reference: https://developers.facebook.com/docs/marketing-api/reference/ad-creative
- Auth overview: https://developers.facebook.com/docs/marketing-api/access

## Env Vars
- `FACEBOOK_ACCESS_TOKEN` (required)
- `FACEBOOK_AD_ACCOUNT_ID` (required, e.g., `act_123456789012345`)

## Tools
- `create_ad`
  - required: `adset_id`, `name`, `creative_id`
  - optional: `status` (default `PAUSED`), `tracking_specs`, `ad_account_id` override

## Run
```bash
pip install -r requirements.txt
python server.py
```

## Notes
- Assumes creative already exists; pass `creative_id` and the server wraps it in `{"creative_id": ...}`.
- Keep ads paused until manual QA is complete.
