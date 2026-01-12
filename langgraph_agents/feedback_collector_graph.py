"""
Feedback Collector Graph
=========================

LangGraph implementation for collecting and evaluating action outcomes.

This graph tracks the results of executed actions at T+1, T+3, T+7 days
to measure impact and generate learnings for future action planning.

Flow:
    load_pending_feedback -> collect_metrics -> compare_impact ->
    evaluate_success -> generate_learnings -> save_to_memory -> notify

The feedback loop enables:
1. Measuring actual vs expected impact
2. Learning from successful/failed actions
3. Improving future action recommendations
4. Building institutional knowledge

Usage:
    collector = FeedbackCollectorGraph()
    result = await collector.collect_feedback()  # Runs daily
"""

from typing import Dict, Any, Optional, List, TypedDict, Annotated, Literal
from datetime import datetime, timedelta
from langgraph.graph import StateGraph, END
from pathlib import Path
import structlog
import operator
import json
import os
import httpx
import glob

from .base_graph import BaseAgentGraph

# Import Claude Agent SDK
try:
    from claude_agent_sdk import query, ClaudeAgentOptions
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

logger = structlog.get_logger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Feedback collection intervals (days after action execution)
FEEDBACK_INTERVALS = [1, 3, 7]

# Success evaluation thresholds
SUCCESS_THRESHOLDS = {
    "roas_improvement": 0.2,       # 20% improvement = success
    "cost_reduction": 0.1,         # 10% reduction = success
    "conversion_improvement": 0.15, # 15% improvement = success
    "ctr_improvement": 0.1         # 10% improvement = success
}


# =============================================================================
# STATE SCHEMA
# =============================================================================

class ActionFeedback(TypedDict):
    """Feedback for a single action."""
    action_id: str
    action_title: str
    executed_at: str
    days_since_execution: int
    pre_metrics: Dict[str, Any]
    post_metrics: Dict[str, Any]
    expected_impact: str
    actual_impact: Dict[str, Any]
    success: Optional[bool]
    success_reason: str
    learnings: str


class FeedbackCollectorState(TypedDict):
    """State for feedback collection workflow."""

    # Input
    brand: str
    collection_date: str

    # Pending Feedback
    pending_actions: List[Dict[str, Any]]

    # Metrics Collection
    current_metrics: Dict[str, Dict[str, Any]]

    # Feedback Results
    feedbacks: List[ActionFeedback]
    successful_count: int
    failed_count: int
    pending_count: int

    # Learnings
    learnings_generated: List[Dict[str, Any]]

    # Output
    feedback_saved: bool
    memory_saved: bool
    report_path: Optional[str]

    # Tracking
    steps_completed: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]


def init_feedback_collector_state(
    brand: str = "pomandi",
    collection_date: str = None
) -> FeedbackCollectorState:
    """Initialize feedback collector state."""
    return {
        "brand": brand,
        "collection_date": collection_date or datetime.now().strftime("%Y-%m-%d"),
        # Pending
        "pending_actions": [],
        # Metrics
        "current_metrics": {},
        # Feedback
        "feedbacks": [],
        "successful_count": 0,
        "failed_count": 0,
        "pending_count": 0,
        # Learnings
        "learnings_generated": [],
        # Output
        "feedback_saved": False,
        "memory_saved": False,
        "report_path": None,
        # Tracking
        "steps_completed": [],
        "errors": []
    }


# =============================================================================
# FEEDBACK COLLECTOR GRAPH
# =============================================================================

class FeedbackCollectorGraph(BaseAgentGraph):
    """
    Collects feedback on executed actions.

    Scheduled to run daily to check for actions that need T+1, T+3, or T+7 feedback.

    Flow:
        load_pending -> collect_metrics -> compare_impact ->
        evaluate_success -> generate_learnings -> save_to_memory -> notify
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mcp_dir = Path(__file__).parent.parent / "mcp-servers"
        self._execution_logs_dir = Path(__file__).parent.parent / "agent_outputs" / "execution_logs"
        self._action_plans_dir = Path(__file__).parent.parent / "agent_outputs" / "action_plans"
        self._feedback_dir = Path(__file__).parent.parent / "agent_outputs" / "feedback"

    def build_graph(self) -> StateGraph:
        """Build feedback collector graph."""
        graph = StateGraph(FeedbackCollectorState)

        # Add nodes
        graph.add_node("load_pending", self.load_pending_node)
        graph.add_node("collect_metrics", self.collect_metrics_node)
        graph.add_node("compare_impact", self.compare_impact_node)
        graph.add_node("evaluate_success", self.evaluate_success_node)
        graph.add_node("generate_learnings", self.generate_learnings_node)
        graph.add_node("save_feedback", self.save_feedback_node)
        graph.add_node("notify", self.notify_node)

        # Entry point
        graph.set_entry_point("load_pending")

        # Flow
        graph.add_edge("load_pending", "collect_metrics")
        graph.add_edge("collect_metrics", "compare_impact")
        graph.add_edge("compare_impact", "evaluate_success")
        graph.add_edge("evaluate_success", "generate_learnings")
        graph.add_edge("generate_learnings", "save_feedback")
        graph.add_edge("save_feedback", "notify")
        graph.add_edge("notify", END)

        return graph

    # =========================================================================
    # NODE IMPLEMENTATIONS
    # =========================================================================

    async def load_pending_node(self, state: FeedbackCollectorState) -> FeedbackCollectorState:
        """Load actions that need feedback collection."""
        try:
            brand = state["brand"]
            collection_date = datetime.strptime(state["collection_date"], "%Y-%m-%d")
            pending_actions = []

            # Scan execution logs for actions needing feedback
            if self._execution_logs_dir.exists():
                for log_file in self._execution_logs_dir.glob("exec_*.json"):
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            log_data = json.load(f)

                        # Check if this is for our brand
                        if log_data.get("brand") != brand:
                            continue

                        # Parse execution date
                        executed_at = log_data.get("executed_at", "")
                        if not executed_at:
                            continue

                        execution_date = datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
                        days_since = (collection_date - execution_date.replace(tzinfo=None)).days

                        # Check if we need feedback at this interval
                        if days_since in FEEDBACK_INTERVALS:
                            for result in log_data.get("execution_results", []):
                                if result.get("status") == "success":
                                    pending_actions.append({
                                        "action_id": result.get("action_id"),
                                        "action_title": result.get("action_title"),
                                        "executed_at": executed_at,
                                        "days_since": days_since,
                                        "execution_log": str(log_file),
                                        "mcp_response": result.get("mcp_response")
                                    })

                    except Exception as e:
                        logger.warning("log_file_read_error", file=str(log_file), error=str(e))

            state["pending_actions"] = pending_actions

            logger.info(
                "pending_actions_loaded",
                count=len(pending_actions)
            )

            state = self.add_step(state, "load_pending")

        except Exception as e:
            state["errors"].append(f"Load pending failed: {str(e)}")
            logger.error("load_pending_error", error=str(e))

        return state

    async def collect_metrics_node(self, state: FeedbackCollectorState) -> FeedbackCollectorState:
        """Collect current metrics for comparison."""
        try:
            # Load the most recent analytics data for the brand
            analytics_dir = Path(__file__).parent.parent / "agent_outputs" / "daily_analytics"

            if analytics_dir.exists():
                # Find the most recent file for this brand
                brand = state["brand"]
                pattern = f"*_{brand}.json"
                files = sorted(analytics_dir.glob(pattern), reverse=True)

                if files:
                    with open(files[0], 'r', encoding='utf-8') as f:
                        analytics_data = json.load(f)

                    # Extract current metrics
                    state["current_metrics"] = {
                        "aggregated": analytics_data.get("aggregated_metrics", {}),
                        "raw_data": analytics_data.get("raw_data", {}),
                        "collection_date": analytics_data.get("metadata", {}).get("collection_date")
                    }

                    logger.info(
                        "current_metrics_loaded",
                        source=str(files[0])
                    )

            state = self.add_step(state, "collect_metrics")

        except Exception as e:
            state["errors"].append(f"Collect metrics failed: {str(e)}")
            logger.error("collect_metrics_error", error=str(e))

        return state

    async def compare_impact_node(self, state: FeedbackCollectorState) -> FeedbackCollectorState:
        """Compare pre and post action metrics."""
        try:
            pending = state.get("pending_actions", [])
            current_metrics = state.get("current_metrics", {})
            feedbacks = []

            for action in pending:
                # Get pre-action metrics from the action plan
                pre_metrics = await self._get_pre_action_metrics(action)

                # Current metrics as post-action
                post_metrics = current_metrics.get("aggregated", {})

                # Calculate actual impact
                actual_impact = self._calculate_impact(pre_metrics, post_metrics)

                feedback: ActionFeedback = {
                    "action_id": action.get("action_id"),
                    "action_title": action.get("action_title"),
                    "executed_at": action.get("executed_at"),
                    "days_since_execution": action.get("days_since", 0),
                    "pre_metrics": pre_metrics,
                    "post_metrics": post_metrics,
                    "expected_impact": action.get("expected_impact", "Unknown"),
                    "actual_impact": actual_impact,
                    "success": None,  # Will be evaluated in next step
                    "success_reason": "",
                    "learnings": ""
                }

                feedbacks.append(feedback)

            state["feedbacks"] = feedbacks

            logger.info("impact_compared", count=len(feedbacks))
            state = self.add_step(state, "compare_impact")

        except Exception as e:
            state["errors"].append(f"Compare impact failed: {str(e)}")
            logger.error("compare_impact_error", error=str(e))

        return state

    async def _get_pre_action_metrics(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Get metrics from before the action was executed."""
        try:
            execution_date = action.get("executed_at", "")
            if not execution_date:
                return {}

            # Parse date
            exec_date = datetime.fromisoformat(execution_date.replace("Z", "+00:00"))
            pre_date = (exec_date - timedelta(days=1)).strftime("%Y-%m-%d")

            # Look for analytics data from before the action
            analytics_dir = Path(__file__).parent.parent / "agent_outputs" / "daily_analytics"
            pre_file = analytics_dir / f"{pre_date}_{action.get('brand', 'pomandi')}.json"

            if pre_file.exists():
                with open(pre_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("aggregated_metrics", {})

            return {}

        except Exception as e:
            logger.warning("pre_metrics_fetch_error", error=str(e))
            return {}

    def _calculate_impact(
        self,
        pre: Dict[str, Any],
        post: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate the impact of an action."""
        impact = {}

        # Revenue change
        pre_revenue = pre.get("total_revenue", 0)
        post_revenue = post.get("total_revenue", 0)
        if pre_revenue > 0:
            impact["revenue_change"] = post_revenue - pre_revenue
            impact["revenue_change_percent"] = ((post_revenue - pre_revenue) / pre_revenue) * 100

        # ROAS change
        pre_roas = pre.get("roas", 0)
        post_roas = post.get("roas", 0)
        impact["roas_change"] = post_roas - pre_roas

        # Spend change
        pre_spend = pre.get("total_ad_spend", 0)
        post_spend = post.get("total_ad_spend", 0)
        if pre_spend > 0:
            impact["spend_change"] = post_spend - pre_spend
            impact["spend_change_percent"] = ((post_spend - pre_spend) / pre_spend) * 100

        # Orders change
        pre_orders = pre.get("total_orders", 0)
        post_orders = post.get("total_orders", 0)
        impact["orders_change"] = post_orders - pre_orders

        return impact

    async def evaluate_success_node(self, state: FeedbackCollectorState) -> FeedbackCollectorState:
        """Evaluate whether actions were successful."""
        try:
            feedbacks = state.get("feedbacks", [])
            successful = 0
            failed = 0

            for feedback in feedbacks:
                impact = feedback.get("actual_impact", {})

                # Evaluate success based on thresholds
                success = False
                reasons = []

                # Check ROAS improvement
                if impact.get("roas_change", 0) > SUCCESS_THRESHOLDS["roas_improvement"]:
                    success = True
                    reasons.append(f"ROAS +{impact['roas_change']:.2f}")

                # Check cost reduction
                if impact.get("spend_change_percent", 0) < -SUCCESS_THRESHOLDS["cost_reduction"] * 100:
                    success = True
                    reasons.append(f"Cost {impact['spend_change_percent']:.1f}%")

                # Check revenue increase
                if impact.get("revenue_change_percent", 0) > SUCCESS_THRESHOLDS["conversion_improvement"] * 100:
                    success = True
                    reasons.append(f"Revenue +{impact['revenue_change_percent']:.1f}%")

                # Mark as failed if metrics got worse
                if (impact.get("roas_change", 0) < -0.5 or
                    impact.get("revenue_change_percent", 0) < -20):
                    success = False
                    reasons = [f"Metrics declined: ROAS {impact.get('roas_change', 0):.2f}, Revenue {impact.get('revenue_change_percent', 0):.1f}%"]

                feedback["success"] = success
                feedback["success_reason"] = "; ".join(reasons) if reasons else "No significant change"

                if success:
                    successful += 1
                else:
                    failed += 1

            state["feedbacks"] = feedbacks
            state["successful_count"] = successful
            state["failed_count"] = failed

            logger.info(
                "success_evaluated",
                successful=successful,
                failed=failed
            )

            state = self.add_step(state, "evaluate_success")

        except Exception as e:
            state["errors"].append(f"Evaluate success failed: {str(e)}")
            logger.error("evaluate_success_error", error=str(e))

        return state

    async def generate_learnings_node(self, state: FeedbackCollectorState) -> FeedbackCollectorState:
        """Generate learnings from feedback using LLM."""
        try:
            feedbacks = state.get("feedbacks", [])
            learnings = []

            if not CLAUDE_SDK_AVAILABLE or not feedbacks:
                state["learnings_generated"] = learnings
                state = self.add_step(state, "generate_learnings")
                return state

            # Group feedbacks for batch learning
            feedback_summary = []
            for fb in feedbacks:
                feedback_summary.append({
                    "action": fb.get("action_title"),
                    "days_since": fb.get("days_since_execution"),
                    "success": fb.get("success"),
                    "reason": fb.get("success_reason"),
                    "impact": fb.get("actual_impact")
                })

            prompt = f"""Sen bir dijital pazarlama analisti olarak geçmiş aksiyonların sonuçlarını değerlendiriyorsun.

## AKSİYON SONUÇLARI
{json.dumps(feedback_summary, ensure_ascii=False, indent=2)}

## GÖREVİN
Her aksiyon için:
1. Neden başarılı/başarısız oldu?
2. Gelecekte benzer durumda ne yapılmalı?
3. Bu deneyimden ne öğrendik?

JSON formatında yanıt ver:
{{
    "learnings": [
        {{
            "action": "Aksiyon adı",
            "insight": "Öğrenilen ders",
            "recommendation": "Gelecek için öneri",
            "confidence": 0.8
        }}
    ],
    "general_insights": ["Genel çıkarım 1", "Genel çıkarım 2"]
}}

KURALLAR:
- Türkçe yaz
- Somut ve uygulanabilir ol
- Veri temelli çıkarım yap
"""

            response = ""
            async for msg in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    max_turns=1,
                    permission_mode="bypassPermissions"
                )
            ):
                if hasattr(msg, 'content'):
                    for block in msg.content:
                        if hasattr(block, 'text'):
                            response += block.text

            # Parse response
            try:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(response[json_start:json_end])
                    learnings = result.get("learnings", [])

                    # Update feedbacks with learnings
                    for fb in feedbacks:
                        for learning in learnings:
                            if learning.get("action") in fb.get("action_title", ""):
                                fb["learnings"] = learning.get("insight", "")
                                break

                    state["learnings_generated"] = learnings

            except json.JSONDecodeError:
                logger.warning("learnings_json_parse_failed")

            state["feedbacks"] = feedbacks

            logger.info("learnings_generated", count=len(learnings))
            state = self.add_step(state, "generate_learnings")

        except Exception as e:
            state["errors"].append(f"Generate learnings failed: {str(e)}")
            logger.error("generate_learnings_error", error=str(e))

        return state

    async def save_feedback_node(self, state: FeedbackCollectorState) -> FeedbackCollectorState:
        """Save feedback and learnings."""
        try:
            self._feedback_dir.mkdir(parents=True, exist_ok=True)

            # Generate feedback ID
            feedback_id = f"feedback_{state['brand']}_{state['collection_date']}"

            # Build feedback document
            feedback_doc = {
                "feedback_id": feedback_id,
                "brand": state["brand"],
                "collection_date": state["collection_date"],
                "collected_at": datetime.now().isoformat(),
                "feedbacks": state.get("feedbacks", []),
                "summary": {
                    "total": len(state.get("feedbacks", [])),
                    "successful": state.get("successful_count", 0),
                    "failed": state.get("failed_count", 0)
                },
                "learnings": state.get("learnings_generated", []),
                "errors": state.get("errors", [])
            }

            # Save to JSON
            report_path = self._feedback_dir / f"{feedback_id}.json"
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(feedback_doc, f, indent=2, ensure_ascii=False, default=str)

            state["feedback_saved"] = True
            state["report_path"] = str(report_path)

            # TODO: Save learnings to Memory-Hub for future reference
            # await self._save_to_memory_hub(learnings)

            logger.info("feedback_saved", path=str(report_path))
            state = self.add_step(state, "save_feedback")

        except Exception as e:
            state["errors"].append(f"Save feedback failed: {str(e)}")
            logger.error("save_feedback_error", error=str(e))

        return state

    async def notify_node(self, state: FeedbackCollectorState) -> FeedbackCollectorState:
        """Send feedback summary notification."""
        try:
            feedbacks = state.get("feedbacks", [])

            if feedbacks:
                await self._send_telegram_notification(state)

            state = self.add_step(state, "notify")

            logger.info(
                "notification_sent",
                feedbacks_count=len(feedbacks)
            )

        except Exception as e:
            state["errors"].append(f"Notification failed: {str(e)}")
            logger.error("notify_error", error=str(e))

        return state

    async def _send_telegram_notification(self, state: FeedbackCollectorState) -> bool:
        """Send feedback notification to Telegram."""
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN_ANALYTICS")
            chat_id = os.getenv("TELEGRAM_CHAT_ID_ANALYTICS")

            if not bot_token or not chat_id:
                return False

            successful = state.get("successful_count", 0)
            failed = state.get("failed_count", 0)
            total = successful + failed

            message = f"""📊 **AKSİYON GERİ BİLDİRİM RAPORU**

**Marka:** {state['brand']}
**Tarih:** {state['collection_date']}

**SONUÇLAR:**
- ✅ Başarılı: {successful}/{total}
- ❌ Başarısız: {failed}/{total}

"""
            # Add learnings
            learnings = state.get("learnings_generated", [])
            if learnings:
                message += "\n**ÖĞRENİLEN DERSLER:**\n"
                for learning in learnings[:3]:
                    message += f"• {learning.get('insight', 'N/A')}\n"

            # Add failed action details
            for fb in state.get("feedbacks", []):
                if not fb.get("success"):
                    message += f"\n⚠️ **{fb.get('action_title')}:** {fb.get('success_reason')}"

            message += f"\n\n📁 Rapor: {state.get('report_path', 'N/A')}"

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

                return response.status_code == 200

        except Exception as e:
            logger.error("telegram_notification_error", error=str(e))
            return False

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def collect_feedback(
        self,
        brand: str = "pomandi",
        collection_date: str = None
    ) -> Dict[str, Any]:
        """
        Collect feedback for executed actions.

        Should be run daily to check for T+1, T+3, T+7 feedback.

        Args:
            brand: Brand name
            collection_date: Date to collect feedback for

        Returns:
            Feedback collection result
        """
        try:
            # Initialize state
            initial_state = init_feedback_collector_state(
                brand=brand,
                collection_date=collection_date or datetime.now().strftime("%Y-%m-%d")
            )

            # Run graph
            final_state = await self.run(**initial_state)

            # Build result
            return {
                "success": True,
                "feedbacks": final_state.get("feedbacks", []),
                "summary": {
                    "total": len(final_state.get("feedbacks", [])),
                    "successful": final_state.get("successful_count", 0),
                    "failed": final_state.get("failed_count", 0)
                },
                "learnings": final_state.get("learnings_generated", []),
                "report_path": final_state.get("report_path"),
                "errors": final_state.get("errors", [])
            }

        except Exception as e:
            logger.error("collect_feedback_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
