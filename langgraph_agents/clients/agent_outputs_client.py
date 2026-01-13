"""
Agent Outputs Client
====================

Async client for saving agent outputs to the agent-outputs database.
Uses direct PostgreSQL connection for reliability.

Usage:
    from langgraph_agents.clients import save_to_agent_outputs

    saved = await save_to_agent_outputs(
        agent_name="daily-analytics",
        output_type="report",
        title="Daily Analytics Report",
        content=json.dumps(data),
        tags=["pomandi", "daily"],
        metadata={"brand": "pomandi", "date": "2026-01-13"}
    )
"""

import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)

# Database connection settings from environment
DB_HOST = os.getenv("DB_HOST", "46.224.117.155")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "postgres")


class AgentOutputsClient:
    """
    Async client for agent-outputs database.

    Provides methods to save and retrieve agent outputs.
    """

    def __init__(self):
        """Initialize client with database connection settings."""
        self.db_config = {
            "host": DB_HOST,
            "port": int(DB_PORT),
            "user": DB_USER,
            "password": DB_PASSWORD,
            "database": DB_NAME
        }
        self._pool = None
        logger.info(
            "agent_outputs_client_init",
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME
        )

    async def _ensure_pool(self):
        """Ensure database connection pool is initialized."""
        if self._pool is None:
            try:
                import asyncpg
                self._pool = await asyncpg.create_pool(
                    host=self.db_config["host"],
                    port=self.db_config["port"],
                    user=self.db_config["user"],
                    password=self.db_config["password"],
                    database=self.db_config["database"],
                    min_size=1,
                    max_size=5,
                    command_timeout=30
                )
                logger.info("agent_outputs_pool_created")
            except Exception as e:
                logger.error("agent_outputs_pool_error", error=str(e))
                raise

    async def save_output(
        self,
        agent_name: str,
        output_type: str,
        content: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Save an agent output to the database.

        Args:
            agent_name: Name of the agent producing the output
            output_type: Type of output (report, analysis, data, error, summary, recommendation, log)
            content: The actual content (text, JSON string, markdown, etc.)
            title: Optional title/subject of the output
            tags: Optional tags for categorization
            metadata: Optional additional metadata as dict

        Returns:
            Result dict with success status and output ID
        """
        await self._ensure_pool()

        try:
            async with self._pool.acquire() as conn:
                # Insert the output
                row = await conn.fetchrow(
                    """
                    INSERT INTO agent_outputs
                    (agent_name, output_type, title, content, tags, metadata, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id, created_at
                    """,
                    agent_name,
                    output_type,
                    title,
                    content,
                    tags or [],
                    json.dumps(metadata) if metadata else "{}",
                    datetime.utcnow()
                )

                output_id = row["id"]
                created_at = row["created_at"]

                logger.info(
                    "agent_output_saved",
                    id=output_id,
                    agent_name=agent_name,
                    output_type=output_type,
                    title=title
                )

                return {
                    "success": True,
                    "id": output_id,
                    "created_at": created_at.isoformat() if created_at else None
                }

        except Exception as e:
            logger.error(
                "agent_output_save_error",
                agent_name=agent_name,
                error=str(e)
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def get_outputs(
        self,
        agent_name: Optional[str] = None,
        output_type: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Retrieve agent outputs with optional filters.

        Args:
            agent_name: Filter by agent name
            output_type: Filter by output type
            days: Only return outputs from last N days
            limit: Maximum number of results

        Returns:
            List of output records
        """
        await self._ensure_pool()

        try:
            async with self._pool.acquire() as conn:
                # Build query with filters
                conditions = []
                params = []
                param_num = 1

                if agent_name:
                    conditions.append(f"agent_name = ${param_num}")
                    params.append(agent_name)
                    param_num += 1

                if output_type:
                    conditions.append(f"output_type = ${param_num}")
                    params.append(output_type)
                    param_num += 1

                if days:
                    conditions.append(f"created_at >= NOW() - INTERVAL '{days} days'")

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                query = f"""
                    SELECT id, agent_name, output_type, title, content, tags, metadata, created_at
                    FROM agent_outputs
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ${param_num}
                """
                params.append(limit)

                rows = await conn.fetch(query, *params)

                return [
                    {
                        "id": row["id"],
                        "agent_name": row["agent_name"],
                        "output_type": row["output_type"],
                        "title": row["title"],
                        "content": row["content"],
                        "tags": row["tags"],
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error("agent_output_get_error", error=str(e))
            return []

    async def close(self):
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.debug("agent_outputs_pool_closed")


# Singleton instance
_client: Optional[AgentOutputsClient] = None


def get_agent_outputs_client() -> AgentOutputsClient:
    """
    Get the singleton Agent-Outputs client instance.

    Returns:
        AgentOutputsClient instance
    """
    global _client
    if _client is None:
        _client = AgentOutputsClient()
    return _client


async def save_to_agent_outputs(
    agent_name: str,
    output_type: str,
    content: str,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Convenience function to save to agent-outputs database.

    Args:
        agent_name: Name of the agent
        output_type: Type of output (report, analysis, data, error, summary, recommendation, log)
        content: Content to save
        title: Optional title
        tags: Optional tags
        metadata: Optional metadata dict

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        client = get_agent_outputs_client()
        result = await client.save_output(
            agent_name=agent_name,
            output_type=output_type,
            content=content,
            title=title,
            tags=tags,
            metadata=metadata
        )

        success = result.get("success", False)

        if success:
            logger.info(
                "agent_outputs_save_success",
                agent_name=agent_name,
                id=result.get("id")
            )
        else:
            logger.error(
                "agent_outputs_save_failed",
                agent_name=agent_name,
                error=result.get("error")
            )

        return success

    except Exception as e:
        logger.error("agent_outputs_save_error", error=str(e), agent_name=agent_name)
        return False
