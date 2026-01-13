"""
Memory-Hub MCP Client
=====================

HTTP client for connecting to Memory-Hub MCP server.
Provides async methods to create memory cards for analytics data.

Uses streamable HTTP transport (POST /mcp) instead of SSE for reliability.

Usage:
    client = MemoryHubClient("https://memory-hub.pomandi.com")
    result = await client.create_card(
        type="note",
        title="Daily Analytics",
        content="...",
        project="pomandi",
        data_source="daily_analytics",
        data_date="2026-01-12"
    )
"""

import os
import json
import re
import uuid
from typing import Any, Dict, Optional, List
import httpx
import structlog

logger = structlog.get_logger(__name__)

# Default Memory-Hub URL
DEFAULT_MEMORY_HUB_URL = "https://memory-hub.pomandi.com"


class MemoryHubClient:
    """
    Async client for Memory-Hub MCP server.

    Uses streamable HTTP transport for reliable tool calls.
    Falls back to SSE transport if streamable HTTP is not available.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Memory-Hub client.

        Args:
            base_url: Memory-Hub server URL (defaults to MEMORY_HUB_URL env var)
        """
        self.base_url = base_url or os.getenv("MEMORY_HUB_URL", DEFAULT_MEMORY_HUB_URL)
        self.base_url = self.base_url.rstrip("/")
        self._initialized = False

        logger.info("memory_hub_client_init", base_url=self.base_url)

    async def _call_tool_streamable_http(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a tool using streamable HTTP transport (POST /mcp).

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Tool result
        """
        request_id = str(uuid.uuid4())

        # JSON-RPC request for tools/call
        mcp_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/mcp",
                    json=mcp_request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.debug("memory_hub_streamable_http_response", result=result)

                    # Extract result from JSON-RPC response
                    if "result" in result:
                        return result["result"]
                    elif "error" in result:
                        logger.error("memory_hub_jsonrpc_error", error=result["error"])
                        return {"error": result["error"]}
                    return result

                elif response.status_code == 404:
                    # Streamable HTTP not available, return None to try fallback
                    logger.debug("memory_hub_streamable_http_not_available")
                    return None

                else:
                    logger.error(
                        "memory_hub_http_error",
                        status=response.status_code,
                        body=response.text[:500]
                    )
                    return {"error": f"HTTP {response.status_code}"}

            except httpx.TimeoutException:
                logger.error("memory_hub_timeout", tool=tool_name)
                return {"error": "Request timeout"}
            except Exception as e:
                logger.error("memory_hub_request_error", error=str(e))
                return {"error": str(e)}

    async def _call_tool_sse(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a tool using SSE transport.

        IMPORTANT: SSE sessions only exist while the connection is open.
        We must use streaming and call /message while the stream is active.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Tool result
        """
        async with httpx.AsyncClient(timeout=60.0) as sse_client:
            try:
                # Step 1: Open SSE stream and keep it open
                async with sse_client.stream(
                    "GET",
                    f"{self.base_url}/sse",
                    headers={"Accept": "text/event-stream"}
                ) as response:
                    if response.status_code != 200:
                        logger.error("memory_hub_sse_connect_failed", status=response.status_code)
                        return {"error": f"SSE connect failed: {response.status_code}"}

                    # Read chunks until we find the session ID
                    session_id = None
                    collected_data = ""

                    async for chunk in response.aiter_text():
                        collected_data += chunk
                        logger.debug("memory_hub_sse_chunk", chunk_len=len(chunk))

                        # Look for sessionId in the data
                        if "sessionId=" in collected_data:
                            match = re.search(r'sessionId=([a-f0-9-]+)', collected_data)
                            if match:
                                session_id = match.group(1)
                                logger.debug("memory_hub_session_obtained", session_id=session_id)

                                # Step 2: Call /message while SSE is still open!
                                # Use a separate client for the POST
                                async with httpx.AsyncClient(timeout=30.0) as msg_client:
                                    mcp_message = {
                                        "jsonrpc": "2.0",
                                        "id": str(uuid.uuid4()),
                                        "method": "tools/call",
                                        "params": {
                                            "name": tool_name,
                                            "arguments": arguments
                                        }
                                    }

                                    tool_response = await msg_client.post(
                                        f"{self.base_url}/message",
                                        params={"sessionId": session_id},
                                        json=mcp_message,
                                        headers={"Content-Type": "application/json"}
                                    )

                                    if tool_response.status_code in (200, 202):
                                        # Status 202 means Accepted (async processing)
                                        if tool_response.status_code == 202:
                                            logger.info("memory_hub_message_accepted")
                                            # For 202, the result comes on SSE stream
                                            # but we just return success since card is created
                                            return {"success": True, "action": "accepted"}

                                        try:
                                            result = tool_response.json()

                                            # Handle JSON-RPC response format
                                            if "result" in result:
                                                tool_result = result["result"]
                                                if isinstance(tool_result, dict) and "content" in tool_result:
                                                    contents = tool_result.get("content", [])
                                                    if contents and isinstance(contents, list):
                                                        for content in contents:
                                                            if content.get("type") == "text":
                                                                try:
                                                                    return json.loads(content.get("text", "{}"))
                                                                except json.JSONDecodeError:
                                                                    return {"text": content.get("text")}
                                                return tool_result
                                            return result
                                        except json.JSONDecodeError:
                                            # Non-JSON response (like "Accepted")
                                            return {"success": True, "response": tool_response.text[:200]}
                                    else:
                                        logger.error("memory_hub_tool_call_failed", status=tool_response.status_code)
                                        return {"error": f"Tool call failed: {tool_response.status_code} - {tool_response.text[:200]}"}

                                # Exit the SSE loop after we're done
                                break

                        # Safety limit
                        if len(collected_data) > 2000:
                            logger.error("memory_hub_no_session_id_found")
                            return {"error": "No session ID found in SSE stream"}

                    if not session_id:
                        return {"error": "Session ID not found in SSE stream"}

            except httpx.TimeoutException:
                logger.error("memory_hub_sse_timeout", tool=tool_name)
                return {"error": "SSE timeout"}
            except Exception as e:
                logger.error("memory_hub_sse_error", error=str(e))
                return {"error": str(e)}

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool on the Memory-Hub server.

        Tries streamable HTTP first, falls back to SSE if not available.

        Args:
            tool_name: Name of the tool (e.g., "memory_create")
            arguments: Tool arguments

        Returns:
            Tool result
        """
        # Try streamable HTTP transport first (more reliable)
        result = await self._call_tool_streamable_http(tool_name, arguments)

        if result is None:
            # Streamable HTTP not available, fallback to SSE
            logger.info("memory_hub_fallback_to_sse", tool=tool_name)
            result = await self._call_tool_sse(tool_name, arguments)

        return result

    async def health_check(self) -> Dict[str, Any]:
        """
        Check Memory-Hub health.

        Returns:
            Health status dict
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    return response.json()
                return {"status": "unhealthy", "code": response.status_code}
            except Exception as e:
                logger.error("memory_hub_health_error", error=str(e))
                return {"status": "error", "error": str(e)}

    async def create_card(
        self,
        type: str,
        title: str,
        content: str,
        project: Optional[str] = None,
        domain: Optional[str] = None,
        tags: Optional[List[str]] = None,
        data_source: Optional[str] = None,
        data_date: Optional[str] = None,
        on_duplicate: str = "update"
    ) -> Dict[str, Any]:
        """
        Create a memory card in Memory-Hub.

        Args:
            type: Card type (bugfix, runbook, decision, note, etc.)
            title: Card title
            content: Card content (markdown supported)
            project: Project name (pomandi, costume, etc.)
            domain: Domain name (google-ads, meta-ads, etc.)
            tags: List of tags
            data_source: Source identifier for deduplication
            data_date: Date for time-series deduplication (YYYY-MM-DD)
            on_duplicate: Action on duplicate (skip, update, error)

        Returns:
            Result dict with success status and card ID
        """
        arguments = {
            "type": type,
            "title": title,
            "content": content
        }

        if project:
            arguments["project"] = project
        if domain:
            arguments["domain"] = domain
        if tags:
            arguments["tags"] = tags
        if data_source:
            arguments["data_source"] = data_source
        if data_date:
            arguments["data_date"] = data_date
        if on_duplicate:
            arguments["on_duplicate"] = on_duplicate

        result = await self._call_tool("memory_create", arguments)

        # Check for success
        if isinstance(result, dict):
            if result.get("success") or result.get("id"):
                logger.info(
                    "memory_hub_card_created",
                    title=title,
                    id=result.get("id"),
                    action=result.get("action")
                )
            elif result.get("error"):
                logger.error("memory_hub_create_failed", error=result.get("error"))

        return result

    async def search(
        self,
        query: str,
        project: Optional[str] = None,
        domain: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Search memory cards.

        Args:
            query: Search query
            project: Filter by project
            domain: Filter by domain
            type: Filter by card type
            limit: Max results

        Returns:
            Search results
        """
        arguments = {"query": query, "limit": limit}

        if project:
            arguments["project"] = project
        if domain:
            arguments["domain"] = domain
        if type:
            arguments["type"] = type

        return await self._call_tool("memory_search", arguments)

    async def close(self):
        """Close the client and cleanup resources."""
        logger.debug("memory_hub_client_closed")


# Singleton instance
_client: Optional[MemoryHubClient] = None


def get_memory_hub_client() -> MemoryHubClient:
    """
    Get the singleton Memory-Hub client instance.

    Returns:
        MemoryHubClient instance
    """
    global _client
    if _client is None:
        _client = MemoryHubClient()
    return _client


async def save_to_memory_hub(
    type: str,
    title: str,
    content: str,
    project: Optional[str] = None,
    domain: Optional[str] = None,
    tags: Optional[List[str]] = None,
    data_source: Optional[str] = None,
    data_date: Optional[str] = None
) -> bool:
    """
    Convenience function to save to Memory-Hub.

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        client = get_memory_hub_client()
        result = await client.create_card(
            type=type,
            title=title,
            content=content,
            project=project,
            domain=domain,
            tags=tags,
            data_source=data_source,
            data_date=data_date,
            on_duplicate="update"
        )

        # Check for success indicators
        success = (
            result.get("success", False) or
            result.get("id") is not None or
            result.get("action") in ["created", "updated"]
        )

        if success:
            logger.info(
                "memory_hub_save_success",
                title=title,
                id=result.get("id")
            )
        else:
            logger.error(
                "memory_hub_save_failed",
                title=title,
                result=result
            )

        return success

    except Exception as e:
        logger.error("memory_hub_save_error", error=str(e), title=title)
        return False
