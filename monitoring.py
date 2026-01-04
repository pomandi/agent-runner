"""
Langfuse Monitoring Client for Claude Agent SDK

Integrates with self-hosted Langfuse v3 for tracing and observability.
Uses the @observe decorator pattern for automatic trace/span management.

Usage:
    from monitoring import LangfuseClient, observe_agent, observe_tool

    @observe_agent
    async def my_agent(task: str):
        result = await some_tool()
        return result

    # Or use client directly:
    client = LangfuseClient()
    await client.trace_agent("agent-name", "task", my_function)

Environment Variables:
    LANGFUSE_HOST - Langfuse server URL (default: https://langfuse.pomandi.com)
    LANGFUSE_PUBLIC_KEY - Project public key
    LANGFUSE_SECRET_KEY - Project secret key
"""

import os
import logging
from typing import Optional, Dict, Any, Callable
from functools import wraps

logger = logging.getLogger('monitoring')

# Lazy initialization
_langfuse_initialized = False
_langfuse_available = False


def _init_langfuse() -> bool:
    """Initialize Langfuse client lazily."""
    global _langfuse_initialized, _langfuse_available

    if _langfuse_initialized:
        return _langfuse_available

    _langfuse_initialized = True

    try:
        # Check for required env vars
        host = os.getenv('LANGFUSE_HOST', 'https://langfuse.pomandi.com')
        public_key = os.getenv('LANGFUSE_PUBLIC_KEY')
        secret_key = os.getenv('LANGFUSE_SECRET_KEY')

        if not public_key or not secret_key:
            logger.warning("Langfuse keys not set (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)")
            _langfuse_available = False
            return False

        # Import and configure
        from langfuse import Langfuse

        # Initialize the singleton client
        Langfuse(
            host=host,
            public_key=public_key,
            secret_key=secret_key,
        )

        _langfuse_available = True
        logger.info(f"Langfuse initialized: {host}")
        return True

    except ImportError:
        logger.warning("langfuse package not installed. Run: pip install langfuse")
        _langfuse_available = False
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        _langfuse_available = False
        return False


def observe_agent(func: Callable = None, *, name: str = None):
    """
    Decorator to observe agent execution as a trace.

    Usage:
        @observe_agent
        async def my_agent(task: str):
            ...

        @observe_agent(name="custom-name")
        async def my_agent(task: str):
            ...
    """
    def decorator(f):
        if not _init_langfuse() or not _langfuse_available:
            return f  # Return original function if Langfuse not available

        from langfuse import observe
        trace_name = name or f.__name__
        return observe(name=trace_name)(f)

    if func is not None:
        return decorator(func)
    return decorator


def observe_tool(func: Callable = None, *, name: str = None):
    """
    Decorator to observe tool calls as spans within a trace.

    Usage:
        @observe_tool
        async def my_tool(param: str):
            ...
    """
    def decorator(f):
        if not _init_langfuse() or not _langfuse_available:
            return f

        from langfuse import observe
        span_name = name or f.__name__
        return observe(name=span_name)(f)

    if func is not None:
        return decorator(func)
    return decorator


class LangfuseClient:
    """
    Client wrapper for Langfuse operations.

    Provides a simpler interface for manual trace management
    when decorators aren't suitable.
    """

    def __init__(self):
        """Initialize the Langfuse client."""
        self.enabled = _init_langfuse()
        self._current_trace_name = None

    async def start_trace(
        self,
        agent_name: str,
        task: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Start a trace context. Note: In Langfuse v3, traces are
        typically created via @observe decorator. This method
        stores context for logging purposes.

        Returns:
            Trace name or None if disabled
        """
        if not self.enabled:
            return None

        self._current_trace_name = agent_name
        logger.info(f"Langfuse trace context: {agent_name}")
        return agent_name

    async def add_span(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        span_type: str = 'tool_call'
    ) -> Optional[str]:
        """
        Log a span. In v3, spans are created via @observe decorator.
        This method logs for informational purposes.

        Returns:
            Span name or None if disabled
        """
        if not self.enabled:
            return None

        logger.debug(f"Langfuse span: {name} (type={span_type})")
        return name

    async def complete_span(
        self,
        span_id: str,
        output_data: Optional[Dict[str, Any]] = None,
        status: str = 'completed',
        error_message: Optional[str] = None
    ) -> bool:
        """
        Complete a span. In v3, spans auto-complete when function returns.
        """
        if not self.enabled:
            return False

        logger.debug(f"Langfuse span complete: {span_id} ({status})")
        return True

    async def complete_trace(
        self,
        status: str = 'completed',
        cost_usd: Optional[float] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        output_summary: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Complete the trace and flush data to Langfuse.
        """
        if not self.enabled:
            return False

        try:
            from langfuse import get_client
            client = get_client()
            client.flush()
            logger.info(f"Langfuse trace flushed: {self._current_trace_name} ({status})")
            return True
        except Exception as e:
            logger.error(f"Failed to flush Langfuse: {e}")
            return False

    async def close(self):
        """Flush and close the client."""
        if self.enabled:
            try:
                from langfuse import get_client
                get_client().flush()
            except Exception as e:
                logger.error(f"Failed to flush Langfuse: {e}")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Backwards compatibility alias
DashboardClient = LangfuseClient


async def create_monitoring_client() -> LangfuseClient:
    """Create and return a LangfuseClient instance."""
    return LangfuseClient()
