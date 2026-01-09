"""
LangGraph State Schemas
=======================

Pydantic models for graph state management.
Each graph has its own state schema with typed fields.
"""

from typing import List, Dict, Any, Optional, TypedDict, Annotated, Literal
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


# Email Assistant State
class EmailMessage(TypedDict):
    """Single email message structure."""
    id: str
    source: Literal["outlook", "godaddy"]
    from_email: str
    from_name: str
    subject: str
    body: str
    received_at: str
    has_attachments: bool
    is_read: bool


class EmailClassification(TypedDict):
    """Email classification result."""
    category: Literal["important", "spam", "newsletter", "personal", "work", "automated"]
    importance_score: float  # 0-1
    requires_response: bool
    suggested_action: Literal["notify", "archive", "delete", "reply", "ignore"]
    reasoning: str


class ResponsePattern(TypedDict):
    """Learned response pattern from memory."""
    pattern_id: int
    sender_pattern: str  # e.g., "@company.com"
    subject_pattern: str  # e.g., "Meeting request"
    typical_response: str  # Template
    response_tone: str  # "formal" / "casual"
    confidence: float
    usage_count: int


class AutoReplyDraft(TypedDict):
    """Drafted auto-reply."""
    to_email: str
    subject: str
    body: str
    based_on_pattern: Optional[int]
    confidence: float
    requires_approval: bool


class EmailAssistantState(TypedDict):
    """Complete state for email assistant workflow."""

    # Fetching
    outlook_emails: List[EmailMessage]
    godaddy_emails: List[EmailMessage]
    all_emails: List[EmailMessage]
    new_emails_count: int

    # Classification
    classifications: Dict[str, EmailClassification]
    important_emails: List[EmailMessage]
    spam_emails: List[EmailMessage]

    # Pattern matching
    learned_patterns: List[ResponsePattern]
    pattern_matches: Dict[str, ResponsePattern]

    # Notifications
    notification_sent: bool
    notification_ids: List[str]

    # Auto-reply
    reply_drafts: Dict[str, AutoReplyDraft]
    pending_approval: List[str]

    # Actions
    archived_count: int
    deleted_count: int
    replied_count: int

    # Learning
    new_patterns_saved: int

    # Execution tracking
    steps_completed: Annotated[List[str], operator.add]
    warnings: Annotated[List[str], operator.add]
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


def init_email_assistant_state() -> EmailAssistantState:
    """Initialize email assistant state with defaults."""
    return {
        "outlook_emails": [],
        "godaddy_emails": [],
        "all_emails": [],
        "new_emails_count": 0,
        "classifications": {},
        "important_emails": [],
        "spam_emails": [],
        "learned_patterns": [],
        "pattern_matches": {},
        "notification_sent": False,
        "notification_ids": [],
        "reply_drafts": {},
        "pending_approval": [],
        "archived_count": 0,
        "deleted_count": 0,
        "replied_count": 0,
        "new_patterns_saved": 0,
        "steps_completed": [],
        "warnings": [],
        "error": None
    }


# =============================================================================
# Daily Analytics Report State
# =============================================================================

class DailyAnalyticsState(TypedDict):
    """State for daily analytics report workflow.

    Collects data from 8 sources, analyzes with Claude, generates Turkish report.
    """

    # Input
    days: int                                    # Kaç günlük veri (default: 7)
    brand: str                                   # "pomandi" veya "costume"

    # Data Collection (8 kaynak)
    google_ads_data: Optional[Dict[str, Any]]    # Kampanya, keyword, conversion
    meta_ads_data: Optional[Dict[str, Any]]      # FB/IG kampanya, hedefleme
    visitor_tracking_data: Optional[Dict[str, Any]]  # ⭐ Custom DB - sessions, events, conversions
    ga4_data: Optional[Dict[str, Any]]           # Trafik, kullanıcı, conversion
    search_console_data: Optional[Dict[str, Any]]  # SEO, keyword pozisyon
    merchant_data: Optional[Dict[str, Any]]      # Ürün performansı
    shopify_data: Optional[Dict[str, Any]]       # Sipariş, gelir, müşteri
    appointments_data: Optional[Dict[str, Any]]  # Randevu, GCLID/FBCLID attribution

    # Analysis
    merged_data: Optional[Dict[str, Any]]        # Tüm kaynaklar birleşik
    funnel_analysis: Optional[str]               # Claude output (Türkçe)
    insights: List[str]                          # Önemli bulgular
    recommendations: List[str]                   # Öneriler

    # Report
    report_markdown: Optional[str]               # Türkçe rapor
    quality_score: float                         # Rapor kalite skoru 0-1

    # Delivery
    telegram_sent: bool                          # Telegram'a gönderildi mi
    telegram_message_id: Optional[str]           # Telegram mesaj ID'si

    # Execution tracking
    steps_completed: Annotated[List[str], operator.add]  # Tamamlanan adımlar
    errors: Annotated[List[str], operator.add]   # Hatalar


def init_daily_analytics_state(
    days: int = 7,
    brand: str = "pomandi"
) -> DailyAnalyticsState:
    """Initialize daily analytics state with defaults."""
    return {
        "days": days,
        "brand": brand,
        # Data Collection
        "google_ads_data": None,
        "meta_ads_data": None,
        "visitor_tracking_data": None,
        "ga4_data": None,
        "search_console_data": None,
        "merchant_data": None,
        "shopify_data": None,
        "appointments_data": None,
        # Analysis
        "merged_data": None,
        "funnel_analysis": None,
        "insights": [],
        "recommendations": [],
        # Report
        "report_markdown": None,
        "quality_score": 0.0,
        # Delivery
        "telegram_sent": False,
        "telegram_message_id": None,
        # Tracking
        "steps_completed": [],
        "errors": []
    }
