"""
Memory-Hub Test Activity
========================

Simple activity to test Memory-Hub connectivity from Temporal worker.
Uses proper SSE streaming to get session ID and keeps connection open
during the message call.
"""

import os
import json
import re
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

    IMPORTANT: The SSE session only exists while the SSE connection is open.
    We must keep the SSE stream open and call /message while connected.

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
        "sse_raw_data": None,
        "card_created": None,
        "error": None
    }

    try:
        # Step 1: Health check
        logger.info("memory_hub_health_check")
        async with httpx.AsyncClient(timeout=30.0) as client:
            health_resp = await client.get(f"{MEMORY_HUB_URL}/health")
            result["health_check"] = health_resp.json() if health_resp.status_code == 200 else {"error": health_resp.status_code}

        # Step 2: Get SSE session and keep it open while calling /message
        logger.info("memory_hub_sse_connect_streaming")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Use streaming to keep the SSE connection open
            async with client.stream(
                "GET",
                f"{MEMORY_HUB_URL}/sse",
                headers={"Accept": "text/event-stream"}
            ) as response:
                if response.status_code != 200:
                    result["error"] = f"SSE connect failed: {response.status_code}"
                    return result

                # Read chunks to get session ID
                session_id = None
                collected_data = ""

                async for chunk in response.aiter_text():
                    collected_data += chunk
                    logger.info("memory_hub_sse_chunk", chunk_len=len(chunk), total_len=len(collected_data))

                    # Look for sessionId in the data
                    if "sessionId=" in collected_data:
                        match = re.search(r'sessionId=([a-f0-9-]+)', collected_data)
                        if match:
                            session_id = match.group(1)
                            result["sse_raw_data"] = collected_data[:500]
                            result["sse_session"] = session_id
                            logger.info("memory_hub_session_found", session_id=session_id)

                            # NOW call /message while SSE is still open!
                            # Use a separate client for the POST
                            async with httpx.AsyncClient(timeout=30.0) as msg_client:
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
                                create_resp = await msg_client.post(
                                    f"{MEMORY_HUB_URL}/message",
                                    params={"sessionId": session_id},
                                    json=mcp_request,
                                    headers={"Content-Type": "application/json"},
                                    timeout=15.0
                                )

                                if create_resp.status_code == 200 or create_resp.status_code == 202:
                                    result["card_created"] = {
                                        "status": create_resp.status_code,
                                        "response": create_resp.text[:200]
                                    }
                                    logger.info("memory_hub_card_created",
                                              status=create_resp.status_code,
                                              response=create_resp.text[:200])
                                else:
                                    result["error"] = f"Card create failed: {create_resp.status_code} - {create_resp.text[:200]}"

                            # Done - exit the SSE loop
                            # (Don't try to read more from SSE - causes stream re-read error)
                            break

                    # Safety limit
                    if len(collected_data) > 2000:
                        result["error"] = "No session ID found after 2KB"
                        return result

        if not session_id:
            result["error"] = "Session ID not found in SSE stream"

    except httpx.TimeoutException as e:
        result["error"] = f"Timeout: {str(e)}"
        logger.error("memory_hub_timeout", error=str(e))
    except Exception as e:
        result["error"] = f"Error: {str(e)}"
        logger.error("memory_hub_error", error=str(e), exc_info=True)

    logger.info("memory_hub_test_complete", result=result)
    return result
