"""
Langfuse Monitoring Client for Claude Agent SDK

Integrates with self-hosted Langfuse v3 for tracing and observability.
Creates real traces and spans using Langfuse's programmatic API.

Usage:
    from monitoring import LangfuseClient

    client = LangfuseClient()
    await client.start_trace("agent-name", "task description")
    span_id = await client.add_span("tool-name", {"input": "data"})
    await client.complete_span(span_id, {"output": "result"})
    await client.complete_trace(status="completed", cost_usd=0.01)

Environment Variables:
    LANGFUSE_HOST - Langfuse server URL (default: https://langfuse.pomandi.com)
    LANGFUSE_PUBLIC_KEY - Project public key
    LANGFUSE_SECRET_KEY - Project secret key
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from functools import wraps

logger = logging.getLogger('monitoring')

# Global Langfuse client
_langfuse_client = None
_langfuse_available = False


def _get_langfuse():
    """Get or create Langfuse client."""
    global _langfuse_client, _langfuse_available

    if _langfuse_client is not None:
        return _langfuse_client

    try:
        host = os.getenv('LANGFUSE_HOST', 'https://langfuse.pomandi.com')
        public_key = os.getenv('LANGFUSE_PUBLIC_KEY')
        secret_key = os.getenv('LANGFUSE_SECRET_KEY')

        if not public_key or not secret_key:
            logger.warning("Langfuse keys not set (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)")
            _langfuse_available = False
            return None

        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            host=host,
            public_key=public_key,
            secret_key=secret_key,
        )

        _langfuse_available = True
        logger.info(f"Langfuse initialized: {host}")
        return _langfuse_client

    except ImportError:
        logger.warning("langfuse package not installed. Run: pip install langfuse")
        _langfuse_available = False
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        _langfuse_available = False
        return None


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
        langfuse = _get_langfuse()
        if not langfuse:
            return f

        from langfuse.decorators import observe
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
        langfuse = _get_langfuse()
        if not langfuse:
            return f

        from langfuse.decorators import observe
        span_name = name or f.__name__
        return observe(name=span_name)(f)

    if func is not None:
        return decorator(func)
    return decorator


class LangfuseClient:
    """
    Client for creating Langfuse traces and spans programmatically.

    This is the preferred way to track agent executions when you need
    manual control over trace lifecycle.
    """

    def __init__(self):
        """Initialize the Langfuse client."""
        self.langfuse = _get_langfuse()
        self.enabled = self.langfuse is not None
        self._current_trace = None
        self._spans: Dict[str, Any] = {}
        self._span_counter = 0

    async def start_trace(
        self,
        agent_name: str,
        task: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Start a new trace for an agent execution.

        Args:
            agent_name: Name of the agent (becomes trace name)
            task: The task/prompt given to the agent
            metadata: Additional metadata to attach

        Returns:
            Trace ID or None if disabled
        """
        if not self.enabled or not self.langfuse:
            return None

        try:
            self._current_trace = self.langfuse.trace(
                name=agent_name,
                input={"task": task},
                metadata=metadata or {},
            )
            trace_id = self._current_trace.id
            logger.info(f"Langfuse trace started: {agent_name} (id={trace_id})")
            return trace_id
        except Exception as e:
            logger.error(f"Failed to start Langfuse trace: {e}")
            return None

    async def add_span(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        span_type: str = 'tool_call'
    ) -> Optional[str]:
        """
        Add a span (tool call) to the current trace.

        Args:
            name: Span name (usually tool name)
            input_data: Input data for the span
            span_type: Type of span (default: tool_call)

        Returns:
            Span ID or None if disabled
        """
        if not self.enabled or not self._current_trace:
            return None

        try:
            self._span_counter += 1
            span_id = f"span_{self._span_counter}"

            span = self._current_trace.span(
                name=name,
                input=input_data or {},
                metadata={"type": span_type},
            )

            self._spans[span_id] = span
            logger.info(f"Langfuse span added: {name} (id={span_id})")
            return span_id
        except Exception as e:
            logger.error(f"Failed to add Langfuse span: {e}")
            return None

    async def complete_span(
        self,
        span_id: str,
        output_data: Optional[Dict[str, Any]] = None,
        status: str = 'completed',
        error_message: Optional[str] = None
    ) -> bool:
        """
        Complete a span with output data.

        Args:
            span_id: Span ID from add_span
            output_data: Output data from the tool
            status: Status (completed, error)
            error_message: Error message if status is error

        Returns:
            True if successful
        """
        if not self.enabled or span_id not in self._spans:
            return False

        try:
            span = self._spans[span_id]
            span.end(
                output=output_data or {},
                level="ERROR" if error_message else "DEFAULT",
                status_message=error_message,
            )
            del self._spans[span_id]
            logger.debug(f"Langfuse span completed: {span_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to complete Langfuse span: {e}")
            return False

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
        Complete the current trace and flush to Langfuse.

        Args:
            status: Final status (completed, failed)
            cost_usd: Total cost in USD
            input_tokens: Total input tokens
            output_tokens: Total output tokens
            output_summary: Summary of the output
            error_message: Error message if failed

        Returns:
            True if successful
        """
        if not self.enabled or not self._current_trace:
            return False

        try:
            # Close any open spans
            for span_id in list(self._spans.keys()):
                await self.complete_span(span_id, {"status": "auto-closed"})

            # Build output dict
            output = {}
            if output_summary:
                output["summary"] = output_summary
            if error_message:
                output["error"] = error_message

            # Build usage dict for cost tracking
            usage = {}
            if input_tokens:
                usage["input"] = input_tokens
            if output_tokens:
                usage["output"] = output_tokens
            if cost_usd:
                usage["total_cost"] = cost_usd

            # Update trace with final data
            self._current_trace.update(
                output=output if output else {"status": status},
                level="ERROR" if error_message else "DEFAULT",
                metadata={
                    "status": status,
                    "cost_usd": cost_usd,
                } if cost_usd else {"status": status},
            )

            # Flush to send data
            self.langfuse.flush()
            logger.info(f"Langfuse trace completed: {status} (cost=${cost_usd or 0:.4f})")

            self._current_trace = None
            return True

        except Exception as e:
            logger.error(f"Failed to complete Langfuse trace: {e}")
            return False

    async def close(self):
        """Flush and close the client."""
        if self.enabled and self.langfuse:
            try:
                self.langfuse.flush()
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
