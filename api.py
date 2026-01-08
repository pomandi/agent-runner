#!/usr/bin/env python3
"""
Agent Runner HTTP API
Fast minimal API wrapper around SDK runner.
"""
import os
import json
import re
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

from sdk_runner import run_agent
from agents import list_agents, get_agent_info
from actor_status import get_all_actors_status, get_actor_checker

# Import monitoring client
try:
    from monitoring import LangfuseClient
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    LangfuseClient = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("agent-runner-api")

app = FastAPI(
    title="Agent Runner API",
    description="HTTP API for Claude Agent SDK Runner",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Static Files - Dashboard
# ============================================================

# Mount dashboard static files if they exist
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard", "dist")
if os.path.exists(DASHBOARD_DIR):
    app.mount("/dashboard/assets", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "assets")), name="dashboard-assets")
    logger.info(f"Dashboard mounted from {DASHBOARD_DIR}")

    @app.get("/dashboard")
    @app.get("/dashboard/")
    async def serve_dashboard():
        """Serve the animated actor dashboard."""
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))
else:
    logger.warning(f"Dashboard not found at {DASHBOARD_DIR}. Build with 'npm run build' in dashboard/")


# ============================================================
# Request/Response Models
# ============================================================

class InvoiceMatchRequest(BaseModel):
    transaction: dict
    invoices: List[dict]


class InvoiceMatchResponse(BaseModel):
    success: bool
    matched: bool
    invoiceId: Optional[int] = None
    confidence: float
    reasoning: str
    warnings: Optional[List[str]] = None
    error: Optional[str] = None


class RunAgentRequest(BaseModel):
    agent: str
    task: Optional[str] = "Run the default agent task"


class RunAgentResponse(BaseModel):
    success: bool
    agent: str
    task: str
    duration_seconds: float
    tool_calls: List[str]
    final_result: Optional[str] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None


# ============================================================
# Endpoints
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "Agent Runner API",
        "version": "3.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/agents")
async def get_agents():
    """List all available agents."""
    agents = list_agents()
    return {
        "agents": [get_agent_info(name) for name in agents]
    }


@app.post("/api/run", response_model=RunAgentResponse)
async def run_agent_endpoint(request: RunAgentRequest):
    """
    Run any agent with a task.

    Example:
    POST /api/run
    {
        "agent": "feed-publisher",
        "task": "Publish post to Pomandi"
    }
    """
    start_time = datetime.now()

    # Initialize monitoring client (if available and configured)
    monitor = None
    if MONITORING_AVAILABLE and os.getenv('LANGFUSE_PUBLIC_KEY'):
        monitor = LangfuseClient()
        await monitor.start_trace(request.agent, request.task, metadata={
            "api_mode": True,
            "endpoint": "/api/run"
        })
        logger.info(f"Langfuse monitoring started for {request.agent}")

    try:
        result = await run_agent(
            agent_name=request.agent,
            task=request.task,
            use_tools=False,
            use_hooks=False
        )

        if not result.get('success'):
            logger.error(f"Agent {request.agent} failed: {result.get('error')}")

        # Complete monitoring trace
        if monitor:
            status = 'completed' if result.get('success') else 'failed'
            await monitor.complete_trace(
                status=status,
                cost_usd=result.get('cost_usd'),
                output_summary=result.get('final_result'),
                error_message=result.get('error')
            )
            await monitor.close()
            logger.info(f"Langfuse trace completed: {status}")

        return RunAgentResponse(
            success=result.get('success', False),
            agent=result.get('agent', request.agent),
            task=result.get('task', request.task),
            duration_seconds=result.get('duration_seconds', 0.0),
            tool_calls=result.get('tool_calls', []),
            final_result=result.get('final_result'),
            cost_usd=result.get('cost_usd'),
            error=result.get('error')
        )

    except Exception as e:
        logger.error(f"Run agent error: {e}")

        # Complete monitoring trace with error
        if monitor:
            await monitor.complete_trace(
                status='failed',
                error_message=str(e)
            )
            await monitor.close()

        return RunAgentResponse(
            success=False,
            agent=request.agent,
            task=request.task,
            duration_seconds=(datetime.now() - start_time).total_seconds(),
            tool_calls=[],
            error=str(e)
        )


@app.post("/api/invoice-match", response_model=InvoiceMatchResponse)
async def invoice_match(request: InvoiceMatchRequest):
    """
    AI-powered invoice-transaction matching.
    Uses the invoice-matcher agent with Claude Agent SDK.
    """
    start_time = datetime.now()

    # Initialize monitoring client (if available and configured)
    monitor = None
    if MONITORING_AVAILABLE and os.getenv('LANGFUSE_PUBLIC_KEY'):
        monitor = LangfuseClient()
        await monitor.start_trace("invoice-matcher", "AI Invoice Matching", metadata={
            "api_mode": True,
            "endpoint": "/api/invoice-match",
            "transaction_id": request.transaction.get('id'),
            "num_invoices": len(request.invoices)
        })
        logger.info("Langfuse monitoring started for invoice-matcher")

    try:
        # Build task prompt for the agent
        task_prompt = f"""Find the best matching invoice for this transaction:

Transaction:
- ID: {request.transaction.get('id')}
- Amount: €{request.transaction.get('amount')}
- Date: {request.transaction.get('executionDate')}
- Counterparty: {request.transaction.get('counterpartyName')}
- Vendor: {request.transaction.get('vendorName')}
- Communication: {request.transaction.get('communication')}

Available Invoices ({len(request.invoices)}):
"""

        for inv in request.invoices:
            task_prompt += f"\n- ID: {inv.get('id')} | Invoice #{inv.get('invoiceNumber')} | €{inv.get('totalAmount')} | {inv.get('invoiceDate')} | {inv.get('vendorName')} | File: {inv.get('fileName')}"

        task_prompt += """

TASK:
1. Analyze all invoices and find the BEST match for this transaction
2. Consider: amount match, date proximity, vendor match, invoice number patterns
3. Return your analysis in this EXACT JSON format:

{
  "matched": true/false,
  "invoiceId": <numeric ID from the invoice list, or null if no match>,
  "confidence": 0.0-1.0,
  "reasoning": "<explain your matching logic>",
  "warnings": ["<any concerns>"]
}

IMPORTANT:
- Be STRICT on amount matching (±2% tolerance max)
- Prefer same vendor
- Date should be within ±30 days
- confidence >= 0.90 for auto-match
- confidence 0.70-0.89 needs human review
- confidence < 0.70 means no match

Return ONLY the JSON object, no markdown, no explanation.
"""

        # Run invoice-matcher agent
        result = await run_agent(
            agent_name="invoice-matcher",
            task=task_prompt,
            use_tools=False,
            use_hooks=False
        )

        if not result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=f"Agent execution failed: {result.get('error', 'Unknown error')}"
            )

        # Parse agent response (expecting JSON)
        final_result = result.get('final_result', '')

        # Try to extract JSON from response
        # Remove markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', final_result, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*?\}', final_result, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError("No JSON found in agent response")

        match_result = json.loads(json_str)

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Invoice matching completed in {duration:.2f}s: {match_result.get('matched')}")

        # Complete monitoring trace
        if monitor:
            await monitor.complete_trace(
                status='completed',
                output_summary=f"Matched: {match_result.get('matched')}, Confidence: {match_result.get('confidence')}"
            )
            await monitor.close()
            logger.info("Langfuse trace completed: completed")

        return InvoiceMatchResponse(
            success=True,
            matched=match_result.get('matched', False),
            invoiceId=match_result.get('invoiceId'),
            confidence=match_result.get('confidence', 0.0),
            reasoning=match_result.get('reasoning', ''),
            warnings=match_result.get('warnings', [])
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")

        # Complete monitoring trace with error
        if monitor:
            await monitor.complete_trace(
                status='failed',
                error_message=f"JSON parse error: {str(e)}"
            )
            await monitor.close()

        return InvoiceMatchResponse(
            success=False,
            matched=False,
            invoiceId=None,
            confidence=0.0,
            reasoning="Failed to parse agent response as JSON",
            error=str(e)
        )

    except Exception as e:
        logger.error(f"Invoice matching error: {e}")

        # Complete monitoring trace with error
        if monitor:
            await monitor.complete_trace(
                status='failed',
                error_message=str(e)
            )
            await monitor.close()

        return InvoiceMatchResponse(
            success=False,
            matched=False,
            invoiceId=None,
            confidence=0.0,
            reasoning="Internal server error",
            error=str(e)
        )


# ============================================================
# Actor Status Endpoints (Animated Dashboard)
# ============================================================

@app.get("/api/actors/status")
async def get_actors_status():
    """
    Get status and recent activity for all 8 system actors.
    Used by the animated monitoring dashboard.
    """
    try:
        status = await get_all_actors_status()
        return status
    except Exception as e:
        logger.error(f"Actor status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/actors/{actor_name}/activity")
async def get_actor_activity(actor_name: str):
    """
    Get detailed activity for a specific actor.
    """
    try:
        checker = get_actor_checker()
        all_status = await checker.get_all_status()

        for actor in all_status.get("actors", []):
            if actor.get("name") == actor_name:
                return actor

        raise HTTPException(status_code=404, detail=f"Actor '{actor_name}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Actor activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/actors/{actor_name}/activity")
async def update_actor_activity(actor_name: str, action: str, detail: str):
    """
    Update activity for a specific actor (used by workflows).
    """
    try:
        checker = get_actor_checker()
        checker.update_activity(actor_name, action, detail)
        return {"success": True, "actor": actor_name}
    except Exception as e:
        logger.error(f"Update activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Run Server
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
