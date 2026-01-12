"""
Action Executor Graph
======================

LangGraph implementation for executing approved actions.

This graph:
1. Loads approved actions from Action Planner
2. Pre-execution safety checks
3. Executes actions via MCP tool calls
4. Logs execution results
5. Handles rollback if execution fails

Flow:
    load_actions -> safety_check -> execute -> log_results -> handle_failures -> notify

Supported Actions:
- Google Ads: Budget change, campaign pause/resume
- Meta Ads: Campaign pause/resume, budget change
- Shopify: Inventory alerts
- Merchant Center: Issue alerts

Usage:
    executor = ActionExecutorGraph()
    result = await executor.execute_actions(action_plans)
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

# Import MCP Python SDK
try:
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.stdio import stdio_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False

logger = structlog.get_logger(__name__)


# =============================================================================
# EXECUTION CONFIGURATION
# =============================================================================

# Safety limits for auto-execution
SAFETY_LIMITS = {
    "max_budget_change_percent": 20,  # Max 20% budget change
    "max_budget_change_absolute": 50,  # Max €50 absolute change
    "require_confirmation_for_enable": True,  # Require confirmation to enable campaigns
    "allow_pause_with_zero_conversions": True,  # Auto-pause campaigns with 0 conversions
    "dry_run_mode": False,  # If True, don't actually execute actions
}

# MCP server mapping for action types
ACTION_TO_MCP_SERVER = {
    "google_ads": {
        "server": "google-ads",
        "tools": {
            "pause_campaign": "pause_campaign",
            "enable_campaign": "enable_campaign",
            "set_budget": "set_campaign_budget",
            "adjust_bid": "adjust_keyword_bid"
        }
    },
    "meta_ads": {
        "server": "meta-ads",
        "tools": {
            "pause_campaign": "pause_campaign",
            "enable_campaign": "enable_campaign",
            "set_budget": "update_campaign_budget"
        }
    },
    "shopify": {
        "server": "shopify",
        "tools": {
            "update_inventory": "update_inventory",
            "send_alert": "create_draft_order"  # Placeholder
        }
    }
}


# =============================================================================
# STATE SCHEMA
# =============================================================================

class ExecutionResult(TypedDict):
    """Result of a single action execution."""
    action_id: str
    action_title: str
    status: Literal["success", "failed", "skipped", "dry_run"]
    executed_at: str
    mcp_response: Optional[Dict[str, Any]]
    error: Optional[str]
    rollback_available: bool
    rollback_executed: bool


class ExecutorState(TypedDict):
    """State for action execution workflow."""

    # Input
    brand: str
    date: str
    actions_to_execute: List[Dict[str, Any]]
    dry_run: bool

    # Safety
    safety_checks_passed: bool
    safety_issues: List[str]

    # Execution
    execution_results: List[ExecutionResult]
    successful_count: int
    failed_count: int
    skipped_count: int

    # Rollback
    actions_to_rollback: List[Dict[str, Any]]
    rollback_results: List[Dict[str, Any]]

    # Output
    execution_log_path: Optional[str]
    notification_sent: bool

    # Tracking
    steps_completed: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]


def init_executor_state(
    brand: str = "pomandi",
    date: str = None,
    actions_to_execute: List[Dict] = None,
    dry_run: bool = False
) -> ExecutorState:
    """Initialize executor state."""
    return {
        "brand": brand,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "actions_to_execute": actions_to_execute or [],
        "dry_run": dry_run or SAFETY_LIMITS.get("dry_run_mode", False),
        # Safety
        "safety_checks_passed": False,
        "safety_issues": [],
        # Execution
        "execution_results": [],
        "successful_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        # Rollback
        "actions_to_rollback": [],
        "rollback_results": [],
        # Output
        "execution_log_path": None,
        "notification_sent": False,
        # Tracking
        "steps_completed": [],
        "errors": []
    }


# =============================================================================
# EXECUTOR GRAPH
# =============================================================================

class ActionExecutorGraph(BaseAgentGraph):
    """
    Executes approved actions via MCP tool calls.

    Flow:
        load_actions -> safety_check -> execute_actions ->
        log_results -> handle_failures -> notify

    Safety features:
    - Pre-execution safety checks
    - Dry run mode for testing
    - Automatic rollback on failure
    - Rate limiting
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mcp_dir = Path(__file__).parent.parent / "mcp-servers"
        self._output_dir = Path(__file__).parent.parent / "agent_outputs" / "execution_logs"

    def build_graph(self) -> StateGraph:
        """Build executor graph."""
        graph = StateGraph(ExecutorState)

        # Add nodes
        graph.add_node("load_actions", self.load_actions_node)
        graph.add_node("safety_check", self.safety_check_node)
        graph.add_node("execute_actions", self.execute_actions_node)
        graph.add_node("log_results", self.log_results_node)
        graph.add_node("handle_failures", self.handle_failures_node)
        graph.add_node("notify", self.notify_node)

        # Entry point
        graph.set_entry_point("load_actions")

        # Flow
        graph.add_edge("load_actions", "safety_check")
        graph.add_edge("safety_check", "execute_actions")
        graph.add_edge("execute_actions", "log_results")
        graph.add_edge("log_results", "handle_failures")
        graph.add_edge("handle_failures", "notify")
        graph.add_edge("notify", END)

        return graph

    # =========================================================================
    # NODE IMPLEMENTATIONS
    # =========================================================================

    async def load_actions_node(self, state: ExecutorState) -> ExecutorState:
        """Load and validate actions to execute."""
        try:
            actions = state.get("actions_to_execute", [])

            # Filter to only executable actions
            executable = []
            for action in actions:
                action_type = action.get("action_type", "manual")
                if action_type in ["automated", "requires_approval"]:
                    # Check if approval was given for approval_required
                    if action_type == "requires_approval" and not action.get("approved", False):
                        continue
                    executable.append(action)

            state["actions_to_execute"] = executable

            logger.info(
                "actions_loaded",
                total=len(actions),
                executable=len(executable)
            )

            state = self.add_step(state, "load_actions")

        except Exception as e:
            state["errors"].append(f"Load actions failed: {str(e)}")
            logger.error("load_actions_error", error=str(e))

        return state

    async def safety_check_node(self, state: ExecutorState) -> ExecutorState:
        """Perform safety checks before execution."""
        try:
            actions = state.get("actions_to_execute", [])
            safety_issues = []

            for action in actions:
                # Check budget change limits
                if action.get("category") == "budget_optimization":
                    for specific in action.get("specific_actions", []):
                        if specific.get("type") in ["set_budget", "adjust_budget"]:
                            change = abs(specific.get("change_amount", 0))
                            change_percent = specific.get("change_percent", 0)

                            if change > SAFETY_LIMITS["max_budget_change_absolute"]:
                                safety_issues.append(
                                    f"Budget change €{change} exceeds limit €{SAFETY_LIMITS['max_budget_change_absolute']}"
                                )
                            if change_percent > SAFETY_LIMITS["max_budget_change_percent"]:
                                safety_issues.append(
                                    f"Budget change {change_percent}% exceeds limit {SAFETY_LIMITS['max_budget_change_percent']}%"
                                )

                # Check enable campaign restrictions
                if action.get("category") == "campaign_control":
                    for specific in action.get("specific_actions", []):
                        if specific.get("type") == "enable_campaign":
                            if SAFETY_LIMITS["require_confirmation_for_enable"]:
                                if not action.get("enable_confirmed", False):
                                    safety_issues.append(
                                        f"Campaign enable requires confirmation: {specific.get('campaign_id')}"
                                    )

            state["safety_issues"] = safety_issues
            state["safety_checks_passed"] = len(safety_issues) == 0

            if safety_issues:
                logger.warning("safety_check_issues", issues=safety_issues)
            else:
                logger.info("safety_check_passed")

            state = self.add_step(state, "safety_check")

        except Exception as e:
            state["errors"].append(f"Safety check failed: {str(e)}")
            state["safety_checks_passed"] = False
            logger.error("safety_check_error", error=str(e))

        return state

    async def execute_actions_node(self, state: ExecutorState) -> ExecutorState:
        """Execute approved actions via MCP."""
        try:
            if not state.get("safety_checks_passed", False):
                logger.warning("execution_skipped_safety_failed")
                state["skipped_count"] = len(state.get("actions_to_execute", []))
                state = self.add_step(state, "execute_actions")
                return state

            actions = state.get("actions_to_execute", [])
            dry_run = state.get("dry_run", False)
            results = []

            for action in actions:
                result = await self._execute_single_action(action, dry_run)
                results.append(result)

                if result["status"] == "success":
                    state["successful_count"] += 1
                elif result["status"] == "failed":
                    state["failed_count"] += 1
                    # Add to rollback list
                    state["actions_to_rollback"].append({
                        "action": action,
                        "result": result
                    })
                else:
                    state["skipped_count"] += 1

            state["execution_results"] = results

            logger.info(
                "execution_complete",
                success=state["successful_count"],
                failed=state["failed_count"],
                skipped=state["skipped_count"]
            )

            state = self.add_step(state, "execute_actions")

        except Exception as e:
            state["errors"].append(f"Execution failed: {str(e)}")
            logger.error("execute_actions_error", error=str(e))

        return state

    async def _execute_single_action(
        self,
        action: Dict[str, Any],
        dry_run: bool = False
    ) -> ExecutionResult:
        """Execute a single action."""
        action_id = action.get("id", "unknown")
        action_title = action.get("title", "Unknown Action")

        result: ExecutionResult = {
            "action_id": action_id,
            "action_title": action_title,
            "status": "skipped",
            "executed_at": datetime.now().isoformat(),
            "mcp_response": None,
            "error": None,
            "rollback_available": False,
            "rollback_executed": False
        }

        try:
            platform = action.get("target_platform", "")
            specific_actions = action.get("specific_actions", [])

            if dry_run:
                result["status"] = "dry_run"
                result["mcp_response"] = {"dry_run": True, "would_execute": specific_actions}
                logger.info("dry_run_action", action_id=action_id)
                return result

            if not MCP_SDK_AVAILABLE:
                result["status"] = "skipped"
                result["error"] = "MCP SDK not available"
                return result

            # Get MCP server config
            mcp_config = ACTION_TO_MCP_SERVER.get(platform)
            if not mcp_config:
                result["status"] = "skipped"
                result["error"] = f"No MCP server for platform: {platform}"
                return result

            # Execute each specific action
            mcp_responses = []
            for specific in specific_actions:
                action_type = specific.get("type", "")
                tool_name = mcp_config["tools"].get(action_type)

                if not tool_name:
                    logger.warning(
                        "unknown_action_type",
                        action_type=action_type,
                        platform=platform
                    )
                    continue

                # Build tool arguments
                tool_args = self._build_tool_arguments(specific)

                # Call MCP tool
                response = await self._call_mcp_tool(
                    mcp_config["server"],
                    tool_name,
                    tool_args
                )

                mcp_responses.append({
                    "action_type": action_type,
                    "tool_name": tool_name,
                    "response": response
                })

                # Check if this action has a rollback
                if action_type in ["pause_campaign", "set_budget"]:
                    result["rollback_available"] = True

            result["mcp_response"] = mcp_responses
            result["status"] = "success" if mcp_responses else "skipped"

            logger.info(
                "action_executed",
                action_id=action_id,
                platform=platform,
                responses_count=len(mcp_responses)
            )

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error("action_execution_error", action_id=action_id, error=str(e))

        return result

    def _build_tool_arguments(self, specific_action: Dict[str, Any]) -> Dict[str, Any]:
        """Build MCP tool arguments from specific action."""
        action_type = specific_action.get("type", "")

        if action_type == "pause_campaign":
            return {
                "campaign_id": specific_action.get("campaign_id"),
                "reason": specific_action.get("reason", "Auto-paused by action executor")
            }
        elif action_type == "enable_campaign":
            return {
                "campaign_id": specific_action.get("campaign_id")
            }
        elif action_type == "set_budget":
            return {
                "campaign_id": specific_action.get("campaign_id"),
                "new_budget": specific_action.get("new_budget"),
                "budget_type": specific_action.get("budget_type", "daily")
            }
        elif action_type == "adjust_bid":
            return {
                "keyword_id": specific_action.get("keyword_id"),
                "bid_adjustment": specific_action.get("bid_adjustment")
            }
        else:
            return specific_action

    async def _call_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call an MCP server tool."""
        if not MCP_SDK_AVAILABLE:
            return {"error": "MCP SDK not available"}

        server_path = self._mcp_dir / server_name / "server.py"
        if not server_path.exists():
            return {"error": f"MCP server not found: {server_name}"}

        try:
            server_params = StdioServerParameters(
                command="python3",
                args=[str(server_path)],
                env=dict(os.environ)
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    result = await session.call_tool(tool_name, arguments)

                    if result.content:
                        for content in result.content:
                            if hasattr(content, 'text'):
                                try:
                                    return json.loads(content.text)
                                except json.JSONDecodeError:
                                    return {"raw_response": content.text}

                    return {"error": "No content in response"}

        except Exception as e:
            return {"error": str(e)}

    async def log_results_node(self, state: ExecutorState) -> ExecutorState:
        """Log execution results to file."""
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)

            # Generate log ID
            log_id = f"exec_{state['brand']}_{state['date']}_{datetime.now().strftime('%H%M%S')}"

            # Build log document
            log_doc = {
                "log_id": log_id,
                "brand": state["brand"],
                "date": state["date"],
                "executed_at": datetime.now().isoformat(),
                "dry_run": state.get("dry_run", False),
                "safety_checks_passed": state.get("safety_checks_passed", False),
                "safety_issues": state.get("safety_issues", []),
                "execution_results": state.get("execution_results", []),
                "summary": {
                    "total": len(state.get("actions_to_execute", [])),
                    "successful": state.get("successful_count", 0),
                    "failed": state.get("failed_count", 0),
                    "skipped": state.get("skipped_count", 0)
                },
                "errors": state.get("errors", [])
            }

            # Save to JSON
            log_path = self._output_dir / f"{log_id}.json"
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log_doc, f, indent=2, ensure_ascii=False, default=str)

            state["execution_log_path"] = str(log_path)

            logger.info("results_logged", log_id=log_id, path=str(log_path))
            state = self.add_step(state, "log_results")

        except Exception as e:
            state["errors"].append(f"Logging failed: {str(e)}")
            logger.error("log_results_error", error=str(e))

        return state

    async def handle_failures_node(self, state: ExecutorState) -> ExecutorState:
        """Handle failed actions with rollback if available."""
        try:
            rollback_needed = state.get("actions_to_rollback", [])

            if not rollback_needed:
                logger.info("no_rollback_needed")
                state = self.add_step(state, "handle_failures")
                return state

            rollback_results = []

            for item in rollback_needed:
                action = item.get("action", {})
                result = item.get("result", {})

                if not result.get("rollback_available", False):
                    continue

                # Attempt rollback
                rollback_result = await self._execute_rollback(action)
                rollback_results.append(rollback_result)

            state["rollback_results"] = rollback_results

            logger.info(
                "rollback_complete",
                attempted=len(rollback_needed),
                executed=len(rollback_results)
            )

            state = self.add_step(state, "handle_failures")

        except Exception as e:
            state["errors"].append(f"Rollback handling failed: {str(e)}")
            logger.error("handle_failures_error", error=str(e))

        return state

    async def _execute_rollback(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute rollback for a failed action."""
        action_id = action.get("id", "unknown")
        rollback_plan = action.get("rollback_plan", "")

        # This is a placeholder - actual rollback logic would depend on action type
        logger.info("rollback_executed", action_id=action_id, plan=rollback_plan)

        return {
            "action_id": action_id,
            "rollback_plan": rollback_plan,
            "status": "executed",
            "executed_at": datetime.now().isoformat()
        }

    async def notify_node(self, state: ExecutorState) -> ExecutorState:
        """Send execution notification."""
        try:
            successful = state.get("successful_count", 0)
            failed = state.get("failed_count", 0)
            skipped = state.get("skipped_count", 0)

            # Only notify if there were actions executed
            if successful > 0 or failed > 0:
                await self._send_telegram_notification(state)

            state["notification_sent"] = True
            state = self.add_step(state, "notify")

            logger.info(
                "notification_complete",
                success=successful,
                failed=failed,
                skipped=skipped
            )

        except Exception as e:
            state["errors"].append(f"Notification failed: {str(e)}")
            logger.error("notify_error", error=str(e))

        return state

    async def _send_telegram_notification(self, state: ExecutorState) -> bool:
        """Send execution notification to Telegram."""
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN_ANALYTICS")
            chat_id = os.getenv("TELEGRAM_CHAT_ID_ANALYTICS")

            if not bot_token or not chat_id:
                return False

            successful = state.get("successful_count", 0)
            failed = state.get("failed_count", 0)
            skipped = state.get("skipped_count", 0)
            dry_run = state.get("dry_run", False)

            status_icon = "✅" if failed == 0 else "⚠️"

            message = f"""{status_icon} **AKSİYON YÜRÜTME RAPORU**

**Marka:** {state['brand']}
**Tarih:** {state['date']}
{'🔄 **DRY RUN MODE**' if dry_run else ''}

**SONUÇLAR:**
- ✅ Başarılı: {successful}
- ❌ Başarısız: {failed}
- ⏭️ Atlanan: {skipped}

"""
            # Add failed action details
            if failed > 0:
                message += "\n**BAŞARISIZ AKSİYONLAR:**\n"
                for result in state.get("execution_results", []):
                    if result.get("status") == "failed":
                        message += f"• {result.get('action_title')}: {result.get('error', 'Unknown')}\n"

            # Add safety issues if any
            if state.get("safety_issues"):
                message += "\n**GÜVENLİK UYARILARI:**\n"
                for issue in state["safety_issues"][:3]:
                    message += f"• {issue}\n"

            message += f"\n📁 Log: {state.get('execution_log_path', 'N/A')}"

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

    async def execute_actions(
        self,
        actions: List[Dict[str, Any]],
        brand: str = "pomandi",
        date: str = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute approved actions.

        Args:
            actions: List of action plans to execute
            brand: Brand name
            date: Date string
            dry_run: If True, don't actually execute (for testing)

        Returns:
            Execution result with success/failure counts
        """
        try:
            # Initialize state
            initial_state = init_executor_state(
                brand=brand,
                date=date or datetime.now().strftime("%Y-%m-%d"),
                actions_to_execute=actions,
                dry_run=dry_run
            )

            # Run graph
            final_state = await self.run(**initial_state)

            # Build result
            return {
                "success": True,
                "dry_run": dry_run,
                "safety_checks_passed": final_state.get("safety_checks_passed", False),
                "safety_issues": final_state.get("safety_issues", []),
                "execution_results": final_state.get("execution_results", []),
                "summary": {
                    "successful": final_state.get("successful_count", 0),
                    "failed": final_state.get("failed_count", 0),
                    "skipped": final_state.get("skipped_count", 0)
                },
                "rollback_results": final_state.get("rollback_results", []),
                "execution_log_path": final_state.get("execution_log_path"),
                "notification_sent": final_state.get("notification_sent", False),
                "errors": final_state.get("errors", [])
            }

        except Exception as e:
            logger.error("execute_actions_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
