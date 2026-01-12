"""
Memory-Hub MCP Client
=====================

HTTP/SSE client for connecting to Memory-Hub MCP server.
Provides async methods to create memory cards for analytics data.

Usage:
    client = MemoryHubClient("https://memory-hub.pomandi.com")
    await client.create_card(
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
import asyncio
from typing import Any, Dict, Optional, List
import httpx
import structlog

logger = structlog.get_logger(__name__)

# Default Memory-Hub URL
DEFAULT_MEMORY_HUB_URL = "https://memory-hub.pomandi.com"


class MemoryHubClient:
    """
    Async client for Memory-Hub MCP server.

    Uses SSE transport to connect and call MCP tools.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Memory-Hub client.

        Args:
            base_url: Memory-Hub server URL (defaults to MEMORY_HUB_URL env var)
        """
        self.base_url = base_url or os.getenv("MEMORY_HUB_URL", DEFAULT_MEMORY_HUB_URL)
        self.base_url = self.base_url.rstrip("/")
        self._session_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

        logger.info("memory_hub_client_init", base_url=self.base_url)

    async def _ensure_session(self) -> str:
        """
        Ensure we have an active SSE session.

        Returns:
            Session ID
        """
        if self._session_id:
            return self._session_id

        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        try:
            # Connect to SSE endpoint and get session ID from the event stream
            async with self._client.stream("GET", f"{self.base_url}/sse") as response:
                response.raise_for_status()

                # Read the first event which should contain the endpoint with sessionId
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                event_data = json.loads(data)
                                # The endpoint event contains the sessionId in the URL
                                if "endpoint" in str(event_data):
                                    # Parse sessionId from endpoint URL
                                    endpoint = event_data.get("endpoint", "")
                                    if "sessionId=" in endpoint:
                                        self._session_id = endpoint.split("sessionId=")[1].split("&")[0]
                                        logger.info("memory_hub_session_created", session_id=self._session_id)
                                        return self._session_id
                            except json.JSONDecodeError:
                                pass

                    # Timeout after reading initial events
                    if self._session_id:
                        break

        except Exception as e:
            logger.warning("memory_hub_session_error", error=str(e))
            raise

        if not self._session_id:
            raise Exception("Failed to get session ID from Memory-Hub")

        return self._session_id

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool on the Memory-Hub server.

        Args:
            tool_name: Name of the tool (e.g., "memory_create")
            arguments: Tool arguments

        Returns:
            Tool result
        """
        # For simplicity, we'll use the direct HTTP approach
        # Memory-Hub also supports direct tool calls

        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        try:
            # First, get a session via SSE
            session_id = await self._get_session_simple()

            if not session_id:
                logger.warning("memory_hub_no_session", tool=tool_name)
                return {"error": "Failed to establish session"}

            # Prepare MCP message
            mcp_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }

            # Send to message endpoint
            response = await self._client.post(
                f"{self.base_url}/message",
                params={"sessionId": session_id},
                json=mcp_message,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            result = response.json()
            logger.debug("memory_hub_tool_response", tool=tool_name, result=result)

            return result

        except httpx.HTTPStatusError as e:
            logger.error("memory_hub_http_error", tool=tool_name, status=e.response.status_code)
            return {"error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.error("memory_hub_call_error", tool=tool_name, error=str(e))
            return {"error": str(e)}

    async def _get_session_simple(self) -> Optional[str]:
        """
        Get a session ID using a simple SSE connection.

        Opens SSE, reads first event to get sessionId, then keeps connection for tool calls.
        """
        if self._session_id:
            return self._session_id

        if not self._client:
            self._client = httpx.AsyncClient(timeout=60.0)

        try:
            # Open SSE connection with streaming
            # We need to keep this connection open for the session to remain valid
            response = await self._client.get(
                f"{self.base_url}/sse",
                headers={"Accept": "text/event-stream"}
            )

            if response.status_code != 200:
                logger.warning("memory_hub_sse_error", status=response.status_code)
                return None

            # Parse SSE response to find sessionId in endpoint event
            content = response.text
            for line in content.split("\n"):
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data:
                        try:
                            event_data = json.loads(data)
                            endpoint = event_data.get("endpoint", "")
                            if "sessionId=" in endpoint:
                                self._session_id = endpoint.split("sessionId=")[1].split("&")[0]
                                logger.info("memory_hub_session_obtained", session_id=self._session_id)
                                return self._session_id
                        except json.JSONDecodeError:
                            continue

            return None

        except Exception as e:
            logger.error("memory_hub_session_error", error=str(e))
            return None

    async def health_check(self) -> Dict[str, Any]:
        """
        Check Memory-Hub health.

        Returns:
            Health status dict
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=10.0)

        try:
            response = await self._client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
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

        return await self._call_tool("memory_create", arguments)

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
        if self._client:
            await self._client.aclose()
            self._client = None
        self._session_id = None
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

        success = result.get("success", False) or "id" in str(result)
        logger.info(
            "memory_hub_save_result",
            success=success,
            title=title,
            result=result
        )
        return success

    except Exception as e:
        logger.warning("memory_hub_save_error", error=str(e), title=title)
        return False
