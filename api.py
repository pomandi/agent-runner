#!/usr/bin/env python3
"""
Agent Runner HTTP API
Simple API to run agents remotely without SSH
Enhanced with full conversation logging
NOW WITH CLAUDE AGENT SDK SUPPORT!
"""
import asyncio
import os
import subprocess
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn


# Claude Agent SDK
try:
    from claude_agent_sdk import query, ClaudeAgentOptions
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    logging.warning("claude-agent-sdk not installed, falling back to CLI")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner-api")


def get_file_type_from_url(url: str) -> str:
    """Determine file type from URL extension."""
    url_lower = url.lower()
    if any(ext in url_lower for ext in ['.jpg', '.jpeg']):
        return 'image/jpeg'
    elif '.png' in url_lower:
        return 'image/png'
    elif '.webp' in url_lower:
        return 'image/webp'
    elif '.gif' in url_lower:
        return 'image/gif'
    elif '.pdf' in url_lower:
        return 'application/pdf'
    else:
        return 'application/pdf'  # Default to PDF if unclear


def is_image_type(file_type: str) -> bool:
    """Check if the file type is an image."""
    return file_type.startswith('image/')


def detect_heic_format(file_content: bytes) -> bool:
    """
    Detect if file content is actually HEIC/HEIF format by checking magic bytes.
    iPhone often saves HEIC images with .jpg extension.
    """
    # HEIC/HEIF files have 'ftyp' box with specific brands
    # Check for 'ftyp' at byte 4-8 and HEIC brand patterns
    if len(file_content) < 12:
        return False

    # HEIF/HEIC starts with ftyp box
    if file_content[4:8] == b'ftyp':
        # Check for HEIC/HEIF brands
        brand = file_content[8:12]
        heic_brands = [b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1']
        if brand in heic_brands:
            return True

    return False


def convert_heic_to_jpeg(file_content: bytes) -> bytes:
    """
    Convert HEIC/HEIF image to JPEG format.
    Returns the converted JPEG bytes.
    """
    import io
    from PIL import Image

    try:
        # pillow-heif registers itself with Pillow automatically when imported
        import pillow_heif
        pillow_heif.register_heif_opener()

        # Open HEIC image
        img = Image.open(io.BytesIO(file_content))

        # Convert to RGB if necessary (HEIC might have alpha channel)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        # Save as JPEG
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=95)
        output.seek(0)

        return output.read()
    except Exception as e:
        logger.error(f"[HEIC] Failed to convert HEIC to JPEG: {e}")
        raise


app = FastAPI(
    title="Agent Runner API",
    description="Run Claude agents remotely with full conversation logging",
    version="2.2.0"
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
    "log_file": None
}

LOGS_DIR = Path("/app/logs")


class RunRequest(BaseModel):
    agent: Optional[str] = None  # Uses AGENT_NAME env if not provided
    task: Optional[str] = None   # Uses AGENT_TASK env if not provided
    allowed_tools: Optional[str] = None  # MCP tools pattern
    verbose: Optional[bool] = True  # Enable verbose logging
    use_sdk: Optional[bool] = True  # Use SDK (True) or CLI (False)


class RunResponse(BaseModel):
    status: str
    message: str
    run_id: Optional[str] = None
    agent: Optional[str] = None
    task: Optional[str] = None


def format_stream_message(msg: dict) -> str:
    """Format a stream-json message for human readable log."""
    msg_type = msg.get("type", "unknown")
    
    if msg_type == "assistant":
        content = msg.get("message", {}).get("content", [])
        text_parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif part.get("type") == "tool_use":
                    tool_name = part.get("name", "unknown")
                    tool_input = json.dumps(part.get("input", {}), indent=2)
                    text_parts.append(f"\n🔧 TOOL CALL: {tool_name}\n   Input: {tool_input}\n")
            elif isinstance(part, str):
                text_parts.append(part)
        return "\n".join(text_parts) if text_parts else ""
    
    elif msg_type == "user":
        content = msg.get("message", {}).get("content", [])
        for part in content:
            if isinstance(part, dict) and part.get("type") == "tool_result":
                tool_id = part.get("tool_use_id", "")[:8]
                result = part.get("content", "")
                if isinstance(result, list):
                    result = json.dumps(result, indent=2)
                elif isinstance(result, str) and len(result) > 500:
                    result = result[:500] + "... (truncated)"
                return f"\n📥 TOOL RESULT [{tool_id}...]:\n{result}\n"
        return ""
    
    elif msg_type == "result":
        # Final result
        cost = msg.get("cost_usd", 0)
        duration = msg.get("duration_ms", 0) / 1000
        return f"\n💰 Cost: ${cost:.4f} | ⏱️ Duration: {duration:.1f}s\n"
    
    return ""


def run_agent_sync(agent: str, task: str, allowed_tools: str, log_file: Path, verbose: bool = True):
    """Run agent in subprocess with detailed logging."""
    global current_run
    
    try:
        current_run["running"] = True
        current_run["agent"] = agent
        current_run["task"] = task
        current_run["started_at"] = datetime.now().isoformat()
        current_run["log_file"] = str(log_file)
        
        # Ensure MCP config is in place
        mcp_src = Path("/app/.mcp.json")
        mcp_dst = Path("/root/.claude/.mcp.json")
        if mcp_src.exists():
            mcp_dst.write_text(mcp_src.read_text())
        
        # Build command with verbose output
        cmd = [
            "claude",
            "--mcp-config", "/root/.claude/.mcp.json",
            "--allowedTools", allowed_tools,
            "--output-format", "stream-json",  # Full conversation in JSON
            "--verbose",  # Timing and stats
            task
        ]
        
        logger.info(f"Running: {' '.join(cmd)}")
        
        with open(log_file, "w") as f:
            f.write("=" * 60 + "\n")
            f.write("   AGENT RUN - FULL CONVERSATION LOG\n")
            f.write("=" * 60 + "\n")
            f.write(f"Agent: {agent}\n")
            f.write(f"Task: {task}\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"Allowed Tools: {allowed_tools}\n")
            f.write("=" * 60 + "\n\n")
            f.flush()
            
            # Run and capture stream-json output
            process = subprocess.Popen(
                cmd,
                cwd="/app",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            message_count = 0
            tool_calls = 0
            
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                # Try to parse as JSON
                try:
                    msg = json.loads(line)
                    formatted = format_stream_message(msg)
                    
                    if formatted:
                        message_count += 1
                        if "TOOL CALL" in formatted:
                            tool_calls += 1
                        f.write(formatted)
                        f.flush()
                    
                except json.JSONDecodeError:
                    # Plain text output
                    f.write(line + "\n")
                    f.flush()
            
            process.wait(timeout=300)
            return_code = process.returncode
            
            f.write("\n" + "=" * 60 + "\n")
            f.write("   RUN SUMMARY\n")
            f.write("=" * 60 + "\n")
            f.write(f"Exit code: {return_code}\n")
            f.write(f"Messages: {message_count}\n")
            f.write(f"Tool calls: {tool_calls}\n")
            f.write(f"Finished: {datetime.now().isoformat()}\n")
            f.write("=" * 60 + "\n")
        
        logger.info(f"Agent completed with code: {return_code}")
        
    except subprocess.TimeoutExpired:
        logger.error("Agent timed out")
        process.kill()
        with open(log_file, "a") as f:
            f.write(f"\n❌ ERROR: Agent timed out after 5 minutes\n")
    except Exception as e:
        logger.error(f"Agent error: {e}")
        with open(log_file, "a") as f:
            f.write(f"\n❌ ERROR: {str(e)}\n")
    finally:
        current_run["running"] = False


async def run_agent_sdk(agent: str, task: str, allowed_tools: str, log_file: Path):
    """Run agent using Claude Agent SDK (async, native Python)."""
    global current_run

    if not SDK_AVAILABLE:
        logger.error("SDK not available, cannot run")
        return

    try:
        current_run["running"] = True
        current_run["agent"] = agent
        current_run["task"] = task
        current_run["started_at"] = datetime.now().isoformat()
        current_run["log_file"] = str(log_file)
        current_run["mode"] = "sdk"

        # Parse allowed tools
        tools_list = [t.strip() for t in allowed_tools.split(",") if t.strip()]

        # Configure SDK options
        options = ClaudeAgentOptions(
            cwd=f"/app/agents/{agent}" if Path(f"/app/agents/{agent}").exists() else "/app",
            allowed_tools=tools_list,
            max_turns=50
        )

        logger.info(f"[SDK] Starting agent: {agent}")
        logger.info(f"[SDK] Task: {task}")
        logger.info(f"[SDK] Tools: {tools_list}")

        message_count = 0
        tool_calls = 0

        with open(log_file, "w") as f:
            f.write("=" * 60 + "\n")
            f.write("   AGENT RUN - SDK MODE\n")
            f.write("=" * 60 + "\n")
            f.write(f"Agent: {agent}\n")
            f.write(f"Task: {task}\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"Mode: SDK (claude-agent-sdk)\n")
            f.write(f"Allowed Tools: {allowed_tools}\n")
            f.write("=" * 60 + "\n\n")
            f.flush()

            # Run with SDK - native async iteration
            async for message in query(prompt=task, options=options):
                message_count += 1

                # Handle different message types
                if hasattr(message, 'content'):
                    for block in message.content:
                        if hasattr(block, 'text'):
                            f.write(f"\n📝 ASSISTANT:\n{block.text}\n")
                            f.flush()
                        elif hasattr(block, 'type') and block.type == 'tool_use':
                            tool_calls += 1
                            tool_name = getattr(block, 'name', 'unknown')
                            tool_input = getattr(block, 'input', {})
                            f.write(f"\n🔧 TOOL CALL: {tool_name}\n")
                            f.write(f"   Input: {json.dumps(tool_input, indent=2)}\n")
                            f.flush()
                        elif hasattr(block, 'type') and block.type == 'tool_result':
                            result = getattr(block, 'content', '')
                            if isinstance(result, str) and len(result) > 500:
                                result = result[:500] + "... (truncated)"
                            f.write(f"\n📥 TOOL RESULT:\n{result}\n")
                            f.flush()

                # Log progress
                if message_count % 5 == 0:
                    logger.info(f"[SDK] Progress: {message_count} messages, {tool_calls} tool calls")

            f.write("\n" + "=" * 60 + "\n")
            f.write("   RUN SUMMARY\n")
            f.write("=" * 60 + "\n")
            f.write(f"Mode: SDK\n")
            f.write(f"Messages: {message_count}\n")
            f.write(f"Tool calls: {tool_calls}\n")
            f.write(f"Finished: {datetime.now().isoformat()}\n")
            f.write("=" * 60 + "\n")

        logger.info(f"[SDK] Agent completed: {message_count} messages, {tool_calls} tool calls")

    except Exception as e:
        logger.error(f"[SDK] Agent error: {e}")
        with open(log_file, "a") as f:
            f.write(f"\n❌ ERROR: {str(e)}\n")
            import traceback
            f.write(f"\n{traceback.format_exc()}\n")
    finally:
        current_run["running"] = False


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/status")
async def status():
    """Get current agent status."""
    creds_exist = Path("/root/.claude/.credentials.json").exists()

    return {
        "container": "agent-runner",
        "version": "3.0.0",
        "agent_name": os.getenv("AGENT_NAME", "unknown"),
        "schedule": os.getenv("AGENT_SCHEDULE", "none"),
        "credentials_found": creds_exist,
        "sdk_available": SDK_AVAILABLE,
        "default_mode": "sdk" if SDK_AVAILABLE else "cli",
        "current_run": current_run,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest, background_tasks: BackgroundTasks):
    """Run an agent with full conversation logging.

    Supports two modes:
    - SDK mode (default): Uses claude-agent-sdk for native Python async
    - CLI mode: Uses subprocess to call claude CLI (fallback)

    Set use_sdk=false to use CLI mode.
    """

    if current_run["running"]:
        raise HTTPException(
            status_code=409,
            detail=f"Agent already running: {current_run['agent']}"
        )

    # Check credentials
    if not Path("/root/.claude/.credentials.json").exists():
        raise HTTPException(
            status_code=503,
            detail="Claude credentials not found. Copy credentials first."
        )

    agent = request.agent or os.getenv("AGENT_NAME", "feed-publisher")
    task = request.task or os.getenv("AGENT_TASK", "Run the agent task")
    verbose = request.verbose if request.verbose is not None else True
    use_sdk = request.use_sdk if request.use_sdk is not None else True

    # Determine allowed tools
    if request.allowed_tools:
        allowed_tools = request.allowed_tools
    elif agent == "feed-publisher":
        # Include visual-content-mcp for image editing (price banners, text overlays, effects)
        allowed_tools = "mcp__feed-publisher-mcp__*,mcp__visual-content-mcp__*,mcp__social-media-publish__*"
    else:
        allowed_tools = "*"

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = LOGS_DIR / f"{agent}-{run_id}.log"

    # Choose execution mode
    if use_sdk and SDK_AVAILABLE:
        # SDK Mode - async, native Python
        asyncio.create_task(run_agent_sdk(agent, task, allowed_tools, log_file))
        mode = "sdk"
    else:
        # CLI Mode - subprocess fallback
        background_tasks.add_task(run_agent_sync, agent, task, allowed_tools, log_file, verbose)
        mode = "cli"

    return RunResponse(
        status="started",
        message=f"Agent {agent} started in {mode.upper()} mode",
        run_id=run_id,
        agent=agent,
        task=task
    )


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
    """Get the most recent log file - ONE URL to see everything!
    
    Shows:
    - Agent thinking and decisions
    - 🔧 TOOL CALL with inputs
    - 📥 TOOL RESULT with outputs
    - 💰 Cost and duration
    
    Args:
        tail: Number of lines from end (0 = all)
    """
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
    """Get content of a specific log file.
    
    Args:
        filename: Log file name
        tail: Number of lines from end (0 = all)
    """
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


@app.delete("/logs/{filename}")
async def delete_log(filename: str):
    """Delete a log file."""
    log_file = LOGS_DIR / filename
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    log_file.unlink()
    return {"status": "deleted", "file": filename}


# Invoice Matching Endpoint - Proxy for expense-tracker
class InvoiceMatchRequest(BaseModel):
    transaction: dict  # Transaction details
    invoices: list     # List of unmatched invoices


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
1. AMOUNT: The transaction amount and invoice amount MUST match within 1% tolerance. This is the most important criterion.
2. VENDOR: If the transaction has a vendor name, it should match or be similar to the invoice vendor.
3. DATE: The invoice date should be within 30 days of the transaction date (before or after).
4. NEVER match if amounts differ by more than 5% - this is a hard rule.

SCORING:
- Exact amount match: Very high confidence
- Amount within 1%: High confidence
- Amount within 5%: Medium confidence (needs review)
- Amount differs >5%: NO MATCH

OUTPUT FORMAT - You must respond with valid JSON only:
{{
  "matched": true or false,
  "invoiceId": number or null,
  "confidence": number between 0 and 1,
  "reasoning": "brief explanation of why this match was selected or why no match was found",
  "amountDifference": number (percentage difference),
  "warnings": ["any concerns about this match"]
}}

If no suitable match exists, set matched to false and invoiceId to null.
Be conservative - it's better to miss a match than to create a wrong one.

TRANSACTION TO MATCH:
{transaction_json}

AVAILABLE UNMATCHED INVOICES:
{invoices_json}

Analyze and respond with JSON only."""


@app.post("/api/invoice-match", response_model=InvoiceMatchResponse)
async def match_invoice(request: InvoiceMatchRequest):
    """Match a transaction with invoices using Claude AI.

    This endpoint acts as a proxy for expense-tracker-app,
    using Claude Max subscription via CLI.
    """
    try:
        # Build prompt
        transaction_json = json.dumps(request.transaction, indent=2)
        invoices_json = json.dumps(request.invoices, indent=2)

        prompt = INVOICE_MATCH_PROMPT.format(
            transaction_json=transaction_json,
            invoices_json=invoices_json
        )

        # Call Claude CLI - pass prompt via stdin to avoid command line length limits
        cmd = [
            "claude",
            "--print",  # Just print response, no interactive mode
            "-p", prompt  # Pass prompt with -p flag
        ]

        logger.info(f"[InvoiceMatch] Processing transaction {request.transaction.get('id')}")
        logger.info(f"[InvoiceMatch] Prompt length: {len(prompt)} chars")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd="/app"
        )

        if result.returncode != 0:
            logger.error(f"[InvoiceMatch] CLI returncode: {result.returncode}")
            logger.error(f"[InvoiceMatch] CLI stderr: {result.stderr}")
            logger.error(f"[InvoiceMatch] CLI stdout: {result.stdout[:500] if result.stdout else 'empty'}")
            return InvoiceMatchResponse(
                success=False,
                error=f"Claude CLI error (rc={result.returncode}): {result.stderr[:100] or result.stdout[:100]}"
            )

        response_text = result.stdout.strip()
        logger.info(f"[InvoiceMatch] Response length: {len(response_text)}")
        logger.debug(f"[InvoiceMatch] Raw response: {response_text[:500]}")

        # Parse JSON from response
        json_match = None
        try:
            # Try to find JSON in response - look for the first { to the last }
            import re
            # Find all potential JSON objects
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                # Clean up the JSON string - remove any control characters
                json_str = json_str.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                # Remove extra whitespace
                json_str = ' '.join(json_str.split())
                logger.info(f"[InvoiceMatch] Extracted JSON: {json_str[:200]}")
                json_match = json.loads(json_str)
            else:
                logger.error(f"[InvoiceMatch] No JSON braces found in response")
        except json.JSONDecodeError as e:
            logger.error(f"[InvoiceMatch] JSON parse error: {e}")
            logger.error(f"[InvoiceMatch] JSON string was: {json_str[:200] if 'json_str' in dir() else 'N/A'}")
            return InvoiceMatchResponse(
                success=False,
                error=f"Failed to parse response: {str(e)}"
            )

        if not json_match:
            return InvoiceMatchResponse(
                success=False,
                error="No valid JSON in response"
            )

        return InvoiceMatchResponse(
            success=True,
            matched=json_match.get("matched", False),
            invoiceId=json_match.get("invoiceId"),
            confidence=json_match.get("confidence", 0),
            reasoning=json_match.get("reasoning", ""),
            warnings=json_match.get("warnings", [])
        )

    except subprocess.TimeoutExpired:
        logger.error("[InvoiceMatch] Timeout")
        return InvoiceMatchResponse(
            success=False,
            error="Request timed out"
        )
    except Exception as e:
        logger.error(f"[InvoiceMatch] Error: {e}")
        return InvoiceMatchResponse(
            success=False,
            error=str(e)
        )


# Invoice Extraction Endpoint - Extract data from PDF invoices
class InvoiceExtractRequest(BaseModel):
    pdf_url: str  # URL to the PDF file (Cloudflare R2)
    invoice_id: Optional[int] = None  # Optional invoice ID for logging


class InvoiceExtractResponse(BaseModel):
    success: bool
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None  # YYYY-MM-DD format
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


INVOICE_EXTRACT_PROMPT = """You are an expert invoice data extractor for a Belgian company's expense tracking system.

Analyze the provided invoice document and extract all relevant information.

EXTRACTION RULES:
1. AMOUNTS: Extract exact amounts including decimals. Look for:
   - Total amount (incl. VAT) - this is the most important
   - Subtotal (excl. VAT)
   - VAT amount
   - VAT rate (usually 21%, 6%, or 0% in Belgium)

2. DATES: Extract invoice date in YYYY-MM-DD format

3. INVOICE NUMBER: Look for "Invoice", "Facture", "Factuur", "Invoice No", "Factuurnummer", etc.

4. VENDOR INFO:
   - Company name
   - Address
   - VAT number (BTW-nummer, TVA, VAT)

5. LINE ITEMS: If visible, extract individual items with description and amount

6. CURRENCY DETECTION - CRITICAL:
   Always detect the ACTUAL currency used in the invoice. Look for:
   - Currency symbols: € (EUR), $ (USD), £ (GBP), ¥ (CNY/JPY), ₺ (TRY), ₹ (INR), ₽ (RUB), ₩ (KRW), CHF
   - Currency codes: EUR, USD, GBP, CNY, JPY, TRY, CHF, AUD, CAD, etc.
   - Text indicators: "Chinese Yuan", "US Dollar", "British Pound", etc.
   - Country context: Chinese company = likely CNY, US company = likely USD

   COMMON CURRENCY CODES:
   - EUR = Euro (€)
   - USD = US Dollar ($)
   - GBP = British Pound (£)
   - CNY = Chinese Yuan/Renminbi (¥ or RMB)
   - JPY = Japanese Yen (¥)
   - CHF = Swiss Franc
   - TRY = Turkish Lira (₺)
   - INR = Indian Rupee (₹)
   - AED = UAE Dirham
   - SGD = Singapore Dollar

   DO NOT assume EUR by default! Only use EUR if you see € symbol or "EUR" text.

OUTPUT FORMAT - Respond with valid JSON only:
{{
  "invoice_number": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "total_amount": number or null,
  "subtotal": number or null,
  "vat_amount": number or null,
  "vat_rate": number or null (e.g., 21 for 21%),
  "vendor_name": "string or null",
  "vendor_address": "string or null",
  "vendor_vat_number": "string or null",
  "currency": "3-letter ISO code (e.g., EUR, USD, CNY, GBP, TRY, JPY, CHF)",
  "line_items": [
    {{"description": "string", "quantity": number, "unit_price": number, "total": number}}
  ],
  "raw_text": "brief summary of key visible text"
}}

Be precise with numbers - financial accuracy is critical.
If a value cannot be determined with confidence, set it to null.
ALWAYS specify the correct currency - this is critical for accounting!"""


@app.post("/api/invoice-extract", response_model=InvoiceExtractResponse)
async def extract_invoice(request: InvoiceExtractRequest):
    """Extract data from an invoice PDF or IMAGE using Claude AI.

    This endpoint:
    1. Downloads the file from the provided URL
    2. Detects file type (PDF or image)
    3. For PDFs: Extracts text using pypdf, sends to Claude CLI
    4. For Images: Uses Anthropic SDK with vision capability
    5. Returns structured invoice data
    """
    import httpx
    from io import BytesIO

    try:
        file_url = request.pdf_url
        file_type = get_file_type_from_url(file_url)
        is_image = is_image_type(file_type)

        logger.info(f"[InvoiceExtract] Processing file: {file_url}")
        logger.info(f"[InvoiceExtract] Detected type: {file_type}, is_image: {is_image}")

        # Download the file
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(file_url)
            if response.status_code != 200:
                return InvoiceExtractResponse(
                    success=False,
                    error=f"Failed to download file: HTTP {response.status_code}"
                )
            file_content = response.content

            # Also check content-type header
            content_type = response.headers.get('content-type', '').lower()
            if 'image' in content_type:
                is_image = True
                file_type = content_type.split(';')[0].strip()
                logger.info(f"[InvoiceExtract] Content-Type header indicates image: {file_type}")

        logger.info(f"[InvoiceExtract] Downloaded: {len(file_content)} bytes")

        if is_image:
            # ============ IMAGE EXTRACTION (Using Claude CLI with Read tool) ============
            import tempfile

            logger.info(f"[InvoiceExtract] Processing as IMAGE with Claude CLI")

            # Check if the image is actually HEIC (iPhone often saves HEIC as .jpg)
            if detect_heic_format(file_content):
                logger.info(f"[InvoiceExtract] Detected HEIC format (iPhone image), converting to JPEG...")
                try:
                    file_content = convert_heic_to_jpeg(file_content)
                    file_type = 'image/jpeg'
                    logger.info(f"[InvoiceExtract] HEIC converted to JPEG: {len(file_content)} bytes")
                except Exception as heic_error:
                    logger.error(f"[InvoiceExtract] HEIC conversion failed: {heic_error}")
                    return InvoiceExtractResponse(
                        success=False,
                        error=f"Failed to convert HEIC image: {str(heic_error)}"
                    )

            # Determine file extension
            if 'jpeg' in file_type or 'jpg' in file_type:
                ext = '.jpg'
            elif 'png' in file_type:
                ext = '.png'
            elif 'webp' in file_type:
                ext = '.webp'
            elif 'gif' in file_type:
                ext = '.gif'
            else:
                ext = '.jpg'  # Default

            # Save image to temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir='/tmp') as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name

            logger.info(f"[InvoiceExtract] Saved image to: {tmp_path}")

            # Build prompt - Claude CLI will use Read tool to view the image
            image_prompt = f"""Read and analyze the invoice image at this path: {tmp_path}

{INVOICE_EXTRACT_PROMPT}

IMPORTANT: First read the image file using the Read tool, then analyze it and respond with JSON only."""

            # Call Claude CLI - it will use its Read tool to view the image
            cmd = [
                "claude",
                "--print",
                "--allowedTools", "Read",
                "-p", image_prompt
            ]

            logger.info(f"[InvoiceExtract] Running Claude CLI for image: {tmp_path}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd="/app"
                )

                response_text = result.stdout.strip()
                logger.info(f"[InvoiceExtract] CLI returncode: {result.returncode}")
                logger.info(f"[InvoiceExtract] Response length: {len(response_text)}")
                if response_text:
                    logger.info(f"[InvoiceExtract] Response (first 500): {response_text[:500]}")

                if result.returncode != 0:
                    logger.error(f"[InvoiceExtract] CLI stderr: {result.stderr}")
                    return InvoiceExtractResponse(
                        success=False,
                        error=f"Claude CLI error: {result.stderr[:200] or result.stdout[:200]}"
                    )
            finally:
                # Clean up temp file
                import os
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    logger.info(f"[InvoiceExtract] Cleaned up temp file: {tmp_path}")

        else:
            # ============ PDF EXTRACTION (Using pypdf + Claude CLI) ============
            logger.info(f"[InvoiceExtract] Processing as PDF")

            # Extract text from PDF using pypdf
            try:
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(file_content))
                pdf_text = ""
                for page_num, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    if page_text:
                        pdf_text += f"\n--- Page {page_num + 1} ---\n{page_text}"

                logger.info(f"[InvoiceExtract] Extracted {len(pdf_text)} chars from {len(reader.pages)} pages")

                if not pdf_text.strip():
                    return InvoiceExtractResponse(
                        success=False,
                        error="PDF contains no extractable text (may be image-based)"
                    )
            except Exception as e:
                logger.error(f"[InvoiceExtract] PDF extraction error: {e}")
                return InvoiceExtractResponse(
                    success=False,
                    error=f"PDF text extraction failed: {str(e)}"
                )

            # Build prompt with extracted text
            full_prompt = f"""Here is the text extracted from an invoice PDF. Please analyze it and extract structured data.

EXTRACTED PDF TEXT:
{pdf_text[:8000]}

{INVOICE_EXTRACT_PROMPT}

Respond with JSON only."""

            # Call Claude CLI with the text prompt
            cmd = [
                "claude",
                "--print",
                "-p", full_prompt
            ]

            logger.info(f"[InvoiceExtract] Running Claude CLI with {len(full_prompt)} char prompt")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                cwd="/app"
            )

            # Log the raw response for debugging
            logger.info(f"[InvoiceExtract] CLI returncode: {result.returncode}")
            if result.stdout:
                logger.info(f"[InvoiceExtract] Raw stdout (first 500): {result.stdout[:500]}")
            if result.stderr:
                logger.info(f"[InvoiceExtract] Raw stderr: {result.stderr[:200]}")

            if result.returncode != 0:
                logger.error(f"[InvoiceExtract] CLI returncode: {result.returncode}")
                logger.error(f"[InvoiceExtract] CLI stderr: {result.stderr}")
                logger.error(f"[InvoiceExtract] CLI stdout: {result.stdout[:500] if result.stdout else 'empty'}")
                return InvoiceExtractResponse(
                    success=False,
                    error=f"Claude CLI error (rc={result.returncode}): {result.stderr[:200] or result.stdout[:200]}"
                )

            response_text = result.stdout.strip()
            logger.info(f"[InvoiceExtract] Response length: {len(response_text)}")

        # ============ PARSE JSON RESPONSE ============
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                extracted = json.loads(json_str)
            else:
                return InvoiceExtractResponse(
                    success=False,
                    error=f"No valid JSON in response. Response was: {response_text[:300]}"
                )
        except json.JSONDecodeError as e:
            logger.error(f"[InvoiceExtract] JSON parse error: {e}")
            return InvoiceExtractResponse(
                success=False,
                error=f"Failed to parse response: {str(e)}"
            )

        return InvoiceExtractResponse(
            success=True,
            invoice_number=extracted.get("invoice_number"),
            invoice_date=extracted.get("invoice_date"),
            total_amount=extracted.get("total_amount"),
            subtotal=extracted.get("subtotal"),
            vat_amount=extracted.get("vat_amount"),
            vat_rate=extracted.get("vat_rate"),
            vendor_name=extracted.get("vendor_name"),
            vendor_address=extracted.get("vendor_address"),
            vendor_vat_number=extracted.get("vendor_vat_number"),
            currency=extracted.get("currency", "EUR"),
            line_items=extracted.get("line_items", []),
            raw_text=extracted.get("raw_text")
        )

    except httpx.TimeoutException:
        logger.error("[InvoiceExtract] Download timeout")
        return InvoiceExtractResponse(
            success=False,
            error="File download timed out"
        )
    except subprocess.TimeoutExpired:
        logger.error("[InvoiceExtract] Claude timeout")
        return InvoiceExtractResponse(
            success=False,
            error="File processing timed out"
        )
    except Exception as e:
        logger.error(f"[InvoiceExtract] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return InvoiceExtractResponse(
            success=False,
            error=str(e)
        )


# ============================================================
# Credit Card Statement Extraction
# ============================================================

class CCStatementExtractRequest(BaseModel):
    pdf_url: str  # URL to the PDF file (Cloudflare R2)
    statement_id: Optional[int] = None  # Optional statement ID for logging


class CCStatementTransaction(BaseModel):
    transaction_date: str
    posting_date: Optional[str] = None
    description: str
    merchant_name: Optional[str] = None
    amount: float
    currency: str = "EUR"
    original_amount: Optional[float] = None
    original_currency: Optional[str] = None
    transaction_type: str  # purchase, refund, fee, interest, payment


class CCStatementExtractResponse(BaseModel):
    success: bool
    statement_period: Optional[str] = None  # YYYY-MM
    statement_date: Optional[str] = None  # YYYY-MM-DD
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
    last_four_digits: Optional[str] = None
    error: Optional[str] = None


CC_STATEMENT_EXTRACT_PROMPT = """You are a credit card statement parser. Analyze the provided credit card statement and extract all relevant information.

Return a JSON object with the following structure:
{{
  "success": true,
  "statement_period": "YYYY-MM",
  "statement_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD or null",
  "opening_balance": number or null,
  "total_purchases": number (sum of all purchases),
  "total_payments": number (sum of payments received),
  "total_fees": number (interest, fees, etc.),
  "closing_balance": number (amount owed at end of period),
  "minimum_payment": number or null,
  "currency": "EUR" or "USD" etc,
  "card_holder_name": "string or null",
  "bank_name": "string",
  "last_four_digits": "1234",
  "transactions": [
    {{
      "transaction_date": "YYYY-MM-DD",
      "posting_date": "YYYY-MM-DD or null",
      "description": "Transaction description",
      "merchant_name": "Merchant name if identifiable",
      "amount": number (positive for purchases/fees, negative for refunds),
      "currency": "EUR",
      "original_amount": number or null (if foreign currency),
      "original_currency": "USD" or null,
      "transaction_type": "purchase" | "refund" | "fee" | "interest" | "payment"
    }}
  ]
}}

Important parsing rules:
1. All amounts should be numbers (not strings)
2. Dates should be in YYYY-MM-DD format
3. For purchases: amount should be POSITIVE
4. For refunds: amount should be NEGATIVE
5. For payments received: transaction_type should be "payment"
6. Include ALL transactions listed on the statement
7. Try to identify merchant names from descriptions
8. If the statement is in a language other than English, still parse dates in YYYY-MM-DD format
9. statement_period should be derived from the statement date (YYYY-MM format)

If you cannot parse the statement, return:
{{
  "success": false,
  "error": "Description of what went wrong"
}}

Return ONLY the JSON object, no other text."""


@app.post("/api/cc-statement-extract", response_model=CCStatementExtractResponse)
async def extract_cc_statement(request: CCStatementExtractRequest):
    """Extract data from a credit card statement PDF using Claude AI.

    This endpoint:
    1. Downloads the PDF from the provided URL (Cloudflare R2)
    2. Extracts text using pypdf
    3. Uses Claude CLI to parse the statement
    4. Returns structured statement data with transactions
    """
    import httpx
    from io import BytesIO

    try:
        file_url = request.pdf_url
        logger.info(f"[CCStatementExtract] Processing file: {file_url}")
        logger.info(f"[CCStatementExtract] Statement ID: {request.statement_id}")

        # Download the file
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(file_url)
            if response.status_code != 200:
                return CCStatementExtractResponse(
                    success=False,
                    error=f"Failed to download file: HTTP {response.status_code}"
                )
            file_content = response.content

        logger.info(f"[CCStatementExtract] Downloaded: {len(file_content)} bytes")

        # Extract text from PDF using pypdf
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(file_content))
            pdf_text = ""
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    pdf_text += f"\n--- Page {page_num + 1} ---\n{page_text}"

            logger.info(f"[CCStatementExtract] Extracted {len(pdf_text)} chars from {len(reader.pages)} pages")

            if not pdf_text.strip():
                # Try image-based extraction with Claude CLI Read tool
                logger.info("[CCStatementExtract] PDF has no text, trying image-based extraction")
                import tempfile

                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False, dir='/tmp') as tmp_file:
                    tmp_file.write(file_content)
                    tmp_path = tmp_file.name

                image_prompt = f"""Read and analyze the credit card statement PDF at this path: {tmp_path}

{CC_STATEMENT_EXTRACT_PROMPT}

IMPORTANT: First read the PDF file using the Read tool, then analyze it and respond with JSON only."""

                cmd = [
                    "claude",
                    "--print",
                    "--allowedTools", "Read",
                    "-p", image_prompt
                ]

                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        cwd="/app"
                    )
                    response_text = result.stdout.strip()
                finally:
                    import os
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

                if result.returncode != 0:
                    return CCStatementExtractResponse(
                        success=False,
                        error=f"Claude CLI error: {result.stderr[:200] or result.stdout[:200]}"
                    )
            else:
                # Text-based extraction
                full_prompt = f"""Here is the text extracted from a credit card statement PDF. Please analyze it and extract structured data.

EXTRACTED PDF TEXT:
{pdf_text[:12000]}

{CC_STATEMENT_EXTRACT_PROMPT}

Respond with JSON only."""

                cmd = [
                    "claude",
                    "--print",
                    "-p", full_prompt
                ]

                logger.info(f"[CCStatementExtract] Running Claude CLI with {len(full_prompt)} char prompt")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd="/app"
                )

                if result.returncode != 0:
                    logger.error(f"[CCStatementExtract] CLI error: {result.stderr}")
                    return CCStatementExtractResponse(
                        success=False,
                        error=f"Claude CLI error (rc={result.returncode}): {result.stderr[:200] or result.stdout[:200]}"
                    )

                response_text = result.stdout.strip()

        except Exception as e:
            logger.error(f"[CCStatementExtract] PDF extraction error: {e}")
            return CCStatementExtractResponse(
                success=False,
                error=f"PDF processing failed: {str(e)}"
            )

        logger.info(f"[CCStatementExtract] Response length: {len(response_text)}")

        # Parse JSON from response
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                extracted = json.loads(json_str)
            else:
                return CCStatementExtractResponse(
                    success=False,
                    error=f"No valid JSON in response. Response was: {response_text[:300]}"
                )
        except json.JSONDecodeError as e:
            logger.error(f"[CCStatementExtract] JSON parse error: {e}")
            return CCStatementExtractResponse(
                success=False,
                error=f"Failed to parse response: {str(e)}"
            )

        # Check if extraction was successful
        if not extracted.get("success", False):
            return CCStatementExtractResponse(
                success=False,
                error=extracted.get("error", "Unknown extraction error")
            )

        return CCStatementExtractResponse(
            success=True,
            statement_period=extracted.get("statement_period"),
            statement_date=extracted.get("statement_date"),
            due_date=extracted.get("due_date"),
            opening_balance=extracted.get("opening_balance"),
            total_purchases=extracted.get("total_purchases"),
            total_payments=extracted.get("total_payments"),
            total_fees=extracted.get("total_fees"),
            closing_balance=extracted.get("closing_balance"),
            minimum_payment=extracted.get("minimum_payment"),
            currency=extracted.get("currency", "EUR"),
            transactions=extracted.get("transactions", []),
            card_holder_name=extracted.get("card_holder_name"),
            bank_name=extracted.get("bank_name"),
            last_four_digits=extracted.get("last_four_digits")
        )

    except httpx.TimeoutException:
        logger.error("[CCStatementExtract] Download timeout")
        return CCStatementExtractResponse(
            success=False,
            error="File download timed out"
        )
    except subprocess.TimeoutExpired:
        logger.error("[CCStatementExtract] Claude timeout")
        return CCStatementExtractResponse(
            success=False,
            error="Statement processing timed out"
        )
    except Exception as e:
        logger.error(f"[CCStatementExtract] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return CCStatementExtractResponse(
            success=False,
            error=str(e)
        )


# ============================================================
# Invoice Find from Email - Search emails for invoices
# ============================================================

class InvoiceFindRequest(BaseModel):
    transactionId: Optional[int] = None
    vendorName: str
    amount: float
    date: str  # YYYY-MM-DD
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


INVOICE_FIND_PROMPT = """You are an invoice finder agent. Your task is to search emails to find an invoice matching these transaction details:

TRANSACTION DETAILS:
- Vendor: {vendor_name}
- Amount: {amount} EUR
- Date: {date}
- Description: {description}
- Counterparty: {counterparty}

SEARCH STRATEGY:
1. First, search GoDaddy mail (info@pomandi.com) using mcp__godaddy-mail__search_emails
   - Search by vendor name in subject or sender
   - Date range: {date_start} to {date_end} (30 days before/after transaction)

2. For each email with attachments:
   - Use mcp__godaddy-mail__get_attachments to check for PDF files
   - If found, use mcp__godaddy-mail__download_attachment to save it

3. Upload found invoice to expense-tracker:
   - Save file to /tmp/invoices/
   - Use Bash to curl POST to https://fin.pomandi.com/api/invoices/upload

4. If Microsoft Outlook is configured, also search there using mcp__microsoft-outlook__search_emails

IMPORTANT:
- Look for PDF or image attachments (invoice files)
- Check if amount appears in email body
- Match vendor name or email domain

RESPOND WITH JSON:
{{
  "found": true/false,
  "invoiceUploaded": true/false,
  "invoiceId": <id if uploaded>,
  "source": {{
    "emailAccount": "info@pomandi.com",
    "emailUid": "<uid>",
    "emailSubject": "<subject>",
    "emailFrom": "<sender>",
    "emailDate": "<date>",
    "attachmentName": "<filename>"
  }},
  "searchStrategy": "vendor_sender_pattern",
  "emailsScanned": <count>,
  "message": "<explanation>"
}}

If not found:
{{
  "found": false,
  "emailsScanned": <count>,
  "message": "No matching invoice found",
  "searchedAccounts": ["info@pomandi.com"]
}}

START SEARCHING NOW."""


@app.post("/api/invoice-find", response_model=InvoiceFindResponse)
async def find_invoice_from_email(request: InvoiceFindRequest):
    """Search emails to find an invoice matching transaction details.

    Uses GoDaddy IMAP and Microsoft Outlook MCP tools to search emails,
    download attachments, and upload found invoices.
    """
    from datetime import datetime, timedelta

    try:
        # Calculate date range (30 days before/after transaction)
        tx_date = datetime.strptime(request.date, "%Y-%m-%d")
        date_start = (tx_date - timedelta(days=30)).strftime("%Y-%m-%d")
        date_end = (tx_date + timedelta(days=30)).strftime("%Y-%m-%d")

        # Build the prompt
        prompt = INVOICE_FIND_PROMPT.format(
            vendor_name=request.vendorName,
            amount=request.amount,
            date=request.date,
            description=request.description or "",
            counterparty=request.counterpartyName or "",
            date_start=date_start,
            date_end=date_end
        )

        logger.info(f"[InvoiceFind] Searching for: {request.vendorName} {request.amount} EUR on {request.date}")

        # Ensure tmp directory exists
        import os
        os.makedirs("/tmp/invoices", exist_ok=True)

        # Run Claude CLI with MCP tools for email access
        cmd = [
            "claude",
            "--print",
            "--mcp-config", "/app/.mcp.json",
            "--allowedTools", "mcp__godaddy-mail__*,mcp__microsoft-outlook__*,Bash,Read,Write",
            "-p", prompt
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes timeout for email search
            cwd="/app"
        )

        if result.returncode != 0:
            logger.error(f"[InvoiceFind] CLI error: {result.stderr[:500]}")
            return InvoiceFindResponse(
                success=False,
                error=f"Agent error: {result.stderr[:200]}"
            )

        response_text = result.stdout.strip()
        logger.info(f"[InvoiceFind] Response length: {len(response_text)}")

        # Parse JSON from response
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                json_result = json.loads(json_str)

                return InvoiceFindResponse(
                    success=True,
                    found=json_result.get("found", False),
                    invoiceId=json_result.get("invoiceId"),
                    message=json_result.get("message"),
                    source=json_result.get("source"),
                    searchStrategy=json_result.get("searchStrategy"),
                    emailsScanned=json_result.get("emailsScanned", 0)
                )
            else:
                logger.error(f"[InvoiceFind] No JSON in response: {response_text[:500]}")
                return InvoiceFindResponse(
                    success=False,
                    error="No valid JSON in agent response"
                )

        except json.JSONDecodeError as e:
            logger.error(f"[InvoiceFind] JSON parse error: {e}")
            return InvoiceFindResponse(
                success=False,
                error=f"Failed to parse agent response: {str(e)}"
            )

    except subprocess.TimeoutExpired:
        logger.error("[InvoiceFind] Agent timeout")
        return InvoiceFindResponse(
            success=False,
            error="Email search timed out (3 min limit)"
        )
    except Exception as e:
        logger.error(f"[InvoiceFind] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return InvoiceFindResponse(
            success=False,
            error=str(e)
        )


# ============================================================
# Invoice Pre-fetch Endpoints
# ============================================================

class PrefetchTriggerRequest(BaseModel):
    days_back: int = 30
    triggered_by: str = "manual"
    email_accounts: Optional[list] = None  # ["godaddy", "outlook"] default both


class PrefetchRunResponse(BaseModel):
    run_id: int
    status: str
    emails_scanned: int = 0
    attachments_found: int = 0
    invoices_created: int = 0
    duplicates_skipped: int = 0
    errors_count: int = 0
    error_details: list = []
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    triggered_by: str = "manual"


# Track current prefetch run
current_prefetch = {
    "running": False,
    "run_id": None
}


def run_prefetch_background(days_back: int, triggered_by: str, email_accounts: list):
    """Run prefetch in background thread."""
    global current_prefetch
    try:
        current_prefetch["running"] = True

        # Import here to avoid circular import
        from invoice_prefetch import run_prefetch as do_prefetch

        result = do_prefetch(
            days_back=days_back,
            triggered_by=triggered_by,
            email_accounts=email_accounts
        )

        current_prefetch["run_id"] = result.id
        logger.info(f"[Prefetch] Completed run {result.id}: {result.invoices_created} invoices created")

    except Exception as e:
        logger.error(f"[Prefetch] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        current_prefetch["running"] = False


@app.post("/api/invoices/prefetch/trigger")
async def trigger_prefetch(request: PrefetchTriggerRequest, background_tasks: BackgroundTasks):
    """
    Trigger invoice pre-fetch from emails.

    Scans GoDaddy and/or Outlook emails for invoice attachments,
    extracts metadata, uploads to R2, and saves to database.
    """
    if current_prefetch["running"]:
        raise HTTPException(
            status_code=409,
            detail="Prefetch already running"
        )

    email_accounts = request.email_accounts or ["godaddy", "outlook"]

    logger.info(f"[Prefetch] Starting: days_back={request.days_back}, accounts={email_accounts}")

    # Start in background
    background_tasks.add_task(
        run_prefetch_background,
        request.days_back,
        request.triggered_by,
        email_accounts
    )

    return {
        "status": "started",
        "message": f"Prefetch started for accounts: {', '.join(email_accounts)}",
        "days_back": request.days_back
    }


@app.get("/api/invoices/prefetch/status/{run_id}", response_model=PrefetchRunResponse)
async def get_prefetch_status(run_id: int):
    """Get status of a specific prefetch run."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    db_url = os.environ.get(
        "EXPENSE_TRACKER_DB_URL",
        "postgres://postgres:4mXro2JijzR56SARkdGseBpUCw0M1JtdJMT5JbsRUbFPtcGmgnTd4eAEC4hdrEWP@46.224.117.155:5434/expense_tracker"
    )

    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM prefetch_runs WHERE id = %s
            """, (run_id,))
            row = cur.fetchone()

        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Run not found")

        return PrefetchRunResponse(
            run_id=row["id"],
            status=row["status"],
            emails_scanned=row["emails_scanned"] or 0,
            attachments_found=row["attachments_found"] or 0,
            invoices_created=row["invoices_created"] or 0,
            duplicates_skipped=row["duplicates_skipped"] or 0,
            errors_count=row["errors_count"] or 0,
            error_details=row["error_details"] or [],
            started_at=row["started_at"].isoformat() if row["started_at"] else None,
            completed_at=row["completed_at"].isoformat() if row["completed_at"] else None,
            triggered_by=row["triggered_by"] or "manual"
        )

    except psycopg2.Error as e:
        logger.error(f"[Prefetch] DB error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/invoices/prefetch/history")
async def get_prefetch_history(limit: int = 10):
    """Get recent prefetch runs."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    db_url = os.environ.get(
        "EXPENSE_TRACKER_DB_URL",
        "postgres://postgres:4mXro2JijzR56SARkdGseBpUCw0M1JtdJMT5JbsRUbFPtcGmgnTd4eAEC4hdrEWP@46.224.117.155:5434/expense_tracker"
    )

    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM prefetch_runs
                ORDER BY started_at DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()

        conn.close()

        runs = []
        for row in rows:
            runs.append({
                "run_id": row["id"],
                "status": row["status"],
                "emails_scanned": row["emails_scanned"] or 0,
                "attachments_found": row["attachments_found"] or 0,
                "invoices_created": row["invoices_created"] or 0,
                "duplicates_skipped": row["duplicates_skipped"] or 0,
                "errors_count": row["errors_count"] or 0,
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "triggered_by": row["triggered_by"] or "manual"
            })

        return {
            "runs": runs,
            "total": len(runs),
            "currently_running": current_prefetch["running"]
        }

    except psycopg2.Error as e:
        logger.error(f"[Prefetch] DB error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/invoices/prefetch/current")
async def get_current_prefetch():
    """Get currently running prefetch status."""
    return {
        "running": current_prefetch["running"],
        "run_id": current_prefetch["run_id"]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
