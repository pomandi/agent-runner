#!/usr/bin/env python3
"""
Agent Runner HTTP API
Simple API to run agents remotely without SSH
"""
import asyncio
import os
import subprocess
import logging
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
    description="Run Claude agents remotely",
    version="1.0.0"
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


class RunResponse(BaseModel):
    status: str
    message: str
    run_id: Optional[str] = None
    agent: Optional[str] = None
    task: Optional[str] = None


def run_agent_sync(agent: str, task: str, allowed_tools: str, log_file: Path):
    """Run agent in subprocess."""
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
        
        cmd = [
            "claude",
            "--mcp-config", "/root/.claude/.mcp.json",
            "--allowedTools", allowed_tools,
            "--print", task
        ]
        
        logger.info(f"Running: {' '.join(cmd)}")
        
        with open(log_file, "w") as f:
            f.write(f"=== Agent Run Started ===\n")
            f.write(f"Agent: {agent}\n")
            f.write(f"Task: {task}\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"========================\n\n")
            f.flush()
            
            result = subprocess.run(
                cmd,
                cwd="/app",
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=300  # 5 minute timeout
            )
            
            f.write(f"\n========================\n")
            f.write(f"Exit code: {result.returncode}\n")
            f.write(f"Finished: {datetime.now().isoformat()}\n")
        
        logger.info(f"Agent completed with code: {result.returncode}")
        
    except subprocess.TimeoutExpired:
        logger.error("Agent timed out")
        with open(log_file, "a") as f:
            f.write(f"\n[ERROR] Agent timed out after 5 minutes\n")
    except Exception as e:
        logger.error(f"Agent error: {e}")
        with open(log_file, "a") as f:
            f.write(f"\n[ERROR] {str(e)}\n")
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
    """Run an agent with optional custom task."""
    
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
    
    # Determine allowed tools
    if request.allowed_tools:
        allowed_tools = request.allowed_tools
    elif agent == "feed-publisher":
        allowed_tools = "mcp__feed-publisher-mcp__*"
    else:
        allowed_tools = "*"
    
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = LOGS_DIR / f"{agent}-{run_id}.log"
    
    # Run in background
    background_tasks.add_task(run_agent_sync, agent, task, allowed_tools, log_file)
    
    return RunResponse(
        status="started",
        message=f"Agent {agent} started in background",
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


@app.get("/logs/{filename}")
async def get_log_content(filename: str, tail: int = 100):
    """Get content of a specific log file."""
    log_file = LOGS_DIR / filename
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    content = log_file.read_text()
    lines = content.split("\n")
    
    if tail and len(lines) > tail:
        lines = lines[-tail:]
    
    return {
        "file": filename,
        "lines": len(lines),
        "content": "\n".join(lines)
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
