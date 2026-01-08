"""
LangGraph activities - wrap LangGraph workflows as Temporal activities.

Provides integration between Temporal orchestration and LangGraph agent execution.
"""
from temporalio import activity
from typing import Dict, Any
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from temporal_app.monitoring import observe_activity

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

    try:
        from langgraph_agents import InvoiceMatcherGraph

        # Create and run graph
        graph = InvoiceMatcherGraph()
        await graph.initialize()

        result = await graph.match(transaction, invoices)

        activity.logger.info(
            f"Invoice matching complete: matched={result['matched']}, "
            f"confidence={result['confidence']:.2%}, "
            f"decision={result['decision_type']}"
        )

        await graph.close()

        return result

    except Exception as e:
        activity.logger.error(f"Invoice matcher graph failed: {str(e)}")
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

    try:
        from langgraph_agents import FeedPublisherGraph

        # Create and run graph
        graph = FeedPublisherGraph()
        await graph.initialize()

        result = await graph.publish(brand, platform, photo_s3_key)

        activity.logger.info(
            f"Feed publishing complete: published={result['published']}, "
            f"quality={result['quality_score']:.2%}, "
            f"requires_approval={result['requires_approval']}"
        )

        await graph.close()

        return result

    except Exception as e:
        activity.logger.error(f"Feed publisher graph failed: {str(e)}")
        raise


# Activity list for worker registration
LANGGRAPH_ACTIVITIES = [
    run_invoice_matcher_graph,
    run_feed_publisher_graph
]
