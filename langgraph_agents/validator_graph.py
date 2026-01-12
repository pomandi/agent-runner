"""
Data Validator Graph
=====================

LangGraph implementation for data validation before analysis.

This graph validates collected data through:
1. Duplicate Detection - Check if data was already processed
2. Cross-Source Verification - Verify consistency between sources
3. Anomaly Detection - Detect unusual values and patterns
4. Quality Score Calculation - Overall data quality assessment

Flow:
    load_data -> detect_duplicates -> cross_source_verify ->
    detect_anomalies -> calculate_quality_score -> decide_proceed -> output_report

Usage:
    validator = DataValidatorGraph()
    result = await validator.validate(collected_data)

    if result["proceed_to_analysis"]:
        # Continue with analysis
    else:
        # Alert for human review
"""

from typing import Dict, Any, Optional, List, TypedDict, Annotated
from datetime import datetime
from langgraph.graph import StateGraph, END
from pathlib import Path
import structlog
import operator
import json
import os
import httpx

from .base_graph import BaseAgentGraph
from .duplicate_detector import DuplicateDetector
from .validation_rules import (
    CROSS_SOURCE_RULES,
    ANOMALY_RULES,
    DATA_QUALITY_RULES,
    ValidationResult,
    Severity,
    run_cross_source_validation,
    run_anomaly_detection,
    calculate_validation_score,
    should_proceed_to_analysis,
    format_validation_report
)

logger = structlog.get_logger(__name__)


# =============================================================================
# STATE SCHEMA
# =============================================================================

class ValidationState(TypedDict):
    """State for data validation workflow."""

    # Input
    brand: str
    date: str
    days: int
    raw_data: Dict[str, Dict[str, Any]]  # Source name -> source data

    # Duplicate Detection
    duplicates: List[Dict[str, Any]]
    dedup_stats: Dict[str, int]  # checked, duplicates_found, skipped, updated

    # Cross-Source Verification
    cross_source_conflicts: List[Dict[str, Any]]

    # Anomaly Detection
    anomalies: List[Dict[str, Any]]
    historical_context: Optional[Dict[str, Any]]

    # Quality Assessment
    validation_score: float
    data_quality_per_source: Dict[str, float]

    # Decision
    proceed_to_analysis: bool
    requires_human_review: List[str]

    # Output
    validation_report: Optional[str]
    validation_results: List[Dict[str, Any]]

    # Tracking
    steps_completed: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]


def init_validation_state(
    brand: str = "pomandi",
    date: str = None,
    days: int = 7,
    raw_data: Dict[str, Dict[str, Any]] = None
) -> ValidationState:
    """Initialize validation state with defaults."""
    return {
        "brand": brand,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "days": days,
        "raw_data": raw_data or {},
        # Duplicate Detection
        "duplicates": [],
        "dedup_stats": {"checked": 0, "duplicates_found": 0, "skipped": 0, "updated": 0},
        # Cross-Source
        "cross_source_conflicts": [],
        # Anomaly
        "anomalies": [],
        "historical_context": None,
        # Quality
        "validation_score": 1.0,
        "data_quality_per_source": {},
        # Decision
        "proceed_to_analysis": True,
        "requires_human_review": [],
        # Output
        "validation_report": None,
        "validation_results": [],
        # Tracking
        "steps_completed": [],
        "errors": []
    }


# =============================================================================
# VALIDATOR GRAPH
# =============================================================================

class DataValidatorGraph(BaseAgentGraph):
    """
    Toplanan verileri doğrular ve anomalileri tespit eder.

    Flow:
        load_data -> detect_duplicates -> cross_source_verify ->
        detect_anomalies -> calculate_quality_score -> decide_proceed -> output_report

    Duplicate Detection İLK adımda yapılır çünkü:
    1. Duplicate veri diğer kontrolleri yanıltır
    2. Performans için gereksiz işlemi önler
    3. Veri bütünlüğü sağlanır

    Usage:
        validator = DataValidatorGraph()
        result = await validator.validate(collected_data, brand="pomandi")
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Initialize duplicate detector
        # Note: In production, pass actual clients
        self.duplicate_detector = DuplicateDetector(
            memory_hub_client=None,  # TODO: Connect to Memory-Hub MCP
            qdrant_client=None,      # TODO: Connect to Qdrant
            redis_client=None        # TODO: Connect to Redis
        )

        # MCP server directory for Memory-Hub calls
        self._mcp_dir = Path(__file__).parent.parent / "mcp-servers"

    def build_graph(self) -> StateGraph:
        """Build validation graph with CONDITIONAL EDGES.

        Flow:
            load_data -> detect_duplicates -> cross_source_verify ->
            detect_anomalies -> calculate_quality -> generate_report ->
            [CONDITIONAL ROUTING based on validation results]
                -> "critical": send_critical_alert -> END
                -> "review": send_review_alert -> END
                -> "proceed": END (no alert needed)

        Conditional edges make branching VISIBLE in the graph structure,
        not hidden inside nodes.
        """
        graph = StateGraph(ValidationState)

        # Add nodes
        graph.add_node("load_data", self.load_data_node)
        graph.add_node("detect_duplicates", self.detect_duplicates_node)
        graph.add_node("cross_source_verify", self.cross_source_verify_node)
        graph.add_node("detect_anomalies", self.detect_anomalies_node)
        graph.add_node("calculate_quality", self.calculate_quality_score_node)
        graph.add_node("generate_report", self.generate_report_node)

        # Alert nodes (branching targets)
        graph.add_node("send_critical_alert", self.send_critical_alert_node)
        graph.add_node("send_review_alert", self.send_review_alert_node)
        graph.add_node("log_success", self.log_success_node)

        # Entry point
        graph.set_entry_point("load_data")

        # Sequential edges (validation pipeline)
        graph.add_edge("load_data", "detect_duplicates")
        graph.add_edge("detect_duplicates", "cross_source_verify")
        graph.add_edge("cross_source_verify", "detect_anomalies")
        graph.add_edge("detect_anomalies", "calculate_quality")
        graph.add_edge("calculate_quality", "generate_report")

        # CONDITIONAL EDGES - Branching is now VISIBLE in graph structure
        graph.add_conditional_edges(
            "generate_report",
            self._route_after_validation,
            {
                "critical": "send_critical_alert",
                "review": "send_review_alert",
                "proceed": "log_success"
            }
        )

        # All branches lead to END
        graph.add_edge("send_critical_alert", END)
        graph.add_edge("send_review_alert", END)
        graph.add_edge("log_success", END)

        return graph

    def _route_after_validation(self, state: ValidationState) -> str:
        """
        CONDITIONAL ROUTING FUNCTION - Determines next step based on validation results.

        This function makes the decision logic EXPLICIT and VISIBLE.
        Rules are defined here, not hidden in node implementations.

        Returns:
            "critical" - Validation failed, analysis should NOT proceed
            "review"   - Validation passed but human review needed
            "proceed"  - All good, proceed to analysis
        """
        proceed = state.get("proceed_to_analysis", False)
        requires_review = state.get("requires_human_review", [])
        score = state.get("validation_score", 0.0)

        # Critical anomalies detected
        critical_anomalies = [
            a for a in state.get("anomalies", [])
            if a.get("severity") == "critical"
        ]

        # Decision tree (EXPLICIT RULES)
        if not proceed or score < 0.5:
            logger.info(
                "routing_decision",
                route="critical",
                score=score,
                proceed=proceed
            )
            return "critical"

        elif requires_review or critical_anomalies:
            logger.info(
                "routing_decision",
                route="review",
                requires_review=requires_review,
                critical_count=len(critical_anomalies)
            )
            return "review"

        else:
            logger.info(
                "routing_decision",
                route="proceed",
                score=score
            )
            return "proceed"

    # =========================================================================
    # NODE IMPLEMENTATIONS
    # =========================================================================

    async def load_data_node(self, state: ValidationState) -> ValidationState:
        """Load and prepare data for validation."""
        try:
            raw_data = state.get("raw_data", {})

            # Count sources with data vs errors
            sources_with_data = 0
            sources_with_errors = 0

            for source_name, source_data in raw_data.items():
                if source_data:
                    if source_data.get("error"):
                        sources_with_errors += 1
                    else:
                        sources_with_data += 1

            logger.info(
                "validation_data_loaded",
                total_sources=len(raw_data),
                with_data=sources_with_data,
                with_errors=sources_with_errors
            )

            state = self.add_step(state, "load_data")

        except Exception as e:
            state["errors"].append(f"Load data failed: {str(e)}")
            logger.error("load_data_error", error=str(e))

        return state

    async def detect_duplicates_node(self, state: ValidationState) -> ValidationState:
        """
        İLK ADIM: Duplicate veri kontrolü.

        Her kaynak için:
        1. Hash kontrolü (exact match)
        2. Memory-Hub kontrolü (source + date)
        3. Qdrant semantic similarity (fuzzy match)
        """
        try:
            duplicates = []
            dedup_stats = {"checked": 0, "duplicates_found": 0, "skipped": 0, "updated": 0}
            raw_data = state.get("raw_data", {})

            for source_name, source_data in raw_data.items():
                dedup_stats["checked"] += 1

                # Skip if source has error
                if not source_data or source_data.get("error"):
                    continue

                # Prepare data for duplicate check
                check_data = {
                    "source": source_name,
                    "date": state.get("date"),
                    "brand": state.get("brand"),
                    "total_spend": source_data.get("total_spend", 0),
                    "total_clicks": source_data.get("total_clicks", 0),
                    "total_conversions": source_data.get("total_conversions", 0)
                }

                # Check for duplicate
                dup_result = await self.duplicate_detector.check_duplicate(check_data)

                if dup_result["is_duplicate"]:
                    dedup_stats["duplicates_found"] += 1

                    duplicates.append({
                        "source": source_name,
                        "date": state.get("date"),
                        "duplicate_type": dup_result["duplicate_type"],
                        "existing_id": dup_result.get("existing_id"),
                        "similarity_score": dup_result.get("similarity_score"),
                        "action": dup_result["recommended_action"]
                    })

                    # Apply action
                    if dup_result["recommended_action"] == "skip":
                        dedup_stats["skipped"] += 1
                        # Mark source as skipped
                        raw_data[source_name]["_skipped"] = True
                        raw_data[source_name]["_skip_reason"] = "duplicate"

                    elif dup_result["recommended_action"] == "update":
                        dedup_stats["updated"] += 1
                        # Mark for update instead of create
                        raw_data[source_name]["_update_existing"] = True
                        raw_data[source_name]["_existing_id"] = dup_result["existing_id"]

            state["duplicates"] = duplicates
            state["dedup_stats"] = dedup_stats
            state["raw_data"] = raw_data

            # Log if duplicates found
            if dedup_stats["duplicates_found"] > 0:
                logger.warning(
                    "duplicates_detected",
                    count=dedup_stats["duplicates_found"],
                    skipped=dedup_stats["skipped"],
                    updated=dedup_stats["updated"]
                )

            state = self.add_step(state, "detect_duplicates")

        except Exception as e:
            state["errors"].append(f"Duplicate detection failed: {str(e)}")
            logger.error("detect_duplicates_error", error=str(e))

        return state

    async def cross_source_verify_node(self, state: ValidationState) -> ValidationState:
        """Cross-source verification - check data consistency between sources."""
        try:
            raw_data = state.get("raw_data", {})

            # Skip sources that are marked as duplicate/skipped
            active_data = {
                k: v for k, v in raw_data.items()
                if v and not v.get("_skipped") and not v.get("error")
            }

            # Run cross-source validation
            validation_results = run_cross_source_validation(active_data)

            # Convert to dict format
            conflicts = [r.to_dict() for r in validation_results if not r.passed]

            state["cross_source_conflicts"] = conflicts
            state["validation_results"].extend(conflicts)

            if conflicts:
                # Add sources with conflicts to human review list
                for conflict in conflicts:
                    sources = conflict.get("details", {}).get("sources", [])
                    for source in sources:
                        if source not in state["requires_human_review"]:
                            state["requires_human_review"].append(source)

            logger.info(
                "cross_source_verification_complete",
                conflicts_found=len(conflicts)
            )

            state = self.add_step(state, "cross_source_verify")

        except Exception as e:
            state["errors"].append(f"Cross-source verification failed: {str(e)}")
            logger.error("cross_source_verify_error", error=str(e))

        return state

    async def detect_anomalies_node(self, state: ValidationState) -> ValidationState:
        """Detect anomalies in the data."""
        try:
            raw_data = state.get("raw_data", {})
            anomalies = []

            # Get historical context (if available)
            historical = await self._get_historical_context(
                state["brand"],
                days=30
            )
            state["historical_context"] = historical

            # Run anomaly detection for each source
            for source_name, source_data in raw_data.items():
                if not source_data or source_data.get("error") or source_data.get("_skipped"):
                    continue

                # Get historical data for this source
                source_historical = historical.get(source_name, {})

                # Run anomaly detection
                source_anomalies = run_anomaly_detection(source_data, source_historical)

                for anomaly in source_anomalies:
                    if not anomaly.passed:
                        anomaly_dict = anomaly.to_dict()
                        anomaly_dict["source"] = source_name
                        anomalies.append(anomaly_dict)

            state["anomalies"] = anomalies
            state["validation_results"].extend(anomalies)

            # Critical anomalies require human review
            for anomaly in anomalies:
                if anomaly.get("severity") == "critical":
                    source = anomaly.get("source", "unknown")
                    if source not in state["requires_human_review"]:
                        state["requires_human_review"].append(source)

            logger.info(
                "anomaly_detection_complete",
                anomalies_found=len(anomalies)
            )

            state = self.add_step(state, "detect_anomalies")

        except Exception as e:
            state["errors"].append(f"Anomaly detection failed: {str(e)}")
            logger.error("detect_anomalies_error", error=str(e))

        return state

    async def calculate_quality_score_node(self, state: ValidationState) -> ValidationState:
        """Calculate overall data quality score."""
        try:
            # Start with perfect score
            score = 1.0

            # Deduct for duplicates
            dedup_stats = state.get("dedup_stats", {})
            if dedup_stats.get("duplicates_found", 0) > 0:
                score -= 0.1 * min(dedup_stats["duplicates_found"], 3)  # Max -0.3

            # Deduct for cross-source conflicts
            conflicts = state.get("cross_source_conflicts", [])
            for conflict in conflicts:
                severity = conflict.get("severity", "medium")
                if severity == "critical":
                    score -= 0.3
                elif severity == "high":
                    score -= 0.15
                elif severity == "medium":
                    score -= 0.05

            # Deduct for anomalies
            anomalies = state.get("anomalies", [])
            for anomaly in anomalies:
                severity = anomaly.get("severity", "medium")
                if severity == "critical":
                    score -= 0.2
                elif severity == "high":
                    score -= 0.1
                elif severity == "medium":
                    score -= 0.03

            # Deduct for errors
            raw_data = state.get("raw_data", {})
            error_count = sum(1 for v in raw_data.values() if v and v.get("error"))
            score -= error_count * 0.1

            # Ensure score is in valid range
            score = max(0.0, min(1.0, score))

            state["validation_score"] = score
            state["proceed_to_analysis"] = should_proceed_to_analysis(score)

            # Calculate per-source quality
            for source_name, source_data in raw_data.items():
                if not source_data:
                    state["data_quality_per_source"][source_name] = 0.0
                elif source_data.get("error"):
                    state["data_quality_per_source"][source_name] = 0.0
                elif source_data.get("_skipped"):
                    state["data_quality_per_source"][source_name] = 0.5
                else:
                    state["data_quality_per_source"][source_name] = 1.0

            logger.info(
                "quality_score_calculated",
                score=score,
                proceed=state["proceed_to_analysis"]
            )

            state = self.add_step(state, "calculate_quality")

        except Exception as e:
            state["errors"].append(f"Quality calculation failed: {str(e)}")
            state["validation_score"] = 0.5
            state["proceed_to_analysis"] = False
            logger.error("calculate_quality_error", error=str(e))

        return state

    async def generate_report_node(self, state: ValidationState) -> ValidationState:
        """Generate validation report."""
        try:
            brand = state["brand"]
            date = state["date"]
            score = state["validation_score"]
            proceed = state["proceed_to_analysis"]

            # Build report
            lines = [
                f"# Veri Doğrulama Raporu",
                f"",
                f"**Marka:** {brand}",
                f"**Tarih:** {date}",
                f"**Validation Score:** {score:.0%}",
                f"**Analize Devam:** {'✅ Evet' if proceed else '❌ Hayır - İnceleme Gerekli'}",
                f""
            ]

            # Duplicate stats
            dedup = state.get("dedup_stats", {})
            if dedup.get("duplicates_found", 0) > 0:
                lines.extend([
                    "## 🔄 Duplicate Kontrolü",
                    f"- Kontrol edilen: {dedup.get('checked', 0)}",
                    f"- Duplicate bulunan: {dedup.get('duplicates_found', 0)}",
                    f"- Atlanan: {dedup.get('skipped', 0)}",
                    f"- Güncellenen: {dedup.get('updated', 0)}",
                    ""
                ])

            # Cross-source conflicts
            conflicts = state.get("cross_source_conflicts", [])
            if conflicts:
                lines.extend([
                    "## ⚠️ Kaynak Arası Tutarsızlıklar",
                ])
                for c in conflicts:
                    severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(c.get("severity"), "⚪")
                    lines.append(f"- {severity_icon} {c.get('rule_id')}: {c.get('message')}")
                lines.append("")

            # Anomalies
            anomalies = state.get("anomalies", [])
            if anomalies:
                lines.extend([
                    "## 🔍 Tespit Edilen Anomaliler",
                ])
                for a in anomalies:
                    severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(a.get("severity"), "⚪")
                    lines.append(f"- {severity_icon} [{a.get('source')}] {a.get('rule_id')}: {a.get('message')}")
                lines.append("")

            # Human review required
            review_list = state.get("requires_human_review", [])
            if review_list:
                lines.extend([
                    "## 👤 İnsan İncelemesi Gerekli",
                    f"Kaynaklar: {', '.join(review_list)}",
                    ""
                ])

            # Per-source quality
            lines.append("## 📊 Kaynak Bazlı Kalite")
            for source, quality in state.get("data_quality_per_source", {}).items():
                icon = "✅" if quality >= 0.8 else "⚠️" if quality >= 0.5 else "❌"
                lines.append(f"- {icon} {source}: {quality:.0%}")

            state["validation_report"] = "\n".join(lines)

            logger.info("validation_report_generated")
            state = self.add_step(state, "generate_report")

        except Exception as e:
            state["errors"].append(f"Report generation failed: {str(e)}")
            logger.error("generate_report_error", error=str(e))

        return state

    async def send_critical_alert_node(self, state: ValidationState) -> ValidationState:
        """
        Send CRITICAL alert - Validation failed, analysis should NOT proceed.

        This node is only reached via conditional edge when:
        - proceed_to_analysis is False
        - OR validation_score < 0.5
        """
        try:
            await self._send_telegram_alert(
                state,
                alert_type="critical",
                title="🔴 KRİTİK VERİ DOĞRULAMA HATASI",
                action_required="Analiz DURDURULDU - Acil inceleme gerekli"
            )

            state = self.add_step(state, "send_critical_alert")
            logger.warning(
                "critical_alert_sent",
                score=state.get("validation_score"),
                anomaly_count=len(state.get("anomalies", []))
            )

        except Exception as e:
            state["errors"].append(f"Critical alert failed: {str(e)}")
            logger.error("send_critical_alert_error", error=str(e))

        return state

    async def send_review_alert_node(self, state: ValidationState) -> ValidationState:
        """
        Send REVIEW alert - Validation passed but human review recommended.

        This node is only reached via conditional edge when:
        - proceed_to_analysis is True
        - AND requires_human_review has items OR critical anomalies exist
        """
        try:
            review_list = state.get("requires_human_review", [])

            await self._send_telegram_alert(
                state,
                alert_type="review",
                title="🟠 VERİ İNCELEME GEREKLİ",
                action_required=f"İncelenmesi gereken kaynaklar: {', '.join(review_list)}"
            )

            state = self.add_step(state, "send_review_alert")
            logger.info(
                "review_alert_sent",
                score=state.get("validation_score"),
                review_items=review_list
            )

        except Exception as e:
            state["errors"].append(f"Review alert failed: {str(e)}")
            logger.error("send_review_alert_error", error=str(e))

        return state

    async def log_success_node(self, state: ValidationState) -> ValidationState:
        """
        Log successful validation - No alerts needed, proceed to analysis.

        This node is only reached via conditional edge when:
        - proceed_to_analysis is True
        - AND no human review required
        - AND no critical anomalies
        """
        try:
            state = self.add_step(state, "log_success")
            logger.info(
                "validation_passed",
                score=state.get("validation_score"),
                brand=state.get("brand"),
                date=state.get("date"),
                proceed=True
            )

        except Exception as e:
            state["errors"].append(f"Log success failed: {str(e)}")
            logger.error("log_success_error", error=str(e))

        return state

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _get_historical_context(
        self,
        brand: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get historical averages for anomaly detection."""
        try:
            # Try to get from Memory-Hub
            # TODO: Implement Memory-Hub query for historical data

            # For now, return empty (anomaly detection will still work, just less accurate)
            return {}

        except Exception as e:
            logger.warning("historical_context_fetch_failed", error=str(e))
            return {}

    async def _send_telegram_alert(
        self,
        state: ValidationState,
        alert_type: str = "info",
        title: str = "VERİ DOĞRULAMA BİLDİRİMİ",
        action_required: str = ""
    ) -> bool:
        """
        Send validation alert to Telegram.

        Args:
            state: Current validation state
            alert_type: "critical", "review", or "info"
            title: Alert title with emoji
            action_required: Specific action message
        """
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN_ANALYTICS")
            chat_id = os.getenv("TELEGRAM_CHAT_ID_ANALYTICS")

            if not bot_token or not chat_id:
                logger.warning("telegram_config_missing")
                return False

            # Build alert message based on type
            score = state["validation_score"]
            proceed = state["proceed_to_analysis"]
            conflicts = len(state.get("cross_source_conflicts", []))
            anomalies = len(state.get("anomalies", []))
            review = state.get("requires_human_review", [])

            # Type-specific formatting
            if alert_type == "critical":
                status_line = "❌ **DURUM:** ANALİZE DEVAM EDİLMİYOR"
                urgency = "⏰ **Aciliyet:** HEMEN"
            elif alert_type == "review":
                status_line = "⚠️ **DURUM:** İnceleme sonrası devam edilebilir"
                urgency = "⏰ **Aciliyet:** Bugün içinde"
            else:
                status_line = "✅ **DURUM:** Normal"
                urgency = ""

            message = f"""{title}

**Marka:** {state['brand']}
**Tarih:** {state['date']}
**Validation Score:** {score:.0%}

{status_line}

📊 **Detaylar:**
- Tutarsızlıklar: {conflicts}
- Anomaliler: {anomalies}
- İnceleme gereken: {len(review)}

{f'🎯 **Aksiyon:** {action_required}' if action_required else ''}
{urgency}

📁 Rapor: agent_outputs/daily_analytics/"""

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": "Markdown"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    logger.info("validation_alert_sent", alert_type=alert_type)
                    return True
                else:
                    logger.error("validation_alert_failed", status=response.status_code)
                    return False

        except Exception as e:
            logger.error("telegram_alert_error", error=str(e))
            return False

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def validate(
        self,
        raw_data: Dict[str, Dict[str, Any]],
        brand: str = "pomandi",
        date: str = None,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Validate collected data.

        Args:
            raw_data: Dictionary with source names as keys and source data as values
            brand: Brand name
            date: Date string (YYYY-MM-DD)
            days: Number of days in the data period

        Returns:
            Validation result with:
            - validation_score: 0-1 quality score
            - proceed_to_analysis: bool
            - validation_report: Markdown report
            - duplicates, conflicts, anomalies: Lists of issues
        """
        try:
            # Initialize state
            initial_state = init_validation_state(
                brand=brand,
                date=date or datetime.now().strftime("%Y-%m-%d"),
                days=days,
                raw_data=raw_data
            )

            # Run graph
            final_state = await self.run(**initial_state)

            # Build result
            return {
                "success": True,
                "validation_score": final_state.get("validation_score", 0.0),
                "proceed_to_analysis": final_state.get("proceed_to_analysis", False),
                "validation_report": final_state.get("validation_report", ""),
                "duplicates": final_state.get("duplicates", []),
                "dedup_stats": final_state.get("dedup_stats", {}),
                "cross_source_conflicts": final_state.get("cross_source_conflicts", []),
                "anomalies": final_state.get("anomalies", []),
                "requires_human_review": final_state.get("requires_human_review", []),
                "data_quality_per_source": final_state.get("data_quality_per_source", {}),
                "errors": final_state.get("errors", []),
                "steps_completed": final_state.get("steps_completed", [])
            }

        except Exception as e:
            logger.error("validation_failed", error=str(e))
            return {
                "success": False,
                "validation_score": 0.0,
                "proceed_to_analysis": False,
                "error": str(e)
            }
