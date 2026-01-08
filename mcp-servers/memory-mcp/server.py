#!/usr/bin/env python3
"""
Memory MCP Server
=================

Model Context Protocol server exposing memory operations to agents.

Tools provided:
- search_memory: Search for similar content in memory
- save_to_memory: Save new content to memory
- get_memory_stats: Get memory system statistics

Usage:
    python server.py
"""

import asyncio
import os
import sys
from typing import Any

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
import structlog

from memory import MemoryManager

logger = structlog.get_logger(__name__)

# Initialize MCP server
server = Server("memory-mcp")

# Global memory manager instance
memory_manager: MemoryManager = None


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available memory tools.
    """
    return [
        types.Tool(
            name="search_memory",
            description="""
Search for similar content in memory using semantic search.

Returns relevant historical data based on similarity to the query.
Useful for finding past invoices, social posts, ad reports, etc.

Collections available:
- invoices: Invoice content for matching against transactions
- social_posts: Past social media captions and performance
- ad_reports: Google Ads campaign performance data
- agent_context: General agent execution history
            """.strip(),
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection to search (invoices, social_posts, ad_reports, agent_context)",
                        "enum": ["invoices", "social_posts", "ad_reports", "agent_context"]
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query text (will be embedded for semantic search)"
                    },
                    "top_k": {
                        "type": "number",
                        "description": "Number of results to return (default: 10)",
                        "default": 10
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters (e.g., {'matched': false, 'brand': 'pomandi'})",
                        "additionalProperties": True
                    }
                },
                "required": ["collection", "query"]
            }
        ),

        types.Tool(
            name="save_to_memory",
            description="""
Save new content to memory for future retrieval.

Generates embedding and stores in vector database.
Useful for saving invoices, social posts, ad insights, etc.

Note: Saved content will be available for semantic search immediately.
            """.strip(),
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection to save to",
                        "enum": ["invoices", "social_posts", "ad_reports", "agent_context"]
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to embed and save"
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Additional metadata to store (must match collection schema)",
                        "additionalProperties": True
                    }
                },
                "required": ["collection", "content", "metadata"]
            }
        ),

        types.Tool(
            name="get_memory_stats",
            description="""
Get memory system statistics.

Returns:
- Cache hit rates
- Collection sizes
- Embedding cache stats
- Overall system health
            """.strip(),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    """
    global memory_manager

    # Initialize memory manager if needed
    if memory_manager is None:
        memory_manager = MemoryManager()
        await memory_manager.initialize()

    try:
        if name == "search_memory":
            # Extract arguments
            collection = arguments.get("collection")
            query = arguments.get("query")
            top_k = arguments.get("top_k", 10)
            filters = arguments.get("filters")

            if not collection or not query:
                return [types.TextContent(
                    type="text",
                    text="Error: 'collection' and 'query' are required"
                )]

            # Search memory
            results = await memory_manager.search(
                collection=collection,
                query=query,
                top_k=top_k,
                filters=filters
            )

            # Format response
            if not results:
                return [types.TextContent(
                    type="text",
                    text=f"No similar content found in '{collection}' collection."
                )]

            # Build readable response
            response_lines = [f"Found {len(results)} similar items in '{collection}':\n"]
            for i, result in enumerate(results, 1):
                score = result["score"]
                payload = result["payload"]

                response_lines.append(f"\n{i}. Similarity: {score:.2%}")
                for key, value in payload.items():
                    if not key.startswith("_"):  # Skip internal fields
                        response_lines.append(f"   {key}: {value}")

            return [types.TextContent(
                type="text",
                text="\n".join(response_lines)
            )]

        elif name == "save_to_memory":
            # Extract arguments
            collection = arguments.get("collection")
            content = arguments.get("content")
            metadata = arguments.get("metadata", {})

            if not collection or not content:
                return [types.TextContent(
                    type="text",
                    text="Error: 'collection' and 'content' are required"
                )]

            # Save to memory
            doc_id = await memory_manager.save(
                collection=collection,
                content=content,
                metadata=metadata
            )

            return [types.TextContent(
                type="text",
                text=f"Successfully saved to '{collection}' collection (ID: {doc_id})"
            )]

        elif name == "get_memory_stats":
            # Get system stats
            stats = await memory_manager.get_system_stats()

            # Format response
            response_lines = ["Memory System Statistics:\n"]

            # Cache stats
            cache = stats.get("cache", {})
            response_lines.append(f"Cache hit rate: {cache.get('hit_rate_percent', 0):.1f}%")
            response_lines.append(f"Cache hits: {cache.get('hits', 0)}")
            response_lines.append(f"Cache misses: {cache.get('misses', 0)}\n")

            # Collection stats
            response_lines.append("Collections:")
            for coll_name, coll_info in stats.get("collections", {}).items():
                if "error" in coll_info:
                    response_lines.append(f"  {coll_name}: Error - {coll_info['error']}")
                else:
                    points = coll_info.get("points_count", 0)
                    response_lines.append(f"  {coll_name}: {points} items")

            return [types.TextContent(
                type="text",
                text="\n".join(response_lines)
            )]

        else:
            return [types.TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]

    except Exception as e:
        logger.error("tool_execution_failed", tool=name, error=str(e))
        return [types.TextContent(
            type="text",
            text=f"Error executing {name}: {str(e)}"
        )]


async def main():
    """Run the MCP server."""
    # Set up logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ]
    )

    logger.info("starting_memory_mcp_server")

    # Run server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="memory-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
