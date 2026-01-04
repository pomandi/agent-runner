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
from pydantic import BaseModel
import uvicorn

from sdk_runner import run_agent

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


@app.post("/api/invoice-match", response_model=InvoiceMatchResponse)
async def invoice_match(request: InvoiceMatchRequest):
    """
    AI-powered invoice-transaction matching.
    Uses the invoice-matcher agent with Claude Agent SDK.
    """
    start_time = datetime.now()

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
            task_prompt += f"\n- Invoice #{inv.get('invoiceNumber')} | €{inv.get('totalAmount')} | {inv.get('invoiceDate')} | {inv.get('vendorName')} | File: {inv.get('fileName')}"

        task_prompt += """

TASK:
1. Analyze all invoices and find the BEST match for this transaction
2. Consider: amount match, date proximity, vendor match, invoice number patterns
3. Return your analysis in this EXACT JSON format:

{
  "matched": true/false,
  "invoiceId": <invoice_id or null>,
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
        return InvoiceMatchResponse(
            success=False,
            matched=False,
            invoiceId=None,
            confidence=0.0,
            reasoning="Internal server error",
            error=str(e)
        )


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
