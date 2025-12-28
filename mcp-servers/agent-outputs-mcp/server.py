#!/usr/bin/env python3
"""
Agent Outputs MCP Server
========================
MCP server for storing and retrieving agent execution outputs.
Connects directly to PostgreSQL on the same server.
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional
import asyncpg
from mcp.server import Server
from mcp.types import Tool, TextContent

# Database Configuration - localhost connection (same server)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "dXn0xUUpebj1ooW9nI0gJMQJMrJloLaVexQkDm8XvWN6CYNwd3JMXiVUuBcgqr4m")
DB_NAME = os.getenv("DB_NAME", "postgres")

# Global connection pool
pool: Optional[asyncpg.Pool] = None

server = Server("agent-outputs")


async def get_pool() -> asyncpg.Pool:
    """Get or create database connection pool."""
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_size=1,
            max_size=5
        )
    return pool


async def init_database():
    """Initialize database tables if they don't exist."""
    p = await get_pool()
    async with p.acquire() as conn:
        # Main outputs table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_outputs (
                id SERIAL PRIMARY KEY,
                agent_name VARCHAR(100) NOT NULL,
                output_type VARCHAR(50) NOT NULL,
                title VARCHAR(500),
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}',
                tags TEXT[] DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Indexes for common queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_outputs_agent_name
            ON agent_outputs(agent_name)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_outputs_output_type
            ON agent_outputs(output_type)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_outputs_created_at
            ON agent_outputs(created_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_outputs_tags
            ON agent_outputs USING GIN(tags)
        """)

        # Execution logs table for tracking agent runs
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_executions (
                id SERIAL PRIMARY KEY,
                agent_name VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'running',
                started_at TIMESTAMPTZ DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                duration_seconds FLOAT,
                input_summary TEXT,
                output_summary TEXT,
                error_message TEXT,
                metadata JSONB DEFAULT '{}'
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_name
            ON agent_executions(agent_name)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_executions_status
            ON agent_executions(status)
        """)


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
        Tool(
            name="save_output",
            description="Save an agent output/report to the database. Use for storing analysis results, reports, data exports, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the agent producing the output (e.g., 'google-ads-analyzer', 'meta-ads-collector')"
                    },
                    "output_type": {
                        "type": "string",
                        "description": "Type of output: 'report', 'analysis', 'data', 'error', 'summary', 'recommendation'",
                        "enum": ["report", "analysis", "data", "error", "summary", "recommendation", "log"]
                    },
                    "title": {
                        "type": "string",
                        "description": "Title/subject of the output"
                    },
                    "content": {
                        "type": "string",
                        "description": "The actual content (can be text, JSON string, markdown, etc.)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization (e.g., ['pomandi', 'google-ads', '2024-12'])"
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Additional metadata as JSON object"
                    }
                },
                "required": ["agent_name", "output_type", "content"]
            }
        ),
        Tool(
            name="get_outputs",
            description="Retrieve agent outputs with optional filters. Returns recent outputs by default.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Filter by agent name"
                    },
                    "output_type": {
                        "type": "string",
                        "description": "Filter by output type"
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag (outputs containing this tag)"
                    },
                    "search": {
                        "type": "string",
                        "description": "Search in title and content"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20, max: 100)",
                        "default": 20
                    },
                    "days": {
                        "type": "integer",
                        "description": "Only return outputs from last N days"
                    }
                }
            }
        ),
        Tool(
            name="get_output_by_id",
            description="Get a specific output by its ID with full content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Output ID"
                    }
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="delete_output",
            description="Delete an output by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Output ID to delete"
                    }
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="start_execution",
            description="Log the start of an agent execution. Returns execution_id for tracking.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the agent starting execution"
                    },
                    "input_summary": {
                        "type": "string",
                        "description": "Brief summary of input/task"
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Additional metadata"
                    }
                },
                "required": ["agent_name"]
            }
        ),
        Tool(
            name="complete_execution",
            description="Mark an agent execution as completed (success or failure).",
            inputSchema={
                "type": "object",
                "properties": {
                    "execution_id": {
                        "type": "integer",
                        "description": "Execution ID from start_execution"
                    },
                    "status": {
                        "type": "string",
                        "description": "Final status",
                        "enum": ["completed", "failed", "cancelled"]
                    },
                    "output_summary": {
                        "type": "string",
                        "description": "Brief summary of output/result"
                    },
                    "error_message": {
                        "type": "string",
                        "description": "Error message if failed"
                    }
                },
                "required": ["execution_id", "status"]
            }
        ),
        Tool(
            name="get_executions",
            description="Get recent agent executions with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Filter by agent name"
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status",
                        "enum": ["running", "completed", "failed", "cancelled"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 20)",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="get_stats",
            description="Get statistics about stored outputs and executions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Stats for last N days (default: 30)",
                        "default": 30
                    }
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    try:
        await init_database()
        p = await get_pool()

        if name == "save_output":
            async with p.acquire() as conn:
                tags = arguments.get("tags", [])
                metadata = arguments.get("metadata", {})

                row = await conn.fetchrow("""
                    INSERT INTO agent_outputs
                    (agent_name, output_type, title, content, tags, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id, created_at
                """,
                    arguments["agent_name"],
                    arguments["output_type"],
                    arguments.get("title"),
                    arguments["content"],
                    tags,
                    json.dumps(metadata)
                )

                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "success": True,
                        "id": row["id"],
                        "created_at": row["created_at"].isoformat(),
                        "message": f"Output saved with ID {row['id']}"
                    }, indent=2)
                )]

        elif name == "get_outputs":
            async with p.acquire() as conn:
                conditions = []
                params = []
                param_idx = 1

                if arguments.get("agent_name"):
                    conditions.append(f"agent_name = ${param_idx}")
                    params.append(arguments["agent_name"])
                    param_idx += 1

                if arguments.get("output_type"):
                    conditions.append(f"output_type = ${param_idx}")
                    params.append(arguments["output_type"])
                    param_idx += 1

                if arguments.get("tag"):
                    conditions.append(f"${param_idx} = ANY(tags)")
                    params.append(arguments["tag"])
                    param_idx += 1

                if arguments.get("search"):
                    conditions.append(f"(title ILIKE ${param_idx} OR content ILIKE ${param_idx})")
                    params.append(f"%{arguments['search']}%")
                    param_idx += 1

                if arguments.get("days"):
                    conditions.append(f"created_at > NOW() - INTERVAL '{int(arguments['days'])} days'")

                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                limit = min(arguments.get("limit", 20), 100)

                query = f"""
                    SELECT id, agent_name, output_type, title,
                           LEFT(content, 500) as content_preview,
                           tags, created_at
                    FROM agent_outputs
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT {limit}
                """

                rows = await conn.fetch(query, *params)

                results = []
                for row in rows:
                    results.append({
                        "id": row["id"],
                        "agent_name": row["agent_name"],
                        "output_type": row["output_type"],
                        "title": row["title"],
                        "content_preview": row["content_preview"] + ("..." if len(row["content_preview"]) >= 500 else ""),
                        "tags": row["tags"],
                        "created_at": row["created_at"].isoformat()
                    })

                return [TextContent(
                    type="text",
                    text=json.dumps({"outputs": results, "count": len(results)}, indent=2)
                )]

        elif name == "get_output_by_id":
            async with p.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM agent_outputs WHERE id = $1
                """, arguments["id"])

                if not row:
                    return [TextContent(type="text", text=json.dumps({"error": "Output not found"}))]

                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "id": row["id"],
                        "agent_name": row["agent_name"],
                        "output_type": row["output_type"],
                        "title": row["title"],
                        "content": row["content"],
                        "tags": row["tags"],
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                        "created_at": row["created_at"].isoformat(),
                        "updated_at": row["updated_at"].isoformat()
                    }, indent=2)
                )]

        elif name == "delete_output":
            async with p.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM agent_outputs WHERE id = $1
                """, arguments["id"])

                deleted = result.split()[-1] != "0"
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "success": deleted,
                        "message": f"Output {arguments['id']} deleted" if deleted else "Output not found"
                    })
                )]

        elif name == "start_execution":
            async with p.acquire() as conn:
                metadata = arguments.get("metadata", {})

                row = await conn.fetchrow("""
                    INSERT INTO agent_executions
                    (agent_name, input_summary, metadata)
                    VALUES ($1, $2, $3)
                    RETURNING id, started_at
                """,
                    arguments["agent_name"],
                    arguments.get("input_summary"),
                    json.dumps(metadata)
                )

                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "execution_id": row["id"],
                        "started_at": row["started_at"].isoformat(),
                        "message": f"Execution started with ID {row['id']}"
                    }, indent=2)
                )]

        elif name == "complete_execution":
            async with p.acquire() as conn:
                row = await conn.fetchrow("""
                    UPDATE agent_executions
                    SET status = $2,
                        completed_at = NOW(),
                        duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at)),
                        output_summary = $3,
                        error_message = $4
                    WHERE id = $1
                    RETURNING id, status, duration_seconds
                """,
                    arguments["execution_id"],
                    arguments["status"],
                    arguments.get("output_summary"),
                    arguments.get("error_message")
                )

                if not row:
                    return [TextContent(type="text", text=json.dumps({"error": "Execution not found"}))]

                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "success": True,
                        "execution_id": row["id"],
                        "status": row["status"],
                        "duration_seconds": round(row["duration_seconds"], 2) if row["duration_seconds"] else None
                    }, indent=2)
                )]

        elif name == "get_executions":
            async with p.acquire() as conn:
                conditions = []
                params = []
                param_idx = 1

                if arguments.get("agent_name"):
                    conditions.append(f"agent_name = ${param_idx}")
                    params.append(arguments["agent_name"])
                    param_idx += 1

                if arguments.get("status"):
                    conditions.append(f"status = ${param_idx}")
                    params.append(arguments["status"])
                    param_idx += 1

                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                limit = min(arguments.get("limit", 20), 100)

                rows = await conn.fetch(f"""
                    SELECT id, agent_name, status, started_at, completed_at,
                           duration_seconds, input_summary, output_summary, error_message
                    FROM agent_executions
                    {where_clause}
                    ORDER BY started_at DESC
                    LIMIT {limit}
                """, *params)

                results = []
                for row in rows:
                    results.append({
                        "id": row["id"],
                        "agent_name": row["agent_name"],
                        "status": row["status"],
                        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                        "duration_seconds": round(row["duration_seconds"], 2) if row["duration_seconds"] else None,
                        "input_summary": row["input_summary"],
                        "output_summary": row["output_summary"],
                        "error_message": row["error_message"]
                    })

                return [TextContent(
                    type="text",
                    text=json.dumps({"executions": results, "count": len(results)}, indent=2)
                )]

        elif name == "get_stats":
            async with p.acquire() as conn:
                days = arguments.get("days", 30)

                # Output stats
                output_stats = await conn.fetch(f"""
                    SELECT
                        agent_name,
                        output_type,
                        COUNT(*) as count
                    FROM agent_outputs
                    WHERE created_at > NOW() - INTERVAL '{days} days'
                    GROUP BY agent_name, output_type
                    ORDER BY count DESC
                """)

                # Execution stats
                exec_stats = await conn.fetch(f"""
                    SELECT
                        agent_name,
                        status,
                        COUNT(*) as count,
                        AVG(duration_seconds) as avg_duration
                    FROM agent_executions
                    WHERE started_at > NOW() - INTERVAL '{days} days'
                    GROUP BY agent_name, status
                    ORDER BY count DESC
                """)

                # Totals
                totals = await conn.fetchrow("""
                    SELECT
                        (SELECT COUNT(*) FROM agent_outputs) as total_outputs,
                        (SELECT COUNT(*) FROM agent_executions) as total_executions,
                        (SELECT COUNT(DISTINCT agent_name) FROM agent_outputs) as unique_agents
                """)

                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "period_days": days,
                        "totals": {
                            "total_outputs": totals["total_outputs"],
                            "total_executions": totals["total_executions"],
                            "unique_agents": totals["unique_agents"]
                        },
                        "outputs_by_agent_and_type": [
                            {
                                "agent_name": r["agent_name"],
                                "output_type": r["output_type"],
                                "count": r["count"]
                            } for r in output_stats
                        ],
                        "executions_by_agent_and_status": [
                            {
                                "agent_name": r["agent_name"],
                                "status": r["status"],
                                "count": r["count"],
                                "avg_duration_seconds": round(r["avg_duration"], 2) if r["avg_duration"] else None
                            } for r in exec_stats
                        ]
                    }, indent=2)
                )]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e), "type": type(e).__name__})
        )]


async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
