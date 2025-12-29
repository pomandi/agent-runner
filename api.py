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
{
  "matched": true or false,
  "invoiceId": number or null,
  "confidence": number between 0 and 1,
  "reasoning": "brief explanation of why this match was selected or why no match was found",
  "amountDifference": number (percentage difference),
  "warnings": ["any concerns about this match"]
}

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

        # Call Claude CLI
        cmd = [
            "claude",
            "--print",  # Just print response, no interactive mode
            prompt
        ]

        logger.info(f"[InvoiceMatch] Processing transaction {request.transaction.get('id')}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd="/app"
        )

        if result.returncode != 0:
            logger.error(f"[InvoiceMatch] CLI error: {result.stderr}")
            return InvoiceMatchResponse(
                success=False,
                error=f"Claude CLI error: {result.stderr[:200]}"
            )

        response_text = result.stdout.strip()
        logger.info(f"[InvoiceMatch] Response length: {len(response_text)}")

        # Parse JSON from response
        json_match = None
        try:
            # Try to find JSON in response
            import re
            json_pattern = re.search(r'\{[\s\S]*\}', response_text)
            if json_pattern:
                json_match = json.loads(json_pattern.group())
        except json.JSONDecodeError as e:
            logger.error(f"[InvoiceMatch] JSON parse error: {e}")
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
