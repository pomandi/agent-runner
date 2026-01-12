"""
LangGraph Agent Implementations
===============================

Graph-based agent orchestration with memory integration.

Usage:
    from langgraph_agents import (
        DailyAnalyticsGraph,
        DataValidatorGraph,
        ActionPlannerGraph,
        ActionExecutorGraph,
        FeedbackCollectorGraph
    )

    # Full pipeline
    analytics = DailyAnalyticsGraph()
    data = await analytics.generate_report(days=7, brand="pomandi")

    validator = DataValidatorGraph()
    validated = await validator.validate(data)

    if validated["proceed_to_analysis"]:
        planner = ActionPlannerGraph()
        actions = await planner.plan_actions(validated)

        executor = ActionExecutorGraph()
        results = await executor.execute_actions(actions)
"""

from .base_graph import BaseAgentGraph
from .invoice_matcher_graph import InvoiceMatcherGraph
from .feed_publisher_graph import FeedPublisherGraph
from .daily_analytics_graph import DailyAnalyticsGraph
from .validator_graph import DataValidatorGraph
from .action_planner_graph import ActionPlannerGraph
from .executor_graph import ActionExecutorGraph
from .feedback_collector_graph import FeedbackCollectorGraph

__all__ = [
    "BaseAgentGraph",
    "InvoiceMatcherGraph",
    "FeedPublisherGraph",
    "DailyAnalyticsGraph",
    "DataValidatorGraph",
    "ActionPlannerGraph",
    "ActionExecutorGraph",
    "FeedbackCollectorGraph"
]
__version__ = "2.0.0"  # Major version bump for full pipeline integration
