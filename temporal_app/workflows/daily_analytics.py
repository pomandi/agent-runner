"""
Daily Analytics Pipeline Workflow - Full Integrated System
============================================================

This workflow implements the complete closed-loop autonomous system:

    DATA COLLECTION → VALIDATION → ANALYSIS → ACTION PLANNING → EXECUTION

Pipeline Flow:
    1. Data Collection (8 sources)
       └── DailyAnalyticsGraph: Collect from Google Ads, Meta Ads, Shopify, etc.

    2. Data Validation
       └── DataValidatorGraph: Duplicate detection, cross-source verification, anomaly detection

    3. Analysis (if validation passes)
       └── Claude LLM analysis with Turkish reports → Telegram

    4. Action Planning (if validation_score >= 0.70)
       └── ActionPlannerGraph: Generate actionable recommendations

    5. Action Execution (automated actions only, or with approval)
       └── ActionExecutorGraph: Execute via MCP tools

Schedule: Daily 08:00 UTC (10:00 Amsterdam)

Note: FeedbackCollectorGraph runs separately on its own schedule (T+1, T+3, T+7)
"""
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any
import logging

# Import activities
with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.langgraph_activities import (
        run_daily_analytics_graph,
        run_validator_graph,
        run_action_planner_graph,
        run_executor_graph
    )
    from temporal_app.monitoring import observe_workflow

logger = logging.getLogger(__name__)


# =============================================================================
# WORKFLOW CONFIGURATION
# =============================================================================

# Validation threshold for proceeding to analysis
VALIDATION_THRESHOLD = 0.70

# Enable/disable pipeline stages
PIPELINE_CONFIG = {
    "enable_validation": True,
    "enable_action_planning": True,
    "enable_execution": True,
    "execution_dry_run": True,  # Safety: Default to dry-run mode
    "send_telegram_on_validation_fail": True
}


# =============================================================================
# INTEGRATED DAILY ANALYTICS WORKFLOW
# =============================================================================

@workflow.defn
class DailyAnalyticsWorkflow:
    """
    Full integrated daily analytics pipeline.

    Flow:
        ┌─────────────────────────────────────────────────────────────────┐
        │  1. DATA COLLECTION                                             │
        │     └── DailyAnalyticsGraph (8 sources)                        │
        │         └── Output: raw_data, insights, telegram_sent          │
        └─────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────────────────────────────────────────────┐
        │  2. VALIDATION (if enabled)                                     │
        │     └── DataValidatorGraph                                      │
        │         ├── Duplicate detection                                 │
        │         ├── Cross-source verification                           │
        │         └── Anomaly detection                                   │
        │         └── Output: validation_score, proceed_to_analysis      │
        └─────────────────────────┬───────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │ validation_score >= 0.70? │
                    └─────────────┬─────────────┘
                          │               │
                         YES              NO
                          │               │
                          ▼               ▼
        ┌─────────────────────┐   ┌─────────────────────┐
        │  3. ACTION PLANNING │   │  Alert: Human Review │
        │     └── ActionPlan  │   │  (Telegram)          │
        └─────────┬───────────┘   └─────────────────────┘
                  │
                  ▼
        ┌─────────────────────────────────────────────────────────────────┐
        │  4. EXECUTION (if enabled)                                      │
        │     └── ActionExecutorGraph                                     │
        │         ├── Safety checks                                       │
        │         ├── Execute automated actions                           │
        │         └── Log results                                         │
        └─────────────────────────────────────────────────────────────────┘

    Returns comprehensive result with all pipeline stage outputs.
    """

    @workflow.run
    async def run(
        self,
        days: int = 7,
        brand: str = "pomandi",
        config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute the full daily analytics pipeline.

        Args:
            days: Number of days to analyze (default: 7)
            brand: Brand name (pomandi or costume)
            config: Optional override for pipeline config

        Returns:
            Comprehensive result with all pipeline outputs
        """
        # Merge config with defaults
        pipeline_config = {**PIPELINE_CONFIG, **(config or {})}

        # Convert days to int if string
        if isinstance(days, str):
            days = int(days)

        workflow.logger.info(
            f"🚀 Starting Daily Analytics Pipeline for {brand} (last {days} days)"
        )
        workflow.logger.info(f"📋 Config: validation={pipeline_config['enable_validation']}, "
                           f"planning={pipeline_config['enable_action_planning']}, "
                           f"execution={pipeline_config['enable_execution']}, "
                           f"dry_run={pipeline_config['execution_dry_run']}")

        result = {
            "success": False,
            "brand": brand,
            "period_days": days,
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id,
            "pipeline_stages": [],
            "errors": []
        }

        try:
            # ================================================================
            # STAGE 1: DATA COLLECTION
            # ================================================================
            workflow.logger.info("📊 STAGE 1: Data Collection (DailyAnalyticsGraph)")
            result["pipeline_stages"].append("data_collection_started")

            analytics_result = await workflow.execute_activity(
                run_daily_analytics_graph,
                args=[days, brand],
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(minutes=1),
                    maximum_interval=timedelta(minutes=5),
                    backoff_coefficient=2.0,
                ),
            )

            result["data_collection"] = {
                "success": analytics_result.get("success", False),
                "quality_score": analytics_result.get("quality_score", 0.0),
                "telegram_sent": analytics_result.get("telegram_sent", False),
                "insights_count": len(analytics_result.get("insights", [])),
                "errors": analytics_result.get("errors", [])
            }
            result["pipeline_stages"].append("data_collection_completed")

            workflow.logger.info(
                f"✅ Data Collection complete - "
                f"Quality: {analytics_result['quality_score']:.0%}, "
                f"Telegram: {analytics_result['telegram_sent']}"
            )

            # Extract raw data for validation (from insights/recommendations)
            raw_data = self._extract_raw_data_for_validation(analytics_result)

            # ================================================================
            # STAGE 2: VALIDATION
            # ================================================================
            if pipeline_config["enable_validation"]:
                workflow.logger.info("🔍 STAGE 2: Data Validation (ValidatorGraph)")
                result["pipeline_stages"].append("validation_started")

                validation_result = await workflow.execute_activity(
                    run_validator_graph,
                    args=[raw_data, brand, days],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2,
                        initial_interval=timedelta(seconds=30),
                    ),
                )

                result["validation"] = {
                    "score": validation_result.get("validation_score", 0.0),
                    "proceed_to_analysis": validation_result.get("proceed_to_analysis", False),
                    "anomalies_count": len(validation_result.get("anomalies", [])),
                    "duplicates_count": len(validation_result.get("duplicates", [])),
                    "conflicts_count": len(validation_result.get("cross_source_conflicts", [])),
                    "requires_human_review": validation_result.get("requires_human_review", []),
                    "dedup_stats": validation_result.get("dedup_stats", {}),
                    "errors": validation_result.get("errors", [])
                }
                result["pipeline_stages"].append("validation_completed")

                validation_score = validation_result.get("validation_score", 0.0)
                proceed = validation_result.get("proceed_to_analysis", False)

                workflow.logger.info(
                    f"✅ Validation complete - "
                    f"Score: {validation_score:.0%}, "
                    f"Proceed: {proceed}, "
                    f"Anomalies: {len(validation_result.get('anomalies', []))}"
                )

                # Check if we should proceed
                if not proceed or validation_score < VALIDATION_THRESHOLD:
                    workflow.logger.warning(
                        f"⚠️ Validation failed (score={validation_score:.0%} < {VALIDATION_THRESHOLD:.0%}). "
                        f"Stopping pipeline. Human review required."
                    )
                    result["stopped_at"] = "validation"
                    result["stop_reason"] = f"Validation score {validation_score:.0%} below threshold {VALIDATION_THRESHOLD:.0%}"
                    result["success"] = True  # Pipeline completed successfully, just stopped early
                    result["completed_at"] = workflow.now().isoformat()
                    return result
            else:
                workflow.logger.info("⏭️ Validation SKIPPED (disabled in config)")
                validation_result = {"validation_score": 1.0, "proceed_to_analysis": True}

            # ================================================================
            # STAGE 3: ACTION PLANNING
            # ================================================================
            if pipeline_config["enable_action_planning"]:
                workflow.logger.info("📝 STAGE 3: Action Planning (ActionPlannerGraph)")
                result["pipeline_stages"].append("action_planning_started")

                planning_result = await workflow.execute_activity(
                    run_action_planner_graph,
                    args=[validation_result, analytics_result, brand],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2,
                        initial_interval=timedelta(seconds=30),
                    ),
                )

                result["action_planning"] = {
                    "actions_count": planning_result.get("action_count", 0),
                    "auto_actions": len(planning_result.get("auto_actions", [])),
                    "approval_required": len(planning_result.get("approval_required", [])),
                    "manual_actions": len(planning_result.get("manual_actions", [])),
                    "plan_saved": planning_result.get("plan_saved", False),
                    "errors": planning_result.get("errors", [])
                }
                result["pipeline_stages"].append("action_planning_completed")

                workflow.logger.info(
                    f"✅ Action Planning complete - "
                    f"Total: {planning_result.get('action_count', 0)}, "
                    f"Auto: {len(planning_result.get('auto_actions', []))}, "
                    f"Manual: {len(planning_result.get('manual_actions', []))}"
                )

                actions_to_execute = planning_result.get("auto_actions", [])
            else:
                workflow.logger.info("⏭️ Action Planning SKIPPED (disabled in config)")
                actions_to_execute = []

            # ================================================================
            # STAGE 4: EXECUTION
            # ================================================================
            if pipeline_config["enable_execution"] and actions_to_execute:
                workflow.logger.info(
                    f"⚡ STAGE 4: Action Execution (ExecutorGraph) - "
                    f"{len(actions_to_execute)} actions, dry_run={pipeline_config['execution_dry_run']}"
                )
                result["pipeline_stages"].append("execution_started")

                execution_result = await workflow.execute_activity(
                    run_executor_graph,
                    args=[actions_to_execute, brand, pipeline_config["execution_dry_run"]],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(
                        maximum_attempts=1,  # No retry for execution
                    ),
                )

                result["execution"] = {
                    "successful": execution_result.get("successful_count", 0),
                    "failed": execution_result.get("failed_count", 0),
                    "skipped": execution_result.get("skipped_count", 0),
                    "dry_run": execution_result.get("dry_run", True),
                    "safety_passed": execution_result.get("safety_checks_passed", False),
                    "notification_sent": execution_result.get("notification_sent", False),
                    "errors": execution_result.get("errors", [])
                }
                result["pipeline_stages"].append("execution_completed")

                workflow.logger.info(
                    f"✅ Execution complete - "
                    f"Success: {execution_result.get('successful_count', 0)}, "
                    f"Failed: {execution_result.get('failed_count', 0)}, "
                    f"DryRun: {execution_result.get('dry_run', True)}"
                )
            elif not actions_to_execute:
                workflow.logger.info("⏭️ Execution SKIPPED (no automated actions)")
            else:
                workflow.logger.info("⏭️ Execution SKIPPED (disabled in config)")

            # ================================================================
            # PIPELINE COMPLETE
            # ================================================================
            result["success"] = True
            result["pipeline_stages"].append("pipeline_completed")
            result["completed_at"] = workflow.now().isoformat()

            workflow.logger.info(
                f"🎉 Daily Analytics Pipeline COMPLETE for {brand} - "
                f"Stages: {len(result['pipeline_stages'])}"
            )

            return result

        except Exception as e:
            workflow.logger.error(f"❌ Pipeline failed: {e}")
            result["errors"].append(str(e))
            result["completed_at"] = workflow.now().isoformat()
            raise

    def _extract_raw_data_for_validation(self, analytics_result: Dict) -> Dict[str, Any]:
        """
        Extract raw data from analytics result for validation.

        This converts the analytics output into a format suitable
        for the validator graph.
        """
        # In a full implementation, the DailyAnalyticsGraph would
        # return raw_data separately. For now, we construct it from insights.
        raw_data = {
            "google_ads": {"has_data": True},
            "meta_ads": {"has_data": True},
            "shopify": {"has_data": True},
            "visitor_tracking": {"has_data": True},
            "ga4": {"has_data": True},
            "search_console": {"has_data": True},
            "merchant_center": {"has_data": True},
            "appointments": {"has_data": True},
        }

        # Add metrics from analytics result if available
        if analytics_result.get("insights"):
            raw_data["_insights"] = analytics_result["insights"]
        if analytics_result.get("recommendations"):
            raw_data["_recommendations"] = analytics_result["recommendations"]

        return raw_data


# =============================================================================
# WEEKLY ANALYTICS WORKFLOW (Extended Pipeline)
# =============================================================================

@workflow.defn
class WeeklyAnalyticsWorkflow:
    """
    Weekly analytics report - same pipeline with 14 day window.
    """

    @workflow.run
    async def run(self, brand: str = "pomandi") -> Dict[str, Any]:
        """Execute weekly analytics pipeline (14 days)."""
        workflow.logger.info(f"📊 Starting Weekly Analytics Pipeline for {brand}")

        # Run daily workflow with 14 days
        daily_workflow = DailyAnalyticsWorkflow()
        result = await daily_workflow.run(
            days=14,
            brand=brand,
            config={
                "enable_validation": True,
                "enable_action_planning": True,
                "enable_execution": False,  # No auto-execution for weekly
                "execution_dry_run": True
            }
        )

        result["report_type"] = "weekly"
        return result


# =============================================================================
# FEEDBACK COLLECTION WORKFLOW (Separate Schedule)
# =============================================================================

@workflow.defn
class FeedbackCollectionWorkflow:
    """
    Feedback collection workflow - runs separately from main pipeline.

    Schedule: Daily (checks for T+1, T+3, T+7 feedback)
    """

    @workflow.run
    async def run(self, brand: str = "pomandi") -> Dict[str, Any]:
        """Execute feedback collection."""
        from temporal_app.activities.langgraph_activities import run_feedback_collector_graph

        workflow.logger.info(f"📈 Starting Feedback Collection for {brand}")

        result = await workflow.execute_activity(
            run_feedback_collector_graph,
            args=[brand],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
                initial_interval=timedelta(seconds=30),
            ),
        )

        workflow.logger.info(
            f"✅ Feedback Collection complete - "
            f"Success: {result.get('successful_count', 0)}, "
            f"Failed: {result.get('failed_count', 0)}"
        )

        return {
            "success": True,
            "brand": brand,
            "workflow_id": workflow.info().workflow_id,
            "feedback_result": result,
            "completed_at": workflow.now().isoformat()
        }
