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


# =============================================================================
# VALIDATOR GRAPH ACTIVITY
# =============================================================================

@activity.defn
async def run_validator_graph(
    raw_data: Dict[str, Any],
    brand: str = "pomandi",
    days: int = 7
) -> Dict[str, Any]:
    """
    Run data validator LangGraph workflow.

    Validates collected data through:
    - Duplicate detection
    - Cross-source verification
    - Anomaly detection
    - Quality score calculation

    Args:
        raw_data: Collected data from all sources
        brand: Brand name ("pomandi" or "costume")
        days: Number of days analyzed

    Returns:
        Validation result with score, anomalies, and proceed decision
    """
    activity.logger.info(
        f"Running validator graph: brand={brand}, sources={len(raw_data)}"
    )

    start_time = time.time()
    status = "completed"

    try:
        from langgraph_agents import DataValidatorGraph

        graph = DataValidatorGraph()
        await graph.initialize()

        result = await graph.validate(raw_data, brand=brand, days=days)

        duration = time.time() - start_time

        activity.logger.info(
            f"Validation complete: score={result['validation_score']:.0%}, "
            f"proceed={result['proceed_to_analysis']}, "
            f"anomalies={len(result.get('anomalies', []))}"
        )

        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="validator_graph",
                status=status
            ).inc()

        await graph.close()

        return {
            "validation_score": result.get("validation_score", 0.0),
            "proceed_to_analysis": result.get("proceed_to_analysis", False),
            "duplicates": result.get("duplicates", [])[:10],
            "anomalies": result.get("anomalies", [])[:20],
            "cross_source_conflicts": result.get("cross_source_conflicts", [])[:10],
            "requires_human_review": result.get("requires_human_review", []),
            "validation_report": result.get("validation_report", ""),
            "dedup_stats": result.get("dedup_stats", {}),
            "errors": list(set(result.get("errors", [])))[:20],
            "duration_seconds": duration
        }

    except Exception as e:
        status = "failed"
        activity.logger.error(f"Validator graph failed: {str(e)}")
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="validator_graph",
                status=status
            ).inc()
        raise


# =============================================================================
# ACTION PLANNER GRAPH ACTIVITY
# =============================================================================

@activity.defn
async def run_action_planner_graph(
    validated_data: Dict[str, Any],
    analysis_reports: Dict[str, Any],
    brand: str = "pomandi"
) -> Dict[str, Any]:
    """
    Run action planner LangGraph workflow.

    Generates actionable recommendations based on validated data
    and analysis reports.

    Args:
        validated_data: Output from validator graph
        analysis_reports: Analysis reports from daily analytics
        brand: Brand name

    Returns:
        Action plan with prioritized recommendations
    """
    activity.logger.info(
        f"Running action planner graph: brand={brand}, "
        f"validation_score={validated_data.get('validation_score', 0):.0%}"
    )

    start_time = time.time()
    status = "completed"

    try:
        from langgraph_agents import ActionPlannerGraph

        graph = ActionPlannerGraph()
        await graph.initialize()

        result = await graph.plan_actions(
            validated_data=validated_data,
            analysis_reports=analysis_reports,
            brand=brand
        )

        duration = time.time() - start_time

        actions = result.get("actions", [])
        activity.logger.info(
            f"Action planning complete: actions={len(actions)}, "
            f"auto={sum(1 for a in actions if a.get('action_type') == 'automated')}, "
            f"manual={sum(1 for a in actions if a.get('action_type') == 'manual')}"
        )

        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="action_planner_graph",
                status=status
            ).inc()

        await graph.close()

        return {
            "actions": actions[:20],  # Max 20 actions
            "action_count": len(actions),
            "auto_actions": [a for a in actions if a.get("action_type") == "automated"][:10],
            "approval_required": [a for a in actions if a.get("action_type") == "requires_approval"][:10],
            "manual_actions": [a for a in actions if a.get("action_type") == "manual"][:10],
            "plan_saved": result.get("plan_saved", False),
            "plan_path": result.get("plan_path"),
            "errors": list(set(result.get("errors", [])))[:20],
            "duration_seconds": duration
        }

    except Exception as e:
        status = "failed"
        activity.logger.error(f"Action planner graph failed: {str(e)}")
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="action_planner_graph",
                status=status
            ).inc()
        raise


# =============================================================================
# EXECUTOR GRAPH ACTIVITY
# =============================================================================

@activity.defn
async def run_executor_graph(
    actions_to_execute: list,
    brand: str = "pomandi",
    dry_run: bool = True  # Default to dry_run for safety
) -> Dict[str, Any]:
    """
    Run action executor LangGraph workflow.

    Executes approved actions via MCP tool calls with safety checks.

    Args:
        actions_to_execute: List of actions to execute (from action planner)
        brand: Brand name
        dry_run: If True, simulate execution without actual changes

    Returns:
        Execution results with success/failure status
    """
    activity.logger.info(
        f"Running executor graph: brand={brand}, "
        f"actions={len(actions_to_execute)}, dry_run={dry_run}"
    )

    start_time = time.time()
    status = "completed"

    try:
        from langgraph_agents import ActionExecutorGraph

        graph = ActionExecutorGraph()
        await graph.initialize()

        result = await graph.execute_actions(
            actions=actions_to_execute,
            brand=brand,
            dry_run=dry_run
        )

        duration = time.time() - start_time

        activity.logger.info(
            f"Execution complete: successful={result.get('successful_count', 0)}, "
            f"failed={result.get('failed_count', 0)}, "
            f"skipped={result.get('skipped_count', 0)}"
        )

        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="executor_graph",
                status=status
            ).inc()

        await graph.close()

        return {
            "successful_count": result.get("successful_count", 0),
            "failed_count": result.get("failed_count", 0),
            "skipped_count": result.get("skipped_count", 0),
            "execution_results": result.get("execution_results", [])[:20],
            "safety_checks_passed": result.get("safety_checks_passed", False),
            "safety_issues": result.get("safety_issues", [])[:10],
            "rollback_results": result.get("rollback_results", [])[:10],
            "execution_log_path": result.get("execution_log_path"),
            "notification_sent": result.get("notification_sent", False),
            "dry_run": dry_run,
            "errors": list(set(result.get("errors", [])))[:20],
            "duration_seconds": duration
        }

    except Exception as e:
        status = "failed"
        activity.logger.error(f"Executor graph failed: {str(e)}")
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="executor_graph",
                status=status
            ).inc()
        raise


# =============================================================================
# FEEDBACK COLLECTOR GRAPH ACTIVITY
# =============================================================================

@activity.defn
async def run_feedback_collector_graph(
    brand: str = "pomandi"
) -> Dict[str, Any]:
    """
    Run feedback collector LangGraph workflow.

    Collects T+1, T+3, T+7 feedback on executed actions to measure
    impact and generate learnings.

    Args:
        brand: Brand name

    Returns:
        Feedback results with success/failure analysis and learnings
    """
    activity.logger.info(f"Running feedback collector graph: brand={brand}")

    start_time = time.time()
    status = "completed"

    try:
        from langgraph_agents import FeedbackCollectorGraph

        graph = FeedbackCollectorGraph()
        await graph.initialize()

        result = await graph.collect_feedback(brand=brand)

        duration = time.time() - start_time

        activity.logger.info(
            f"Feedback collection complete: successful={result.get('successful_count', 0)}, "
            f"failed={result.get('failed_count', 0)}, "
            f"pending={result.get('pending_count', 0)}"
        )

        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="feedback_collector_graph",
                status=status
            ).inc()

        await graph.close()

        return {
            "successful_count": result.get("successful_count", 0),
            "failed_count": result.get("failed_count", 0),
            "pending_count": result.get("pending_count", 0),
            "feedbacks": result.get("feedbacks", [])[:20],
            "learnings_generated": result.get("learnings_generated", [])[:10],
            "feedback_saved": result.get("feedback_saved", False),
            "memory_saved": result.get("memory_saved", False),
            "report_path": result.get("report_path"),
            "errors": list(set(result.get("errors", [])))[:20],
            "duration_seconds": duration
        }

    except Exception as e:
        status = "failed"
        activity.logger.error(f"Feedback collector graph failed: {str(e)}")
        if METRICS_AVAILABLE:
            WorkflowMetrics.activity_execution_total.labels(
                activity_name="feedback_collector_graph",
                status=status
            ).inc()
        raise


# Activity list for worker registration
LANGGRAPH_ACTIVITIES = [
    run_invoice_matcher_graph,
    run_feed_publisher_graph,
    run_daily_analytics_graph,
    run_validator_graph,
    run_action_planner_graph,
    run_executor_graph,
    run_feedback_collector_graph
]
