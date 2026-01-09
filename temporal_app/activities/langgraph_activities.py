"""
LangGraph activities - wrap LangGraph workflows as Temporal activities.

Provides integration between Temporal orchestration and LangGraph agent execution.
"""
from temporalio import activity
from typing import Dict, Any
import logging
import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from temporal_app.monitoring import observe_activity

# Import monitoring metrics
try:
    from monitoring.metrics import WorkflowMetrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)


@activity.defn
async def run_invoice_matcher_graph(
    transaction: Dict[str, Any],
    invoices: list
) -> Dict[str, Any]:
    """
    Run invoice matcher LangGraph workflow.

    Args:
        transaction: Bank transaction to match
        invoices: List of available invoices

    Returns:
        Matching result with decision
    """
    activity.logger.info(
        f"Running invoice matcher graph: transaction_id={transaction.get('id')}, "
        f"invoices_count={len(invoices)}"
    )

    start_time = time.time()
    status = "completed"

    try:
        from langgraph_agents import InvoiceMatcherGraph

        # Create and run graph
        graph = InvoiceMatcherGraph()
        await graph.initialize()

        result = await graph.match(transaction, invoices)

        duration = time.time() - start_time

        activity.logger.info(
            f"Invoice matching complete: matched={result['matched']}, "
            f"confidence={result['confidence']:.2%}, "
            f"decision={result['decision_type']}"
        )

        # Record workflow metrics
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="invoice_matcher_graph",
                status=status
            ).inc()

            WorkflowMetrics.activity_duration.labels(
                activity_name="invoice_matcher_graph"
            ).observe(duration)

        await graph.close()

        return result

    except Exception as e:
        status = "failed"
        duration = time.time() - start_time

        activity.logger.error(f"Invoice matcher graph failed: {str(e)}")

        # Record failure metrics
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="invoice_matcher_graph",
                status=status
            ).inc()

            WorkflowMetrics.activity_duration.labels(
                activity_name="invoice_matcher_graph"
            ).observe(duration)

        raise


@activity.defn
async def run_feed_publisher_graph(
    brand: str,
    platform: str,
    photo_s3_key: str
) -> Dict[str, Any]:
    """
    Run feed publisher LangGraph workflow.

    Args:
        brand: "pomandi" or "costume"
        platform: "facebook" or "instagram"
        photo_s3_key: S3 key for photo

    Returns:
        Publishing result with post IDs
    """
    activity.logger.info(
        f"Running feed publisher graph: brand={brand}, platform={platform}, "
        f"photo={photo_s3_key}"
    )

    start_time = time.time()
    status = "completed"

    try:
        from langgraph_agents import FeedPublisherGraph

        # Create and run graph
        graph = FeedPublisherGraph()
        await graph.initialize()

        result = await graph.publish(brand, platform, photo_s3_key)

        duration = time.time() - start_time

        activity.logger.info(
            f"Feed publishing complete: published={result['published']}, "
            f"quality={result['quality_score']:.2%}, "
            f"requires_approval={result['requires_approval']}"
        )

        # Record workflow metrics
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="feed_publisher_graph",
                status=status
            ).inc()

            WorkflowMetrics.activity_duration.labels(
                activity_name="feed_publisher_graph"
            ).observe(duration)

        await graph.close()

        return result

    except Exception as e:
        status = "failed"
        duration = time.time() - start_time

        activity.logger.error(f"Feed publisher graph failed: {str(e)}")

        # Record failure metrics
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="feed_publisher_graph",
                status=status
            ).inc()

            WorkflowMetrics.activity_duration.labels(
                activity_name="feed_publisher_graph"
            ).observe(duration)

        raise


@activity.defn
async def run_daily_analytics_graph(
    days: int = 7,
    brand: str = "pomandi"
) -> Dict[str, Any]:
    """
    Run daily analytics LangGraph workflow.

    Collects data from 8 sources, analyzes with Claude,
    generates Turkish report, sends to Telegram.

    Args:
        days: Number of days to analyze
        brand: Brand name ("pomandi" or "costume")

    Returns:
        Report result with markdown, insights, delivery status
    """
    activity.logger.info(
        f"Running daily analytics graph: brand={brand}, days={days}"
    )

    start_time = time.time()
    status = "completed"

    try:
        from langgraph_agents import DailyAnalyticsGraph

        # Create and run graph
        graph = DailyAnalyticsGraph()
        await graph.initialize()

        result = await graph.generate_report(days=days, brand=brand)

        duration = time.time() - start_time

        # Get counts before truncating
        error_count = len(result.get('errors', []))
        steps_count = len(result.get('steps_completed', []))

        activity.logger.info(
            f"Daily analytics complete: quality={result['quality_score']:.0%}, "
            f"telegram={result['telegram_sent']}, "
            f"insights={len(result['insights'])}, "
            f"errors={error_count}"
        )

        # Record workflow metrics
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="daily_analytics_graph",
                status=status
            ).inc()

            WorkflowMetrics.activity_duration.labels(
                activity_name="daily_analytics_graph"
            ).observe(duration)

        await graph.close()

        # IMPORTANT: Truncate large lists to avoid gRPC message size limit (4MB)
        # The state uses operator.add which causes exponential growth
        truncated_result = {
            "success": result.get("success", False),
            "brand": result.get("brand", brand),
            "period_days": result.get("period_days", days),
            "report_markdown": result.get("report_markdown", ""),
            "insights": result.get("insights", [])[:20],  # Max 20 insights
            "recommendations": result.get("recommendations", [])[:20],  # Max 20
            "quality_score": result.get("quality_score", 0.0),
            "telegram_sent": result.get("telegram_sent", False),
            "telegram_message_id": result.get("telegram_message_id"),
            # Only include unique errors and limit count
            "errors": list(set(result.get("errors", [])))[:50],
            "error_count": error_count,
            # Only include unique steps and limit count
            "steps_completed": list(set(result.get("steps_completed", [])))[:50],
            "steps_count": steps_count,
            "regenerate_attempts": result.get("regenerate_attempts", 0),
            "duration_seconds": duration
        }

        return truncated_result

    except Exception as e:
        status = "failed"
        duration = time.time() - start_time

        activity.logger.error(f"Daily analytics graph failed: {str(e)}")

        # Record failure metrics
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="daily_analytics_graph",
                status=status
            ).inc()

            WorkflowMetrics.activity_duration.labels(
                activity_name="daily_analytics_graph"
            ).observe(duration)

        raise


# Activity list for worker registration
LANGGRAPH_ACTIVITIES = [
    run_invoice_matcher_graph,
    run_feed_publisher_graph,
    run_daily_analytics_graph
]
