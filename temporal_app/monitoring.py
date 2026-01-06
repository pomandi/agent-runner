"""
Langfuse monitoring integration for Temporal workflows.

Provides decorators and utilities to automatically track:
- Workflow executions as Langfuse traces
- Activity executions as spans
- Retry attempts and failures
- Cost tracking for AI activities
"""
import os
import logging
import sys
from typing import Optional, Dict, Any, Callable
from functools import wraps
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from temporalio import workflow, activity

logger = logging.getLogger(__name__)

# Try to import Langfuse
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    logger.warning("Langfuse not available - monitoring disabled")
    LANGFUSE_AVAILABLE = False

# Global Langfuse client
_langfuse_client = None


def _get_langfuse():
    """Get or create Langfuse client singleton."""
    global _langfuse_client

    if _langfuse_client is not None:
        return _langfuse_client

    if not LANGFUSE_AVAILABLE:
        return None

    try:
        host = os.getenv('LANGFUSE_HOST', 'https://langfuse.pomandi.com')
        public_key = os.getenv('LANGFUSE_PUBLIC_KEY')
        secret_key = os.getenv('LANGFUSE_SECRET_KEY')

        if not public_key or not secret_key:
            logger.warning("Langfuse credentials not configured")
            return None

        _langfuse_client = Langfuse(
            host=host,
            public_key=public_key,
            secret_key=secret_key,
        )

        logger.info(f"Langfuse monitoring enabled: {host}")
        return _langfuse_client

    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        return None


class WorkflowMonitor:
    """
    Monitor Temporal workflows with Langfuse traces.

    Automatically tracks:
    - Workflow start/completion
    - Input parameters
    - Output results
    - Execution time
    - Errors and failures
    """

    def __init__(self, workflow_name: str, workflow_id: str, run_id: str):
        """
        Initialize workflow monitor.

        Args:
            workflow_name: Workflow type name
            workflow_id: Unique workflow execution ID
            run_id: Temporal run ID
        """
        self.langfuse = _get_langfuse()
        self.enabled = self.langfuse is not None
        self.workflow_name = workflow_name
        self.workflow_id = workflow_id
        self.run_id = run_id
        self._trace = None
        self._start_time = datetime.utcnow()

    def start(self, input_data: Dict[str, Any]) -> Optional[str]:
        """Start workflow trace."""
        if not self.enabled:
            return None

        try:
            self._trace = self.langfuse.start_span(
                name=f"workflow:{self.workflow_name}",
                input=input_data,
                metadata={
                    "workflow_id": self.workflow_id,
                    "run_id": self.run_id,
                    "type": "temporal_workflow",
                },
            )

            trace_id = self._trace.trace_id if hasattr(self._trace, 'trace_id') else None
            logger.info(f"Workflow trace started: {self.workflow_name} (trace_id={trace_id})")
            return trace_id

        except Exception as e:
            logger.error(f"Failed to start workflow trace: {e}")
            return None

    def complete(
        self,
        output_data: Optional[Dict[str, Any]] = None,
        status: str = 'completed',
        error: Optional[str] = None,
        cost_usd: Optional[float] = None
    ):
        """Complete workflow trace."""
        if not self.enabled or not self._trace:
            return

        try:
            duration_ms = (datetime.utcnow() - self._start_time).total_seconds() * 1000

            metadata = {
                "status": status,
                "duration_ms": duration_ms,
            }
            if cost_usd:
                metadata["cost_usd"] = cost_usd

            self._trace.update(
                output=output_data or {"status": status},
                level="ERROR" if error else "DEFAULT",
                status_message=error,
                metadata=metadata,
            )
            self._trace.end()

            # Flush to send data
            self.langfuse.flush()

            logger.info(
                f"Workflow trace completed: {self.workflow_name} "
                f"(status={status}, duration={duration_ms:.0f}ms, cost=${cost_usd or 0:.4f})"
            )

        except Exception as e:
            logger.error(f"Failed to complete workflow trace: {e}")

    def add_activity_span(
        self,
        activity_name: str,
        input_data: Optional[Dict[str, Any]] = None
    ) -> 'ActivitySpan':
        """
        Add an activity span to the workflow trace.

        Returns:
            ActivitySpan context manager
        """
        return ActivitySpan(self, activity_name, input_data)


class ActivitySpan:
    """
    Context manager for tracking individual activity execution.

    Usage:
        with monitor.add_activity_span("get_photo", {"brand": "pomandi"}) as span:
            result = await get_photo()
            span.complete({"photo_key": result})
    """

    def __init__(
        self,
        workflow_monitor: WorkflowMonitor,
        activity_name: str,
        input_data: Optional[Dict[str, Any]] = None
    ):
        """Initialize activity span."""
        self.workflow_monitor = workflow_monitor
        self.activity_name = activity_name
        self.input_data = input_data or {}
        self._span = None
        self._start_time = datetime.utcnow()

    def __enter__(self):
        """Start activity span."""
        if not self.workflow_monitor.enabled or not self.workflow_monitor._trace:
            return self

        try:
            self._span = self.workflow_monitor._trace.start_span(
                name=f"activity:{self.activity_name}",
                input=self.input_data,
                metadata={
                    "type": "temporal_activity",
                },
            )
            logger.debug(f"Activity span started: {self.activity_name}")
        except Exception as e:
            logger.error(f"Failed to start activity span: {e}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End activity span."""
        if exc_type:
            # Activity failed
            self.complete(
                status='failed',
                error=str(exc_val)
            )
        else:
            # Auto-complete if not already done
            if self._span:
                self.complete()

    def complete(
        self,
        output_data: Optional[Dict[str, Any]] = None,
        status: str = 'completed',
        error: Optional[str] = None,
        cost_usd: Optional[float] = None
    ):
        """Complete the activity span."""
        if not self._span:
            return

        try:
            duration_ms = (datetime.utcnow() - self._start_time).total_seconds() * 1000

            metadata = {
                "status": status,
                "duration_ms": duration_ms,
            }
            if cost_usd:
                metadata["cost_usd"] = cost_usd

            self._span.update(
                output=output_data or {"status": status},
                level="ERROR" if error else "DEFAULT",
                status_message=error,
                metadata=metadata,
            )
            self._span.end()

            logger.debug(
                f"Activity span completed: {self.activity_name} "
                f"(status={status}, duration={duration_ms:.0f}ms)"
            )

        except Exception as e:
            logger.error(f"Failed to complete activity span: {e}")
        finally:
            self._span = None


def observe_workflow(workflow_class):
    """
    Decorator to automatically monitor a Temporal workflow.

    Usage:
        @workflow.defn
        @observe_workflow
        class MyWorkflow:
            @workflow.run
            async def run(self, param: str) -> dict:
                ...
    """
    if not LANGFUSE_AVAILABLE:
        return workflow_class

    original_run = workflow_class.run

    @wraps(original_run)
    async def monitored_run(self, *args, **kwargs):
        """Wrapped run method with monitoring."""
        # Get workflow info
        info = workflow.info()
        workflow_name = workflow_class.__name__
        workflow_id = info.workflow_id
        run_id = info.run_id

        # Create monitor
        monitor = WorkflowMonitor(workflow_name, workflow_id, run_id)

        # Store monitor in workflow instance for activities to access
        self._workflow_monitor = monitor

        # Prepare input data
        input_data = {
            "args": args,
            "kwargs": kwargs,
        }

        # Start trace
        monitor.start(input_data)

        try:
            # Execute workflow
            result = await original_run(self, *args, **kwargs)

            # Extract cost if available
            cost_usd = result.get('cost_usd') if isinstance(result, dict) else None

            # Complete trace
            monitor.complete(
                output_data={"result": result} if result else None,
                status='completed',
                cost_usd=cost_usd
            )

            return result

        except Exception as e:
            # Workflow failed
            monitor.complete(
                status='failed',
                error=str(e)
            )
            raise

    workflow_class.run = monitored_run
    return workflow_class


def observe_activity(activity_func):
    """
    Decorator to automatically monitor a Temporal activity.

    Usage:
        @activity.defn
        @observe_activity
        async def my_activity(param: str) -> dict:
            ...

    Note: This creates a standalone span if not within a monitored workflow.
    """
    if not LANGFUSE_AVAILABLE:
        return activity_func

    @wraps(activity_func)
    async def monitored_activity(*args, **kwargs):
        """Wrapped activity with monitoring."""
        activity_name = activity_func.__name__

        # Get activity info
        info = activity.info()

        # Try to get workflow monitor from workflow context
        # (This would require passing it through - simplified version creates standalone span)

        langfuse = _get_langfuse()
        if not langfuse:
            return await activity_func(*args, **kwargs)

        # Create standalone trace for activity
        trace = langfuse.start_span(
            name=f"activity:{activity_name}",
            input={
                "args": args,
                "kwargs": kwargs,
            },
            metadata={
                "type": "temporal_activity",
                "workflow_id": info.workflow_id,
                "activity_id": info.activity_id,
            },
        )

        start_time = datetime.utcnow()

        try:
            # Execute activity
            result = await activity_func(*args, **kwargs)

            # Complete trace
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            trace.update(
                output={"result": result} if result else None,
                metadata={
                    "status": "completed",
                    "duration_ms": duration_ms,
                },
            )
            trace.end()
            langfuse.flush()

            return result

        except Exception as e:
            # Activity failed
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            trace.update(
                level="ERROR",
                status_message=str(e),
                metadata={
                    "status": "failed",
                    "duration_ms": duration_ms,
                },
            )
            trace.end()
            langfuse.flush()
            raise

    return monitored_activity
