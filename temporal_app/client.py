"""
Temporal client singleton.
"""
import os
from temporalio.client import Client
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_client: Optional[Client] = None

async def get_temporal_client() -> Client:
    """Get or create Temporal client."""
    global _client

    if _client is None:
        host = os.getenv('TEMPORAL_HOST', 'localhost:7233')
        namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')

        logger.info(f"Connecting to Temporal at {host}, namespace: {namespace}")

        _client = await Client.connect(
            host,
            namespace=namespace,
        )

        logger.info("Temporal client connected successfully")

    return _client

async def close_temporal_client():
    """Close Temporal client."""
    global _client
    if _client:
        await _client.close()
        _client = None
        logger.info("Temporal client closed")
