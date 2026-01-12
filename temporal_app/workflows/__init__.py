"""
Temporal workflows - orchestration for agent tasks.

Workflows:
    - DailyAnalyticsWorkflow: Full integrated analytics pipeline
    - WeeklyAnalyticsWorkflow: Extended analytics with 14-day window
    - FeedbackCollectionWorkflow: T+1, T+3, T+7 action feedback
    - FeedPublisherWorkflow: Social media feed publishing
    - FeedPublisherLangGraphWorkflow: LangGraph-based publishing
    - InvoiceMatcherLangGraphWorkflow: Invoice matching
"""

from .feed_publisher import FeedPublisherWorkflow
from .feed_publisher_langgraph import FeedPublisherLangGraphWorkflow
from .invoice_matcher_langgraph import InvoiceMatcherLangGraphWorkflow
from .daily_analytics import (
    DailyAnalyticsWorkflow,
    WeeklyAnalyticsWorkflow,
    FeedbackCollectionWorkflow
)
from .appointment_collector import *

__all__ = [
    # Core Analytics Pipeline
    "DailyAnalyticsWorkflow",
    "WeeklyAnalyticsWorkflow",
    "FeedbackCollectionWorkflow",
    # Publishing
    "FeedPublisherWorkflow",
    "FeedPublisherLangGraphWorkflow",
    # Other
    "InvoiceMatcherLangGraphWorkflow",
]
