"""
LangGraph State Schemas
=======================

Pydantic models for graph state management.
Each graph has its own state schema with typed fields.
"""

from typing import List, Dict, Any, Optional, TypedDict, Annotated
from datetime import datetime
import operator


# Invoice Matcher State
class InvoiceMatchState(TypedDict):
    """State for invoice matching workflow."""

    # Input
    transaction: Dict[str, Any]  # Bank transaction to match
    invoices: List[Dict[str, Any]]  # Available invoices

    # Memory retrieval
    memory_results: List[Dict[str, Any]]  # Similar invoices from Qdrant
    memory_query: str  # Query used for memory search

    # Matching results
    matched_invoice_id: Optional[int]  # ID of matched invoice (None if no match)
    confidence: float  # Confidence score 0-1
    reasoning: str  # Explanation of matching decision

    # Decision metadata
    decision_type: str  # "auto_match", "human_review", or "no_match"
    warnings: Annotated[List[str], operator.add]  # Accumulated warnings

    # Execution tracking
    steps_completed: Annotated[List[str], operator.add]  # Track progress
    error: Optional[str]  # Error message if any


# Feed Publisher State
class FeedPublisherState(TypedDict):
    """State for social media feed publishing workflow."""

    # Input
    brand: str  # "pomandi" or "costume"
    platform: str  # "facebook" or "instagram"
    photo_s3_key: str  # S3 key for photo

    # Memory check
    similar_captions: List[Dict[str, Any]]  # Similar past captions
    duplicate_detected: bool  # True if too similar to recent post
    similarity_score: float  # Highest similarity score

    # Caption generation
    caption: str  # Generated caption
    caption_language: str  # "nl" or "fr"
    caption_quality_score: float  # Quality assessment 0-1

    # Publishing
    facebook_post_id: Optional[str]  # FB post ID if published
    instagram_post_id: Optional[str]  # IG post ID if published
    published_at: Optional[datetime]  # Publication timestamp

    # Decision metadata
    requires_approval: bool  # True if human review needed
    rejection_reason: Optional[str]  # Why post was rejected (if any)

    # Execution tracking
    steps_completed: Annotated[List[str], operator.add]
    warnings: Annotated[List[str], operator.add]
    error: Optional[str]


# Agent Context State (General purpose)
class AgentContextState(TypedDict):
    """Generic state for storing agent execution context."""

    agent_name: str
    task: str
    context: Dict[str, Any]
    memory_retrieved: List[Dict[str, Any]]
    decisions_made: Annotated[List[str], operator.add]
    outputs: Dict[str, Any]
    error: Optional[str]


# Utility functions for state initialization

def init_invoice_match_state(
    transaction: Dict[str, Any],
    invoices: List[Dict[str, Any]]
) -> InvoiceMatchState:
    """Initialize invoice match state with defaults."""
    return {
        "transaction": transaction,
        "invoices": invoices,
        "memory_results": [],
        "memory_query": "",
        "matched_invoice_id": None,
        "confidence": 0.0,
        "reasoning": "",
        "decision_type": "",
        "warnings": [],
        "steps_completed": [],
        "error": None
    }


def init_feed_publisher_state(
    brand: str,
    platform: str,
    photo_s3_key: str
) -> FeedPublisherState:
    """Initialize feed publisher state with defaults."""
    return {
        "brand": brand,
        "platform": platform,
        "photo_s3_key": photo_s3_key,
        "similar_captions": [],
        "duplicate_detected": False,
        "similarity_score": 0.0,
        "caption": "",
        "caption_language": "nl" if brand == "pomandi" else "fr",
        "caption_quality_score": 0.0,
        "facebook_post_id": None,
        "instagram_post_id": None,
        "published_at": None,
        "requires_approval": False,
        "rejection_reason": None,
        "steps_completed": [],
        "warnings": [],
        "error": None
    }


def init_agent_context_state(
    agent_name: str,
    task: str,
    context: Dict[str, Any]
) -> AgentContextState:
    """Initialize generic agent context state."""
    return {
        "agent_name": agent_name,
        "task": task,
        "context": context,
        "memory_retrieved": [],
        "decisions_made": [],
        "outputs": {},
        "error": None
    }
