#!/usr/bin/env python3
"""
Agent Runner HTTP API v2
========================

SDK-ONLY architecture - No subprocess CLI calls!

Key changes from v1:
- Uses AgentRegistry for configuration (agents.yaml)
- Uses SDKExecutor for all Claude calls
- No hardcoded agent configurations
- Scalable: adding new agents requires only YAML changes

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                      API Layer                          │
    │  FastAPI endpoints (/run, /api/invoice-match, etc.)     │
    └────────────────────────┬────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │                   AgentRegistry                          │
    │  Loads agents.yaml, provides agent config                │
    └────────────────────────┬────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │                   SDKExecutor                            │
    │  Executes prompts via Claude Agent SDK                   │
    └────────────────────────┬────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │              Claude Agent SDK (Python)                   │
    │  Uses ~/.claude/.credentials.json for auth               │
    └─────────────────────────────────────────────────────────┘
"""
import asyncio
import os
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Local imports
from agent_registry import get_registry, reload_registry
from sdk_executor import SDKExecutor, check_sdk, ExecutionResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner-api")

# Initialize components
registry = get_registry()
executor = SDKExecutor() if check_sdk() else None

app = FastAPI(
    title="Agent Runner API",
    description="SDK-only agent execution with config-based agent management",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# State
current_run = {
    "running": False,
    "agent": None,
    "task": None,
    "started_at": None,
    "log_file": None,
    "mode": "sdk"
}

LOGS_DIR = Path("/app/logs")
LOGS_DIR.mkdir(exist_ok=True)


# ============================================================
# Request/Response Models
# ============================================================

class RunRequest(BaseModel):
    agent: Optional[str] = None
    task: Optional[str] = None
    allowed_tools: Optional[str] = None  # Override from registry
    verbose: Optional[bool] = True


class RunResponse(BaseModel):
    status: str
    message: str
    run_id: Optional[str] = None
    agent: Optional[str] = None
    task: Optional[str] = None
    mode: str = "sdk"


# ============================================================
# Health & Status
# ============================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/status")
async def status():
    """Get current agent status and registry info."""
    creds_exist = Path(os.path.expanduser("~/.claude/.credentials.json")).exists()

    return {
        "container": "agent-runner",
        "version": "2.0.0",
        "architecture": "sdk-only",
        "sdk_available": check_sdk(),
        "credentials_found": creds_exist,
        "registered_agents": registry.list_agents(),
        "registered_endpoints": registry.list_endpoints(),
        "current_run": current_run,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/debug/cli")
async def debug_cli():
    """Debug endpoint to test bundled CLI directly."""
    import subprocess
    import os

    # Check file existence (use expanduser for non-root user)
    home = os.path.expanduser("~")
    creds_path = Path(f"{home}/.claude/.credentials.json")
    settings_path = Path(f"{home}/.claude/settings.json")
    bundled_cli = Path("/usr/local/lib/python3.11/dist-packages/claude_agent_sdk/_bundled/claude")
    npm_cli = Path("/usr/local/bin/claude")

    result = {
        "credentials_exists": creds_path.exists(),
        "settings_exists": settings_path.exists(),
        "bundled_cli_exists": bundled_cli.exists(),
        "npm_cli_exists": npm_cli.exists(),
        "HOME": os.environ.get("HOME", "not set"),
        "USER": os.environ.get("USER", "not set"),
    }

    # Read settings.json content
    if settings_path.exists():
        try:
            result["settings_content"] = settings_path.read_text()
        except Exception as e:
            result["settings_error"] = str(e)

    # Check credentials content (masked)
    if creds_path.exists():
        try:
            import json
            creds = json.loads(creds_path.read_text())
            oauth = creds.get("claudeAiOauth", {})
            result["credentials_info"] = {
                "hasAccessToken": "accessToken" in oauth,
                "hasRefreshToken": "refreshToken" in oauth,
                "expiresAt": oauth.get("expiresAt"),
                "subscriptionType": oauth.get("subscriptionType"),
            }
        except Exception as e:
            result["credentials_error"] = str(e)

    # Try running bundled CLI with --version
    if bundled_cli.exists():
        try:
            proc = subprocess.run(
                [str(bundled_cli), "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "HOME": "/root"}
            )
            result["bundled_cli_version"] = {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode
            }
        except Exception as e:
            result["bundled_cli_error"] = str(e)

    # Try a simple prompt with the bundled CLI
    if bundled_cli.exists():
        try:
            proc = subprocess.run(
                [str(bundled_cli), "--print", "--dangerously-skip-permissions"],
                input="Say 'hello' and nothing else",
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "HOME": "/root"}
            )
            result["simple_prompt_test"] = {
                "stdout": proc.stdout[:500] if proc.stdout else "",
                "stderr": proc.stderr[:1000] if proc.stderr else "",
                "returncode": proc.returncode
            }
        except Exception as e:
            result["simple_prompt_error"] = str(e)

    return result


@app.get("/agents")
async def list_agents():
    """List all registered agents with their configuration."""
    agents = {}
    for name in registry.list_agents(enabled_only=False):
        agent = registry.get_agent(name)
        if agent:
            agents[name] = {
                "description": agent.description,
                "enabled": agent.enabled,
                "tools": agent.tools,
                "cwd": agent.cwd,
                "max_turns": agent.max_turns,
                "schedule": agent.schedule
            }
    return {"agents": agents, "total": len(agents)}


@app.post("/agents/reload")
async def reload_agents():
    """Reload agent configuration from YAML."""
    reload_registry()
    return {
        "status": "reloaded",
        "agents": registry.list_agents(),
        "endpoints": registry.list_endpoints()
    }


# ============================================================
# Agent Execution
# ============================================================

async def run_agent_background(agent_name: str, task: str, log_file: Path):
    """Run agent in background using SDK."""
    global current_run

    try:
        current_run["running"] = True
        current_run["agent"] = agent_name
        current_run["task"] = task
        current_run["started_at"] = datetime.now().isoformat()
        current_run["log_file"] = str(log_file)

        logger.info(f"[Agent] Starting: {agent_name}")
        logger.info(f"[Agent] Task: {task[:100]}...")

        result = await executor.run_agent(
            agent_name=agent_name,
            task=task,
            log_file=log_file
        )

        if result.success:
            logger.info(f"[Agent] Completed: {result.message_count} messages, {result.tool_calls} tools")
        else:
            logger.error(f"[Agent] Failed: {result.error}")

    except Exception as e:
        logger.error(f"[Agent] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        current_run["running"] = False


@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest, background_tasks: BackgroundTasks):
    """Run an agent using SDK.

    Agent configuration is loaded from agents.yaml.
    No hardcoded configurations - everything is config-driven!
    """
    if current_run["running"]:
        raise HTTPException(
            status_code=409,
            detail=f"Agent already running: {current_run['agent']}"
        )

    if not check_sdk():
        raise HTTPException(
            status_code=503,
            detail="Claude Agent SDK not available"
        )

    if not Path(os.path.expanduser("~/.claude/.credentials.json")).exists():
        raise HTTPException(
            status_code=503,
            detail="Claude credentials not found"
        )

    # Get agent name
    agent_name = request.agent or os.getenv("AGENT_NAME", "feed-publisher")

    # Check if agent exists in registry
    agent_config = registry.get_agent(agent_name)
    if not agent_config:
        # List available agents in error
        available = registry.list_agents()
        raise HTTPException(
            status_code=404,
            detail=f"Agent not found: {agent_name}. Available: {available}"
        )

    if not agent_config.enabled:
        raise HTTPException(
            status_code=400,
            detail=f"Agent is disabled: {agent_name}"
        )

    task = request.task or os.getenv("AGENT_TASK", "Run the agent task")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = LOGS_DIR / f"{agent_name}-{run_id}.log"

    # Start agent in background
    asyncio.create_task(run_agent_background(agent_name, task, log_file))

    return RunResponse(
        status="started",
        message=f"Agent {agent_name} started (SDK mode)",
        run_id=run_id,
        agent=agent_name,
        task=task,
        mode="sdk"
    )


# ============================================================
# Logs
# ============================================================

@app.get("/logs")
async def get_logs(limit: int = 10):
    """Get recent log files."""
    log_files = sorted(LOGS_DIR.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)

    logs = []
    for f in log_files[:limit]:
        logs.append({
            "file": f.name,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        })

    return {"logs": logs, "total": len(log_files)}


@app.get("/logs/latest")
async def get_latest_log(tail: int = 0):
    """Get the most recent log file."""
    log_files = sorted(LOGS_DIR.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not log_files:
        return {
            "status": "no_logs",
            "message": "No log files found. Run an agent first with POST /run",
            "running": current_run["running"]
        }

    latest = log_files[0]
    content = latest.read_text()
    lines = content.split("\n")

    if tail > 0 and len(lines) > tail:
        lines = lines[-tail:]

    return {
        "file": latest.name,
        "lines": len(lines),
        "running": current_run["running"],
        "content": "\n".join(lines)
    }


@app.get("/logs/{filename}")
async def get_log_content(filename: str, tail: int = 0):
    """Get content of a specific log file."""
    log_file = LOGS_DIR / filename

    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    content = log_file.read_text()
    lines = content.split("\n")

    if tail > 0 and len(lines) > tail:
        lines = lines[-tail:]

    return {
        "file": filename,
        "lines": len(lines),
        "content": "\n".join(lines)
    }


# ============================================================
# Invoice Match Endpoint (SDK-based)
# ============================================================

class InvoiceMatchRequest(BaseModel):
    transaction: dict
    invoices: list


class InvoiceMatchResponse(BaseModel):
    success: bool
    matched: bool = False
    invoiceId: Optional[int] = None
    confidence: float = 0
    reasoning: str = ""
    warnings: list = []
    error: Optional[str] = None


INVOICE_MATCH_PROMPT = """You are an expert invoice matching assistant for a Belgian company's expense tracking system.

Your job is to analyze a bank transaction and find the best matching invoice from a list of available invoices.

CRITICAL MATCHING RULES:
1. AMOUNT: The transaction amount and invoice amount MUST match within 1% tolerance.
2. VENDOR: If the transaction has a vendor name, it should match or be similar to the invoice vendor.
3. DATE: The invoice date should be within 30 days of the transaction date.
4. NEVER match if amounts differ by more than 5%.

OUTPUT FORMAT - Respond with valid JSON only:
{{
  "matched": true or false,
  "invoiceId": number or null,
  "confidence": number between 0 and 1,
  "reasoning": "brief explanation",
  "amountDifference": number (percentage),
  "warnings": ["any concerns"]
}}

TRANSACTION TO MATCH:
{transaction_json}

AVAILABLE UNMATCHED INVOICES:
{invoices_json}

Analyze and respond with JSON only."""


@app.post("/api/invoice-match", response_model=InvoiceMatchResponse)
async def match_invoice(request: InvoiceMatchRequest):
    """Match a transaction with invoices using Claude SDK."""
    if not check_sdk():
        return InvoiceMatchResponse(success=False, error="SDK not available")

    try:
        prompt = INVOICE_MATCH_PROMPT.format(
            transaction_json=json.dumps(request.transaction, indent=2),
            invoices_json=json.dumps(request.invoices, indent=2)
        )

        logger.info(f"[InvoiceMatch] Processing transaction {request.transaction.get('id')}")

        result = await executor.run_prompt(
            prompt=prompt,
            tools=[],  # No tools needed for matching
            max_turns=5,
            timeout_seconds=60
        )

        if not result.success:
            return InvoiceMatchResponse(success=False, error=result.error)

        json_data = result.get_json()
        if not json_data:
            return InvoiceMatchResponse(success=False, error="No valid JSON in response")

        return InvoiceMatchResponse(
            success=True,
            matched=json_data.get("matched", False),
            invoiceId=json_data.get("invoiceId"),
            confidence=json_data.get("confidence", 0),
            reasoning=json_data.get("reasoning", ""),
            warnings=json_data.get("warnings", [])
        )

    except Exception as e:
        logger.error(f"[InvoiceMatch] Error: {e}")
        return InvoiceMatchResponse(success=False, error=str(e))


# ============================================================
# Invoice Extract Endpoint (SDK-based)
# ============================================================

class InvoiceExtractRequest(BaseModel):
    pdf_url: str
    invoice_id: Optional[int] = None


class InvoiceExtractResponse(BaseModel):
    success: bool
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    total_amount: Optional[float] = None
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    vat_rate: Optional[float] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_vat_number: Optional[str] = None
    currency: str = "EUR"
    line_items: list = []
    raw_text: Optional[str] = None
    error: Optional[str] = None


INVOICE_EXTRACT_PROMPT = """You are an expert invoice data extractor. Analyze the provided invoice and extract:

1. Invoice number, date (YYYY-MM-DD format)
2. Total amount, subtotal, VAT amount/rate
3. Vendor name, address, VAT number
4. Currency (detect from symbols: €=EUR, $=USD, £=GBP, ¥=CNY/JPY, etc.)
5. Line items if visible

OUTPUT - Respond with valid JSON only:
{{
  "invoice_number": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "total_amount": number or null,
  "subtotal": number or null,
  "vat_amount": number or null,
  "vat_rate": number or null,
  "vendor_name": "string or null",
  "vendor_address": "string or null",
  "vendor_vat_number": "string or null",
  "currency": "3-letter ISO code",
  "line_items": [{{"description": "...", "quantity": N, "unit_price": N, "total": N}}],
  "raw_text": "brief summary"
}}

{content_section}

Respond with JSON only."""


@app.post("/api/invoice-extract", response_model=InvoiceExtractResponse)
async def extract_invoice(request: InvoiceExtractRequest):
    """Extract data from invoice PDF/image using Claude SDK."""
    import httpx
    from io import BytesIO
    import tempfile

    if not check_sdk():
        return InvoiceExtractResponse(success=False, error="SDK not available")

    try:
        logger.info(f"[InvoiceExtract] Processing: {request.pdf_url}")

        # Download file
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(request.pdf_url)
            if response.status_code != 200:
                return InvoiceExtractResponse(
                    success=False,
                    error=f"Download failed: HTTP {response.status_code}"
                )
            file_content = response.content

        logger.info(f"[InvoiceExtract] Downloaded: {len(file_content)} bytes")

        # Determine file type
        content_type = response.headers.get('content-type', '').lower()
        is_image = 'image' in content_type or any(ext in request.pdf_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp'])
        is_pdf = 'pdf' in content_type or '.pdf' in request.pdf_url.lower()

        if is_image:
            # Save image to temp file for Claude to read
            ext = '.jpg' if 'jpeg' in content_type or 'jpg' in content_type else '.png'
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir='/tmp') as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name

            content_section = f"Read and analyze the invoice image at: {tmp_path}"
            tools = ["Read"]

            try:
                prompt = INVOICE_EXTRACT_PROMPT.format(content_section=content_section)
                result = await executor.run_prompt(
                    prompt=prompt,
                    tools=tools,
                    max_turns=10,
                    timeout_seconds=120
                )
            finally:
                if Path(tmp_path).exists():
                    Path(tmp_path).unlink()

        elif is_pdf:
            # Extract text from PDF
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(file_content))
            pdf_text = ""
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    pdf_text += f"\n--- Page {page_num + 1} ---\n{page_text}"

            if not pdf_text.strip():
                return InvoiceExtractResponse(
                    success=False,
                    error="PDF contains no extractable text"
                )

            content_section = f"EXTRACTED PDF TEXT:\n{pdf_text[:8000]}"
            prompt = INVOICE_EXTRACT_PROMPT.format(content_section=content_section)

            result = await executor.run_prompt(
                prompt=prompt,
                tools=[],
                max_turns=5,
                timeout_seconds=90
            )
        else:
            return InvoiceExtractResponse(
                success=False,
                error=f"Unsupported file type: {content_type}"
            )

        if not result.success:
            return InvoiceExtractResponse(success=False, error=result.error)

        json_data = result.get_json()
        if not json_data:
            return InvoiceExtractResponse(success=False, error="No valid JSON in response")

        return InvoiceExtractResponse(
            success=True,
            invoice_number=json_data.get("invoice_number"),
            invoice_date=json_data.get("invoice_date"),
            total_amount=json_data.get("total_amount"),
            subtotal=json_data.get("subtotal"),
            vat_amount=json_data.get("vat_amount"),
            vat_rate=json_data.get("vat_rate"),
            vendor_name=json_data.get("vendor_name"),
            vendor_address=json_data.get("vendor_address"),
            vendor_vat_number=json_data.get("vendor_vat_number"),
            currency=json_data.get("currency", "EUR"),
            line_items=json_data.get("line_items", []),
            raw_text=json_data.get("raw_text")
        )

    except Exception as e:
        logger.error(f"[InvoiceExtract] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return InvoiceExtractResponse(success=False, error=str(e))


# ============================================================
# CC Statement Extract Endpoint (SDK-based)
# ============================================================

class CCStatementExtractRequest(BaseModel):
    pdf_url: str
    statement_id: Optional[int] = None
    card_last_four: Optional[str] = None


class CCStatementExtractResponse(BaseModel):
    success: bool
    statement_period: Optional[str] = None
    statement_date: Optional[str] = None
    due_date: Optional[str] = None
    opening_balance: Optional[float] = None
    total_purchases: Optional[float] = None
    total_payments: Optional[float] = None
    total_fees: Optional[float] = None
    closing_balance: Optional[float] = None
    minimum_payment: Optional[float] = None
    currency: str = "EUR"
    transactions: list = []
    card_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    error: Optional[str] = None


CC_STATEMENT_PROMPT = """You are an expert credit card statement data extractor.

Extract ALL information from the credit card statement:

1. STATEMENT INFO:
   - Statement period (YYYY-MM)
   - Statement/closing date
   - Payment due date
   - Card holder name
   - Bank/issuer name

2. SUMMARY AMOUNTS:
   - Opening balance
   - Total purchases/debits
   - Total payments/credits
   - Total fees/interest
   - Closing balance
   - Minimum payment

3. ALL TRANSACTIONS - Extract EVERY transaction:
   - Transaction date (YYYY-MM-DD)
   - Posting date (YYYY-MM-DD)
   - Description
   - Merchant name
   - Amount (positive for purchases, negative for refunds)
   - Transaction type: purchase, refund, fee, interest, payment
   - Original currency/amount if foreign

OUTPUT - Respond with valid JSON only:
{{
  "statement_period": "YYYY-MM",
  "statement_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD or null",
  "opening_balance": number or null,
  "total_purchases": number or null,
  "total_payments": number or null,
  "total_fees": number or null,
  "closing_balance": number or null,
  "minimum_payment": number or null,
  "currency": "EUR",
  "card_holder_name": "string or null",
  "bank_name": "string or null",
  "transactions": [
    {{
      "transaction_date": "YYYY-MM-DD",
      "posting_date": "YYYY-MM-DD or null",
      "description": "Full description",
      "merchant_name": "Merchant or null",
      "amount": number,
      "currency": "EUR",
      "original_amount": number or null,
      "original_currency": "code or null",
      "transaction_type": "purchase|refund|fee|interest|payment"
    }}
  ]
}}

{card_info}

EXTRACTED PDF TEXT:
{pdf_text}

Respond with JSON only."""


@app.post("/api/cc-statement-extract", response_model=CCStatementExtractResponse)
async def extract_cc_statement(request: CCStatementExtractRequest):
    """Extract data from credit card statement PDF using Claude SDK."""
    import httpx
    from io import BytesIO

    if not check_sdk():
        return CCStatementExtractResponse(success=False, error="SDK not available")

    try:
        logger.info(f"[CCStatement] Processing: {request.pdf_url}")

        # Download PDF
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(request.pdf_url)
            if response.status_code != 200:
                return CCStatementExtractResponse(
                    success=False,
                    error=f"Download failed: HTTP {response.status_code}"
                )
            file_content = response.content

        logger.info(f"[CCStatement] Downloaded: {len(file_content)} bytes")

        # Extract text from PDF
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(file_content))
        pdf_text = ""
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                pdf_text += f"\n--- Page {page_num + 1} ---\n{page_text}"

        if not pdf_text.strip():
            return CCStatementExtractResponse(
                success=False,
                error="PDF contains no extractable text"
            )

        logger.info(f"[CCStatement] Extracted {len(pdf_text)} chars from {len(reader.pages)} pages")

        card_info = f"Card last 4 digits: *{request.card_last_four}" if request.card_last_four else ""
        prompt = CC_STATEMENT_PROMPT.format(
            card_info=card_info,
            pdf_text=pdf_text[:12000]
        )

        result = await executor.run_prompt(
            prompt=prompt,
            tools=[],
            max_turns=5,
            timeout_seconds=120
        )

        if not result.success:
            return CCStatementExtractResponse(success=False, error=result.error)

        json_data = result.get_json()
        if not json_data:
            return CCStatementExtractResponse(
                success=False,
                error="No valid JSON in response"
            )

        transactions = json_data.get("transactions", [])
        logger.info(f"[CCStatement] Extracted {len(transactions)} transactions")

        return CCStatementExtractResponse(
            success=True,
            statement_period=json_data.get("statement_period"),
            statement_date=json_data.get("statement_date"),
            due_date=json_data.get("due_date"),
            opening_balance=json_data.get("opening_balance"),
            total_purchases=json_data.get("total_purchases"),
            total_payments=json_data.get("total_payments"),
            total_fees=json_data.get("total_fees"),
            closing_balance=json_data.get("closing_balance"),
            minimum_payment=json_data.get("minimum_payment"),
            currency=json_data.get("currency", "EUR"),
            transactions=transactions,
            card_holder_name=json_data.get("card_holder_name"),
            bank_name=json_data.get("bank_name")
        )

    except Exception as e:
        logger.error(f"[CCStatement] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return CCStatementExtractResponse(success=False, error=str(e))


# ============================================================
# Invoice Find Endpoint (SDK-based)
# ============================================================

class InvoiceFindRequest(BaseModel):
    transactionId: Optional[int] = None
    vendorName: str
    amount: float
    date: str
    description: Optional[str] = None
    counterpartyName: Optional[str] = None


class InvoiceFindResponse(BaseModel):
    success: bool
    found: bool = False
    invoiceId: Optional[int] = None
    message: Optional[str] = None
    source: Optional[dict] = None
    searchStrategy: Optional[str] = None
    emailsScanned: int = 0
    error: Optional[str] = None


INVOICE_FIND_PROMPT = """You are an invoice finder agent. Search emails to find an invoice matching:

TRANSACTION:
- Vendor: {vendor_name}
- Amount: {amount} EUR
- Date: {date}
- Description: {description}

SEARCH STRATEGY:
1. Search GoDaddy mail using mcp__godaddy-mail__search_emails
   - By vendor name in subject/sender
   - Date range: {date_start} to {date_end}

2. For emails with attachments:
   - Check for PDF files with mcp__godaddy-mail__get_attachments
   - Download with mcp__godaddy-mail__download_attachment

3. Also search Microsoft Outlook if available

RESPOND WITH JSON:
{{
  "found": true/false,
  "invoiceUploaded": true/false,
  "invoiceId": <id if uploaded>,
  "source": {{
    "emailAccount": "email",
    "emailUid": "uid",
    "emailSubject": "subject",
    "attachmentName": "filename"
  }},
  "emailsScanned": <count>,
  "message": "explanation"
}}

START SEARCHING NOW."""


@app.post("/api/invoice-find", response_model=InvoiceFindResponse)
async def find_invoice(request: InvoiceFindRequest):
    """Search emails for invoices using Claude SDK with MCP tools."""
    from datetime import datetime as dt, timedelta

    if not check_sdk():
        return InvoiceFindResponse(success=False, error="SDK not available")

    try:
        tx_date = dt.strptime(request.date, "%Y-%m-%d")
        date_start = (tx_date - timedelta(days=30)).strftime("%Y-%m-%d")
        date_end = (tx_date + timedelta(days=30)).strftime("%Y-%m-%d")

        prompt = INVOICE_FIND_PROMPT.format(
            vendor_name=request.vendorName,
            amount=request.amount,
            date=request.date,
            description=request.description or "",
            date_start=date_start,
            date_end=date_end
        )

        logger.info(f"[InvoiceFind] Searching for: {request.vendorName} {request.amount} EUR")

        result = await executor.run_prompt(
            prompt=prompt,
            tools=[
                "mcp__godaddy-mail__*",
                "mcp__microsoft-outlook__*",
                "Bash",
                "Read",
                "Write"
            ],
            max_turns=30,
            timeout_seconds=180
        )

        if not result.success:
            return InvoiceFindResponse(success=False, error=result.error)

        json_data = result.get_json()
        if not json_data:
            return InvoiceFindResponse(success=False, error="No valid JSON in response")

        return InvoiceFindResponse(
            success=True,
            found=json_data.get("found", False),
            invoiceId=json_data.get("invoiceId"),
            message=json_data.get("message"),
            source=json_data.get("source"),
            searchStrategy=json_data.get("searchStrategy"),
            emailsScanned=json_data.get("emailsScanned", 0)
        )

    except Exception as e:
        logger.error(f"[InvoiceFind] Error: {e}")
        return InvoiceFindResponse(success=False, error=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
