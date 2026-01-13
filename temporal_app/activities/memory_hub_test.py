"""
Memory-Hub Test Activity
========================

Simple activity to test Memory-Hub connectivity from Temporal worker.
"""

import os
import json
from datetime import datetime
from temporalio import activity
import structlog
import httpx

logger = structlog.get_logger(__name__)

# Memory-Hub URL
MEMORY_HUB_URL = os.getenv("MEMORY_HUB_URL", "https://memory-hub.pomandi.com")


@activity.defn
async def test_memory_hub_save() -> dict:
    """
    Test saving to Memory-Hub via SSE transport.

    Returns:
        dict with success status and details
    """
    import uuid

    timestamp = datetime.utcnow().isoformat()
    test_id = str(uuid.uuid4())[:8]

    logger.info("memory_hub_test_start", test_id=test_id, url=MEMORY_HUB_URL)

    result = {
        "test_id": test_id,
        "timestamp": timestamp,
        "memory_hub_url": MEMORY_HUB_URL,
        "health_check": None,
        "sse_session": None,
        "card_created": None,
        "error": None
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Health check
            logger.info("memory_hub_health_check")
            health_resp = await client.get(f"{MEMORY_HUB_URL}/health")
            result["health_check"] = health_resp.json() if health_resp.status_code == 200 else {"error": health_resp.status_code}

            # Step 2: Get SSE session
            logger.info("memory_hub_sse_connect")
            sse_resp = await client.get(
                f"{MEMORY_HUB_URL}/sse",
                headers={"Accept": "text/event-stream"},
                timeout=10.0
            )

            if sse_resp.status_code != 200:
                result["error"] = f"SSE connect failed: {sse_resp.status_code}"
                return result

            # Parse session ID
            session_id = None
            for line in sse_resp.text.split("\n"):
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if "sessionId=" in data:
                        # Extract from endpoint string
                        session_id = data.split("sessionId=")[1].split("&")[0].split('"')[0]
                        break

            if not session_id:
                result["error"] = f"No session ID found in SSE response: {sse_resp.text[:200]}"
                return result

            result["sse_session"] = session_id
            logger.info("memory_hub_session_obtained", session_id=session_id)

            # Step 3: Create memory card
            mcp_request = {
                "jsonrpc": "2.0",
                "id": test_id,
                "method": "tools/call",
                "params": {
                    "name": "memory_create",
                    "arguments": {
                        "type": "note",
                        "title": f"Temporal Worker Test - {timestamp}",
                        "content": f"Test from Temporal worker. Test ID: {test_id}",
                        "project": "pomandi",
                        "tags": ["test", "temporal-worker", "memory-hub-test"],
                        "data_source": "temporal-worker-test",
                        "data_date": datetime.utcnow().strftime("%Y-%m-%d")
                    }
                }
            }

            logger.info("memory_hub_create_card", session_id=session_id)
            create_resp = await client.post(
                f"{MEMORY_HUB_URL}/message",
                params={"sessionId": session_id},
                json=mcp_request,
                headers={"Content-Type": "application/json"},
                timeout=15.0
            )

            if create_resp.status_code == 200:
                create_result = create_resp.json()
                result["card_created"] = create_result
                logger.info("memory_hub_card_created", result=create_result)
            else:
                result["error"] = f"Card create failed: {create_resp.status_code} - {create_resp.text[:200]}"

    except httpx.TimeoutException as e:
        result["error"] = f"Timeout: {str(e)}"
        logger.error("memory_hub_timeout", error=str(e))
    except Exception as e:
        result["error"] = f"Error: {str(e)}"
        logger.error("memory_hub_error", error=str(e))

    logger.info("memory_hub_test_complete", result=result)
    return result
