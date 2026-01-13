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
        Call a tool using SSE transport (legacy fallback).

        Opens SSE connection, gets session ID, makes POST call.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Tool result
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # Step 1: Open SSE connection and get session ID
                sse_response = await client.get(
                    f"{self.base_url}/sse",
                    headers={"Accept": "text/event-stream"}
                )

                if sse_response.status_code != 200:
                    logger.error("memory_hub_sse_connect_failed", status=sse_response.status_code)
                    return {"error": f"SSE connect failed: {sse_response.status_code}"}

                # Parse session ID from SSE response
                session_id = None
                for line in sse_response.text.split("\n"):
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                event_data = json.loads(data)
                                endpoint = event_data.get("endpoint", "")
                                if "sessionId=" in endpoint:
                                    session_id = endpoint.split("sessionId=")[1].split("&")[0]
                                    break
                            except json.JSONDecodeError:
                                continue

                if not session_id:
                    logger.error("memory_hub_no_session_id")
                    return {"error": "Failed to get session ID from SSE"}

                logger.debug("memory_hub_session_obtained", session_id=session_id)

                # Step 2: Make tool call with session ID
                mcp_message = {
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }

                tool_response = await client.post(
                    f"{self.base_url}/message",
                    params={"sessionId": session_id},
                    json=mcp_message,
                    headers={"Content-Type": "application/json"}
                )

                if tool_response.status_code == 200:
                    result = tool_response.json()

                    # Handle JSON-RPC response format
                    if "result" in result:
                        # Extract content from MCP tool response
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
                else:
                    logger.error("memory_hub_tool_call_failed", status=tool_response.status_code)
                    return {"error": f"Tool call failed: {tool_response.status_code}"}

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
