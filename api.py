#!/usr/bin/env python3
"""
Agent Runner HTTP API
Simple API to run agents remotely without SSH
Enhanced with full conversation logging
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner-api")

app = FastAPI(
    title="Agent Runner API",
    description="Run Claude agents remotely with full conversation logging",
    version="2.1.0"
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
        "agent_name": os.getenv("AGENT_NAME", "unknown"),
        "schedule": os.getenv("AGENT_SCHEDULE", "none"),
        "credentials_found": creds_exist,
        "current_run": current_run,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest, background_tasks: BackgroundTasks):
    """Run an agent with full conversation logging."""
    
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
    
    # Determine allowed tools
    if request.allowed_tools:
        allowed_tools = request.allowed_tools
    elif agent == "feed-publisher":
        allowed_tools = "mcp__feed-publisher-mcp__*,mcp__social-media-publish__*"
    else:
        allowed_tools = "*"
    
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = LOGS_DIR / f"{agent}-{run_id}.log"
    
    # Run in background
    background_tasks.add_task(run_agent_sync, agent, task, allowed_tools, log_file, verbose)
    
    return RunResponse(
        status="started",
        message=f"Agent {agent} started with verbose logging",
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
