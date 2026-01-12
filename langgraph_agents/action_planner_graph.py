"""
Action Planner Graph
=====================

LangGraph implementation for generating actionable recommendations
based on validated analytics data and analysis reports.

This graph:
1. Loads validated data and analysis reports
2. Queries Memory-Hub for historical context and past actions
3. Uses Claude LLM to generate actionable recommendations
4. Prioritizes actions based on impact and risk
5. Determines automation level (auto, semi, manual)

Flow:
    load_context -> query_memory -> analyze_situation ->
    generate_actions -> prioritize -> determine_automation ->
    save_plan -> notify

Usage:
    planner = ActionPlannerGraph()
    result = await planner.plan_actions(validated_data, analysis_reports)
"""

from typing import Dict, Any, Optional, List, TypedDict, Annotated, Literal
from datetime import datetime
from langgraph.graph import StateGraph, END
from pathlib import Path
import structlog
import operator
import json
import os
import httpx

from .base_graph import BaseAgentGraph

# Import Claude Agent SDK (for LLM planning)
try:
    from claude_agent_sdk import query, ClaudeAgentOptions
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

logger = structlog.get_logger(__name__)


# =============================================================================
# ACTION TYPES & CONFIGURATION
# =============================================================================

class AutomationLevel:
    """Automation levels for actions."""
    AUTO = "auto"        # Execute immediately without approval
    SEMI = "semi"        # Execute low-risk automatically, approve high-risk
    MANUAL = "manual"    # Always requires human approval


class ActionCategory:
    """Categories of actions."""
    BUDGET_OPTIMIZATION = "budget_optimization"
    CAMPAIGN_CONTROL = "campaign_control"
    KEYWORD_OPTIMIZATION = "keyword_optimization"
    INVENTORY_ALERT = "inventory_alert"
    TRACKING_FIX = "tracking_fix"
    CONTENT_OPTIMIZATION = "content_optimization"
    AUDIENCE_ADJUSTMENT = "audience_adjustment"


ACTION_TYPES = {
    ActionCategory.BUDGET_OPTIMIZATION: {
        "platforms": ["google_ads", "meta_ads"],
        "automation_level": AutomationLevel.SEMI,
        "max_auto_change_percent": 20,  # Max 20% budget change without approval
        "examples": [
            "Increase budget for high-ROAS campaigns",
            "Decrease budget for underperforming campaigns",
            "Reallocate budget between campaigns"
        ]
    },
    ActionCategory.CAMPAIGN_CONTROL: {
        "platforms": ["google_ads", "meta_ads"],
        "automation_level": AutomationLevel.SEMI,
        "examples": [
            "Pause campaign with 0 conversions",
            "Enable paused campaign after fix"
        ]
    },
    ActionCategory.KEYWORD_OPTIMIZATION: {
        "platforms": ["google_ads"],
        "automation_level": AutomationLevel.MANUAL,
        "examples": [
            "Add negative keywords",
            "Adjust keyword bids"
        ]
    },
    ActionCategory.INVENTORY_ALERT: {
        "platforms": ["shopify", "merchant_center"],
        "automation_level": AutomationLevel.AUTO,
        "examples": [
            "Low stock alert",
            "Out of stock products in ads"
        ]
    },
    ActionCategory.TRACKING_FIX: {
        "platforms": ["all"],
        "automation_level": AutomationLevel.MANUAL,
        "examples": [
            "Fix conversion tracking",
            "Update UTM parameters"
        ]
    }
}

# Priority weights for different factors
PRIORITY_WEIGHTS = {
    "revenue_impact": 3.0,
    "cost_impact": 2.5,
    "urgency": 2.0,
    "confidence": 1.5,
    "ease_of_implementation": 1.0
}


# =============================================================================
# STATE SCHEMA
# =============================================================================

class ActionPlan(TypedDict):
    """Single action plan."""
    id: str
    title: str
    description: str
    priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    priority_score: float
    category: str
    action_type: Literal["automated", "requires_approval", "manual"]
    target_platform: str
    specific_actions: List[Dict[str, Any]]
    expected_impact: str
    expected_impact_value: float  # Estimated € impact
    risk_level: Literal["low", "medium", "high"]
    deadline: str
    success_metric: str
    rollback_plan: str
    confidence: float


class ActionPlannerState(TypedDict):
    """State for action planning workflow."""

    # Input
    brand: str
    date: str
    validated_data: Dict[str, Dict[str, Any]]
    analysis_reports: Dict[str, str]
    validation_score: float

    # Context from Memory
    historical_actions: List[Dict[str, Any]]
    similar_situations: List[Dict[str, Any]]
    firm_rules: Dict[str, Any]

    # Analysis
    situation_summary: str
    key_issues: List[Dict[str, Any]]
    opportunities: List[Dict[str, Any]]

    # Action Plans
    action_plans: List[ActionPlan]
    auto_actions: List[ActionPlan]
    approval_required: List[ActionPlan]
    manual_actions: List[ActionPlan]

    # Output
    plan_saved: bool
    plan_id: Optional[str]
    notification_sent: bool

    # Tracking
    steps_completed: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]


def init_action_planner_state(
    brand: str = "pomandi",
    date: str = None,
    validated_data: Dict = None,
    analysis_reports: Dict = None,
    validation_score: float = 1.0
) -> ActionPlannerState:
    """Initialize action planner state."""
    return {
        "brand": brand,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "validated_data": validated_data or {},
        "analysis_reports": analysis_reports or {},
        "validation_score": validation_score,
        # Memory context
        "historical_actions": [],
        "similar_situations": [],
        "firm_rules": {},
        # Analysis
        "situation_summary": "",
        "key_issues": [],
        "opportunities": [],
        # Actions
        "action_plans": [],
        "auto_actions": [],
        "approval_required": [],
        "manual_actions": [],
        # Output
        "plan_saved": False,
        "plan_id": None,
        "notification_sent": False,
        # Tracking
        "steps_completed": [],
        "errors": []
    }


# =============================================================================
# ACTION PLANNER GRAPH
# =============================================================================

class ActionPlannerGraph(BaseAgentGraph):
    """
    Generates actionable recommendations based on analytics data.

    Flow:
        load_context -> query_memory -> analyze_situation ->
        generate_actions -> prioritize -> determine_automation ->
        save_plan -> notify

    The planner uses Claude LLM to:
    1. Understand the current situation
    2. Identify issues and opportunities
    3. Generate specific, actionable recommendations
    4. Prioritize based on impact and risk
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mcp_dir = Path(__file__).parent.parent / "mcp-servers"
        self._output_dir = Path(__file__).parent.parent / "agent_outputs" / "action_plans"

    def build_graph(self) -> StateGraph:
        """Build action planner graph."""
        graph = StateGraph(ActionPlannerState)

        # Add nodes
        graph.add_node("load_context", self.load_context_node)
        graph.add_node("query_memory", self.query_memory_node)
        graph.add_node("analyze_situation", self.analyze_situation_node)
        graph.add_node("generate_actions", self.generate_actions_node)
        graph.add_node("prioritize", self.prioritize_actions_node)
        graph.add_node("determine_automation", self.determine_automation_node)
        graph.add_node("save_plan", self.save_plan_node)
        graph.add_node("notify", self.notify_node)

        # Entry point
        graph.set_entry_point("load_context")

        # Sequential flow
        graph.add_edge("load_context", "query_memory")
        graph.add_edge("query_memory", "analyze_situation")
        graph.add_edge("analyze_situation", "generate_actions")
        graph.add_edge("generate_actions", "prioritize")
        graph.add_edge("prioritize", "determine_automation")
        graph.add_edge("determine_automation", "save_plan")
        graph.add_edge("save_plan", "notify")
        graph.add_edge("notify", END)

        return graph

    # =========================================================================
    # NODE IMPLEMENTATIONS
    # =========================================================================

    async def load_context_node(self, state: ActionPlannerState) -> ActionPlannerState:
        """Load and prepare context for planning."""
        try:
            # Load firm rules
            state["firm_rules"] = {
                "max_daily_budget_change": 50,  # €50 max change
                "min_roas_for_budget_increase": 2.0,
                "auto_pause_roas_threshold": 1.0,
                "new_campaign_days": "weekdays_only",
                "critical_alert_immediate": True
            }

            logger.info(
                "context_loaded",
                brand=state["brand"],
                sources_count=len(state["validated_data"]),
                reports_count=len(state["analysis_reports"])
            )

            state = self.add_step(state, "load_context")

        except Exception as e:
            state["errors"].append(f"Load context failed: {str(e)}")
            logger.error("load_context_error", error=str(e))

        return state

    async def query_memory_node(self, state: ActionPlannerState) -> ActionPlannerState:
        """Query Memory-Hub for historical context."""
        try:
            # TODO: Query Memory-Hub for:
            # 1. Past actions and their outcomes
            # 2. Similar situations and what worked
            # 3. Chronic issues for this brand

            # For now, return empty (will be populated when Memory-Hub is connected)
            state["historical_actions"] = []
            state["similar_situations"] = []

            logger.info("memory_queried")
            state = self.add_step(state, "query_memory")

        except Exception as e:
            state["errors"].append(f"Memory query failed: {str(e)}")
            logger.error("query_memory_error", error=str(e))

        return state

    async def analyze_situation_node(self, state: ActionPlannerState) -> ActionPlannerState:
        """Analyze current situation using LLM."""
        try:
            if not CLAUDE_SDK_AVAILABLE:
                state["situation_summary"] = "Claude SDK not available"
                state["key_issues"] = []
                state["opportunities"] = []
                state = self.add_step(state, "analyze_situation")
                return state

            # Prepare data summary for LLM
            data_summary = self._prepare_data_summary(state["validated_data"])
            reports_summary = self._prepare_reports_summary(state["analysis_reports"])

            prompt = f"""Sen bir dijital pazarlama strateji uzmanısın.
Aşağıdaki verileri analiz et ve mevcut durumu özetle.

## VERİ ÖZETİ
{data_summary}

## ANALİZ RAPORLARI
{reports_summary}

## VALIDATION SCORE: {state['validation_score']:.0%}

## GÖREVİN
1. Mevcut durumu 3-5 cümlede özetle
2. En kritik 3-5 sorunu listele (JSON formatında)
3. En önemli 3-5 fırsatı listele (JSON formatında)

ÇIKTI FORMATI (JSON):
{{
    "summary": "Özet metni...",
    "issues": [
        {{"issue": "Sorun açıklaması", "severity": "critical/high/medium", "source": "kaynak_adı", "metric": "etkilenen_metrik"}}
    ],
    "opportunities": [
        {{"opportunity": "Fırsat açıklaması", "potential_impact": "€ değeri veya % artış", "source": "kaynak_adı"}}
    ]
}}

KURALLAR:
- Türkçe yaz
- Somut ve ölçülebilir ol
- Sadece verilerden çıkarım yap, varsayım yapma
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

            # Parse JSON response
            try:
                # Find JSON in response
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(response[json_start:json_end])
                    state["situation_summary"] = result.get("summary", "")
                    state["key_issues"] = result.get("issues", [])
                    state["opportunities"] = result.get("opportunities", [])
            except json.JSONDecodeError:
                state["situation_summary"] = response
                state["key_issues"] = []
                state["opportunities"] = []

            logger.info(
                "situation_analyzed",
                issues_count=len(state["key_issues"]),
                opportunities_count=len(state["opportunities"])
            )

            state = self.add_step(state, "analyze_situation")

        except Exception as e:
            state["errors"].append(f"Situation analysis failed: {str(e)}")
            logger.error("analyze_situation_error", error=str(e))

        return state

    async def generate_actions_node(self, state: ActionPlannerState) -> ActionPlannerState:
        """Generate action plans using LLM."""
        try:
            if not CLAUDE_SDK_AVAILABLE:
                state["action_plans"] = []
                state = self.add_step(state, "generate_actions")
                return state

            issues = state.get("key_issues", [])
            opportunities = state.get("opportunities", [])
            firm_rules = state.get("firm_rules", {})
            historical = state.get("historical_actions", [])

            prompt = f"""Sen bir dijital pazarlama aksiyon planlayıcısısın.
Aşağıdaki sorunlar ve fırsatlar için SOMUT aksiyon planı oluştur.

## SORUNLAR
{json.dumps(issues, ensure_ascii=False, indent=2)}

## FIRSATLAR
{json.dumps(opportunities, ensure_ascii=False, indent=2)}

## FİRMA KURALLARI
- Budget değişiklikleri günlük max €{firm_rules.get('max_daily_budget_change', 50)}
- ROAS < {firm_rules.get('auto_pause_roas_threshold', 1.0)} olan kampanyalar durdurulabilir
- Yeni kampanya başlatma: sadece hafta içi
- Kritik hatalar: hemen bildirim

## GEÇMİŞTE BENZERİ AKSİYONLAR
{json.dumps(historical[:5], ensure_ascii=False, indent=2) if historical else "Geçmiş veri yok"}

## AKSİYON PLANI OLUŞTUR

Her aksiyon için JSON formatında:
{{
    "actions": [
        {{
            "id": "action_001",
            "title": "Kısa başlık",
            "description": "Detaylı açıklama",
            "priority": "CRITICAL/HIGH/MEDIUM/LOW",
            "category": "budget_optimization/campaign_control/keyword_optimization/inventory_alert/tracking_fix",
            "target_platform": "google_ads/meta_ads/shopify/merchant_center",
            "specific_actions": [
                {{"type": "pause_campaign", "campaign_id": "xxx", "reason": "neden"}}
            ],
            "expected_impact": "€50/gün tasarruf",
            "expected_impact_value": 50,
            "risk_level": "low/medium/high",
            "deadline": "immediate/24h/7d",
            "success_metric": "ROAS > 3 in 7 days",
            "rollback_plan": "Kampanyayı tekrar aç"
        }}
    ]
}}

KURALLAR:
- Max 5 aksiyon öner
- Kritik sorunları önce çöz
- Her aksiyona somut adımlar ekle
- Risk minimize et
- Türkçe yaz
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

            # Parse JSON response
            try:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(response[json_start:json_end])
                    actions = result.get("actions", [])

                    # Add confidence and priority score
                    for action in actions:
                        action["confidence"] = 0.8  # Default confidence
                        action["priority_score"] = self._calculate_priority_score(action)

                    state["action_plans"] = actions
            except json.JSONDecodeError:
                state["action_plans"] = []
                logger.warning("action_generation_json_parse_failed")

            logger.info(
                "actions_generated",
                count=len(state["action_plans"])
            )

            state = self.add_step(state, "generate_actions")

        except Exception as e:
            state["errors"].append(f"Action generation failed: {str(e)}")
            logger.error("generate_actions_error", error=str(e))

        return state

    async def prioritize_actions_node(self, state: ActionPlannerState) -> ActionPlannerState:
        """Prioritize actions by impact and urgency."""
        try:
            actions = state.get("action_plans", [])

            # Sort by priority score (descending)
            sorted_actions = sorted(
                actions,
                key=lambda x: x.get("priority_score", 0),
                reverse=True
            )

            # Limit to top 5
            state["action_plans"] = sorted_actions[:5]

            logger.info("actions_prioritized", count=len(state["action_plans"]))
            state = self.add_step(state, "prioritize")

        except Exception as e:
            state["errors"].append(f"Prioritization failed: {str(e)}")
            logger.error("prioritize_error", error=str(e))

        return state

    async def determine_automation_node(self, state: ActionPlannerState) -> ActionPlannerState:
        """Determine automation level for each action."""
        try:
            actions = state.get("action_plans", [])
            firm_rules = state.get("firm_rules", {})

            auto_actions = []
            approval_required = []
            manual_actions = []

            for action in actions:
                category = action.get("category", "")
                risk = action.get("risk_level", "high")
                impact_value = action.get("expected_impact_value", 0)

                # Get automation config for category
                action_config = ACTION_TYPES.get(category, {})
                automation_level = action_config.get("automation_level", AutomationLevel.MANUAL)

                # Determine action type
                if automation_level == AutomationLevel.AUTO:
                    action["action_type"] = "automated"
                    auto_actions.append(action)

                elif automation_level == AutomationLevel.SEMI:
                    # Check if within auto limits
                    max_auto_change = firm_rules.get("max_daily_budget_change", 50)

                    if risk == "low" and impact_value <= max_auto_change:
                        action["action_type"] = "automated"
                        auto_actions.append(action)
                    else:
                        action["action_type"] = "requires_approval"
                        approval_required.append(action)

                else:  # MANUAL
                    action["action_type"] = "manual"
                    manual_actions.append(action)

            state["auto_actions"] = auto_actions
            state["approval_required"] = approval_required
            state["manual_actions"] = manual_actions

            logger.info(
                "automation_determined",
                auto=len(auto_actions),
                approval=len(approval_required),
                manual=len(manual_actions)
            )

            state = self.add_step(state, "determine_automation")

        except Exception as e:
            state["errors"].append(f"Automation determination failed: {str(e)}")
            logger.error("determine_automation_error", error=str(e))

        return state

    async def save_plan_node(self, state: ActionPlannerState) -> ActionPlannerState:
        """Save action plan to file and Memory-Hub."""
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)

            # Generate plan ID
            plan_id = f"plan_{state['brand']}_{state['date']}_{datetime.now().strftime('%H%M%S')}"

            # Build plan document
            plan_doc = {
                "plan_id": plan_id,
                "brand": state["brand"],
                "date": state["date"],
                "created_at": datetime.now().isoformat(),
                "validation_score": state["validation_score"],
                "situation_summary": state["situation_summary"],
                "key_issues": state["key_issues"],
                "opportunities": state["opportunities"],
                "action_plans": state["action_plans"],
                "auto_actions": state["auto_actions"],
                "approval_required": state["approval_required"],
                "manual_actions": state["manual_actions"],
                "firm_rules": state["firm_rules"]
            }

            # Save to JSON file
            json_path = self._output_dir / f"{plan_id}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(plan_doc, f, indent=2, ensure_ascii=False, default=str)

            state["plan_saved"] = True
            state["plan_id"] = plan_id

            logger.info("plan_saved", plan_id=plan_id, path=str(json_path))
            state = self.add_step(state, "save_plan")

        except Exception as e:
            state["errors"].append(f"Plan save failed: {str(e)}")
            logger.error("save_plan_error", error=str(e))

        return state

    async def notify_node(self, state: ActionPlannerState) -> ActionPlannerState:
        """Send notification with action plan summary."""
        try:
            # Only notify if there are actions requiring attention
            approval_count = len(state.get("approval_required", []))
            manual_count = len(state.get("manual_actions", []))
            auto_count = len(state.get("auto_actions", []))

            if approval_count > 0 or manual_count > 0:
                await self._send_telegram_notification(state)

            state["notification_sent"] = True
            state = self.add_step(state, "notify")

            logger.info(
                "notification_sent",
                auto=auto_count,
                approval=approval_count,
                manual=manual_count
            )

        except Exception as e:
            state["errors"].append(f"Notification failed: {str(e)}")
            logger.error("notify_error", error=str(e))

        return state

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _prepare_data_summary(self, validated_data: Dict[str, Dict]) -> str:
        """Prepare data summary for LLM."""
        lines = []

        for source, data in validated_data.items():
            if not data or data.get("error"):
                continue

            lines.append(f"\n### {source.upper()}")
            for key, value in data.items():
                if key in ["total_spend", "total_clicks", "total_impressions",
                           "total_conversions", "total_revenue", "total_orders",
                           "total_sessions", "avg_ctr", "roas"]:
                    lines.append(f"- {key}: {value}")

        return "\n".join(lines) if lines else "Veri yok"

    def _prepare_reports_summary(self, analysis_reports: Dict[str, str]) -> str:
        """Prepare reports summary for LLM."""
        lines = []

        for source, report in analysis_reports.items():
            if report:
                # Truncate long reports
                truncated = report[:500] + "..." if len(report) > 500 else report
                lines.append(f"\n### {source.upper()}\n{truncated}")

        return "\n".join(lines) if lines else "Rapor yok"

    def _calculate_priority_score(self, action: Dict[str, Any]) -> float:
        """Calculate priority score for an action."""
        score = 0.0

        # Priority mapping
        priority_map = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        priority = action.get("priority", "LOW")
        score += priority_map.get(priority, 1) * PRIORITY_WEIGHTS.get("urgency", 2.0)

        # Impact value
        impact = action.get("expected_impact_value", 0)
        score += min(impact / 100, 5) * PRIORITY_WEIGHTS.get("revenue_impact", 3.0)

        # Risk (inverse - low risk = higher score)
        risk_map = {"low": 3, "medium": 2, "high": 1}
        risk = action.get("risk_level", "high")
        score += risk_map.get(risk, 1) * PRIORITY_WEIGHTS.get("ease_of_implementation", 1.0)

        # Confidence
        confidence = action.get("confidence", 0.5)
        score += confidence * 10 * PRIORITY_WEIGHTS.get("confidence", 1.5)

        return round(score, 2)

    async def _send_telegram_notification(self, state: ActionPlannerState) -> bool:
        """Send action plan notification to Telegram."""
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN_ANALYTICS")
            chat_id = os.getenv("TELEGRAM_CHAT_ID_ANALYTICS")

            if not bot_token or not chat_id:
                return False

            # Build message
            auto_count = len(state.get("auto_actions", []))
            approval_count = len(state.get("approval_required", []))
            manual_count = len(state.get("manual_actions", []))

            message = f"""📋 **AKSİYON PLANI**

**Marka:** {state['brand']}
**Tarih:** {state['date']}
**Plan ID:** {state.get('plan_id', 'N/A')}

📊 **DURUM ÖZETİ**
{state.get('situation_summary', 'Özet yok')[:300]}

🎯 **AKSİYONLAR**
- ⚡ Otomatik: {auto_count}
- 🔐 Onay Gerekli: {approval_count}
- 👤 Manuel: {manual_count}

"""
            # Add approval required actions
            if state.get("approval_required"):
                message += "\n🔐 **ONAY BEKLEYEN:**\n"
                for action in state["approval_required"][:3]:
                    message += f"• {action.get('title', 'N/A')}\n"

            message += "\n📁 Detaylar: agent_outputs/action_plans/"

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

    async def plan_actions(
        self,
        validated_data: Dict[str, Dict[str, Any]],
        analysis_reports: Dict[str, str] = None,
        brand: str = "pomandi",
        date: str = None,
        validation_score: float = 1.0
    ) -> Dict[str, Any]:
        """
        Generate action plan based on validated data.

        Args:
            validated_data: Dictionary of validated source data
            analysis_reports: Dictionary of analysis reports per source
            brand: Brand name
            date: Date string
            validation_score: Data quality score

        Returns:
            Action plan result with actions categorized by automation level
        """
        try:
            # Initialize state
            initial_state = init_action_planner_state(
                brand=brand,
                date=date or datetime.now().strftime("%Y-%m-%d"),
                validated_data=validated_data,
                analysis_reports=analysis_reports or {},
                validation_score=validation_score
            )

            # Run graph
            final_state = await self.run(**initial_state)

            # Build result
            return {
                "success": True,
                "plan_id": final_state.get("plan_id"),
                "situation_summary": final_state.get("situation_summary"),
                "key_issues": final_state.get("key_issues", []),
                "opportunities": final_state.get("opportunities", []),
                "action_plans": final_state.get("action_plans", []),
                "auto_actions": final_state.get("auto_actions", []),
                "approval_required": final_state.get("approval_required", []),
                "manual_actions": final_state.get("manual_actions", []),
                "plan_saved": final_state.get("plan_saved", False),
                "notification_sent": final_state.get("notification_sent", False),
                "errors": final_state.get("errors", [])
            }

        except Exception as e:
            logger.error("plan_actions_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
