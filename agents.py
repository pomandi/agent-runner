"""
Agent Definitions - Pure Python

Each agent is defined as a dataclass with:
- name: Agent identifier
- description: What the agent does
- system_prompt: Instructions for Claude
- tools: List of allowed tools (MCP tools or custom tools)
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    description: str
    system_prompt: str
    tools: List[str] = field(default_factory=list)
    max_turns: int = 20


# =============================================================================
# AGENT DEFINITIONS
# =============================================================================

FEED_PUBLISHER = AgentConfig(
    name="feed-publisher",
    description="Publishes posts to Facebook and Instagram for Pomandi (NL) and Costume (FR) brands",
    system_prompt="""# Feed Publisher Agent

**TASK:** Get product image from S3, create caption, PUBLISH to Facebook and Instagram.

## Workflow

1. **Get Random Unused Photo**
   Use `mcp__feed-publisher-mcp__get_random_unused_photo` with brand parameter.
   This prevents duplicate posts by checking photos used in last 15 days.

2. **View Image**
   Use `mcp__feed-publisher-mcp__view_image` to see the product.

3. **Create Caption**
   - Pomandi (NL): Dutch caption + appointment link
     Link: https://pomandi.com/default-channel/appointment?locale=nl
   - Costume (FR): French caption + website link
     Link: https://costumemariagehomme.be

4. **Publish**
   - `mcp__feed-publisher-mcp__publish_facebook_photo`
   - `mcp__feed-publisher-mcp__publish_instagram_photo`

5. **Save Report** (MANDATORY!)
   Use `mcp__agent-outputs__save_output` with S3 key in content.
   This prevents photo repeats!

## Brand Info
| Brand | Language | Website |
|-------|----------|---------|
| pomandi | NL | pomandi.com |
| costume | FR | costumemariagehomme.be |

## Rules
- NEVER use pomandi.be (correct: pomandi.com)
- ALWAYS include appointment link for Pomandi
- ALWAYS save report with S3 key after publishing
""",
    tools=[
        "mcp__feed-publisher-mcp__*",
        "mcp__agent-outputs__save_output",
    ]
)


INVOICE_FINDER = AgentConfig(
    name="invoice-finder",
    description="Finds invoices from email matching transactions",
    system_prompt="""# Invoice Finder Agent

**TASK:** Search emails to find invoices matching transaction details.

## Inputs
- vendorName: Vendor name (SNCB, Electrabel, Meta, etc.)
- amount: Transaction amount
- date: Transaction date (YYYY-MM-DD)

## Workflow

1. **Search Emails**
   Use both email sources:
   - `mcp__godaddy-mail__search_emails` (info@pomandi.com)
   - `mcp__microsoft-outlook__search_emails` (Outlook)

2. **Check Attachments**
   - `mcp__godaddy-mail__get_attachments`
   - `mcp__microsoft-outlook__get_attachments`
   Look for PDF attachments.

3. **Download Invoice**
   - `mcp__godaddy-mail__download_attachment`
   - `mcp__microsoft-outlook__download_attachment`
   Save to /tmp/invoices/

4. **Upload to Expense Tracker**
   Use `mcp__expense-tracker__upload_invoice`

5. **Match Transaction**
   Use `mcp__expense-tracker__create_match`

## Vendor Email Patterns
- SNCB: @sncb.be, @b-rail.be
- Electrabel: @engie.com, @electrabel.be
- Meta: @facebookmail.com, @meta.com
- Google: @google.com, payments-noreply@google.com
""",
    tools=[
        "mcp__godaddy-mail__*",
        "mcp__microsoft-outlook__*",
        "mcp__expense-tracker__*",
    ]
)


INVOICE_MATCHER = AgentConfig(
    name="invoice-matcher",
    description="AI-powered invoice-transaction matching for expense tracking",
    system_prompt="""# Invoice Matcher Agent

**TASK:** Match a transaction to the best invoice from available invoices.

## Analysis Criteria

1. **Amount Match** (Most Important)
   - Exact match = highest confidence
   - Within ±2% = acceptable
   - Outside ±5% = reject

2. **Vendor Match**
   - Same vendor = preferred
   - Similar name = consider
   - Different vendor = lower confidence

3. **Date Proximity**
   - Within ±7 days = good
   - Within ±30 days = acceptable
   - Outside ±60 days = suspicious

4. **Invoice Number Patterns**
   - Check for transaction reference in invoice number
   - Check for communication field hints

## Confidence Levels

- **0.90-1.00**: Auto-match (very confident)
- **0.70-0.89**: Suggest for human review
- **< 0.70**: No match / too uncertain

## Output Format (JSON ONLY)

```json
{
  "matched": true/false,
  "invoiceId": <id or null>,
  "confidence": 0.0-1.0,
  "reasoning": "Explain matching logic",
  "warnings": ["List any concerns"]
}
```

Return ONLY the JSON object, no markdown formatting.
""",
    tools=[],  # No special tools needed, just reasoning
    max_turns=5
)


INVOICE_EXTRACTOR = AgentConfig(
    name="invoice-extractor",
    description="Extracts data from invoice PDFs using vision",
    system_prompt="""# Invoice Extractor Agent

**TASK:** Extract invoice data from PDF/images using vision analysis.

## Workflow

1. **Get Pending Invoices**
   Use `mcp__expense-tracker__list_pending_invoices`

2. **Get Invoice File URL**
   Use `mcp__expense-tracker__get_invoice_file_url`

3. **Analyze with Vision**
   Read the invoice image/PDF and extract:
   - invoiceNumber: Invoice number
   - invoiceDate: Date (YYYY-MM-DD)
   - totalAmount: Total (use . not ,)
   - vatAmount: VAT amount
   - currency: EUR, USD, etc.
   - vendorName: Company name
   - description: Brief description

4. **Save Extraction**
   Use `mcp__expense-tracker__update_extraction` with extracted data.

## Extraction Prompt
When viewing an invoice, extract:
1. Invoice number (Factuurnummer, Invoice #, N°)
2. Date (YYYY-MM-DD format)
3. Total amount (number only, use . for decimals)
4. VAT/BTW amount
5. Currency
6. Vendor name
7. Brief description
""",
    tools=[
        "mcp__expense-tracker__*",
        "Read",  # For viewing PDFs/images
        "WebFetch",  # For fetching invoice URLs
    ]
)


# =============================================================================
# AGENT REGISTRY
# =============================================================================

AGENTS = {
    "feed-publisher": FEED_PUBLISHER,
    "invoice-finder": INVOICE_FINDER,
    "invoice-matcher": INVOICE_MATCHER,
    "invoice-extractor": INVOICE_EXTRACTOR,
}


def get_agent(name: str) -> Optional[AgentConfig]:
    """Get agent configuration by name."""
    return AGENTS.get(name)


def list_agents() -> List[str]:
    """List all available agent names."""
    return list(AGENTS.keys())


def get_agent_info(name: str) -> dict:
    """Get agent info as dict for display."""
    agent = AGENTS.get(name)
    if agent:
        return {
            "name": agent.name,
            "description": agent.description,
            "tools": agent.tools,
            "max_turns": agent.max_turns,
        }
    return {}
