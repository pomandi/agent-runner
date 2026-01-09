"""
Daily Analytics Report Workflow - LangGraph powered multi-source analytics.

This workflow collects data from 8 sources and generates a Turkish analytics report:
1. Google Ads - Kampanya, keyword, conversion
2. Meta Ads - FB/IG kampanya, hedefleme
3. Custom Visitor Tracking - Sessions, events, conversions
4. GA4 - Trafik, kullanici
5. Search Console - SEO, keyword pozisyon
6. Merchant Center - Urun performansi
7. Shopify - Siparis, gelir, musteri
8. Afspraak-DB - Randevu, GCLID/FBCLID attribution

Schedule: Daily 08:00 UTC (10:00 Amsterdam)
"""
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any
import logging

# Import activities
with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.langgraph_activities import run_daily_analytics_graph
    from temporal_app.monitoring import observe_workflow

logger = logging.getLogger(__name__)


@workflow.defn
class DailyAnalyticsWorkflow:
    """
    LangGraph-powered daily analytics report workflow.

    Flow:
    1. Run DailyAnalyticsGraph (LangGraph):
       - Parallel data collection (8 sources)
       - Merge and validate data
       - Claude analysis (Turkish)
       - Generate insights & recommendations
       - Quality check
       - Format report (Markdown)
       - Send to Telegram
    2. Return result

    Features:
    - Multi-source data aggregation
    - Turkish language analysis via Claude
    - Quality-based regeneration loop
    - Telegram delivery
    - Langfuse monitoring
    """

    @workflow.run
    async def run(
        self,
        days: int = 7,
        brand: str = "pomandi"
    ) -> Dict[str, Any]:
        """
        Execute the daily analytics report workflow.

        Args:
            days: Number of days to analyze (default: 7)
            brand: Brand name (pomandi or costume)

        Returns:
            Report result with markdown, insights, delivery status
        """
        workflow.logger.info(f"📊 Starting Daily Analytics for {brand} (last {days} days)")

        try:
            # Run LangGraph analytics workflow
            workflow.logger.info("🤖 Running DailyAnalyticsGraph...")

            graph_result = await workflow.execute_activity(
                run_daily_analytics_graph,
                args=[days, brand],
                start_to_close_timeout=timedelta(minutes=15),  # Long timeout for data collection
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(minutes=1),
                    maximum_interval=timedelta(minutes=5),
                    backoff_coefficient=2.0,
                ),
            )

            workflow.logger.info(
                f"✅ LangGraph complete - "
                f"Quality: {graph_result['quality_score']:.0%}, "
                f"Telegram: {graph_result['telegram_sent']}, "
                f"Insights: {len(graph_result['insights'])}"
            )

            # Build final result
            result = {
                "success": graph_result["success"],
                "brand": brand,
                "period_days": days,
                "report_markdown": graph_result["report_markdown"],
                "insights": graph_result["insights"],
                "recommendations": graph_result["recommendations"],
                "quality_score": graph_result["quality_score"],
                "telegram_sent": graph_result["telegram_sent"],
                "telegram_message_id": graph_result.get("telegram_message_id"),
                "errors": graph_result["errors"],
                "steps_completed": graph_result["steps_completed"],
                "regenerate_attempts": graph_result.get("regenerate_attempts", 0),
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
                "completed_at": workflow.now().isoformat()
            }

            # Log outcome
            if result["success"] and result["telegram_sent"]:
                workflow.logger.info("🎉 Daily analytics complete - Report sent to Telegram!")
            elif result["success"]:
                workflow.logger.warning("⚠️  Report generated but Telegram delivery failed")
            else:
                workflow.logger.error(f"❌ Daily analytics failed - Errors: {result['errors']}")

            return result

        except Exception as e:
            workflow.logger.error(f"❌ Daily analytics workflow failed: {e}")
            raise


@workflow.defn
class WeeklyAnalyticsWorkflow:
    """
    Weekly analytics report - more comprehensive analysis.

    Same as DailyAnalyticsWorkflow but with 14 day window
    and more detailed breakdown.
    """

    @workflow.run
    async def run(self, brand: str = "pomandi") -> Dict[str, Any]:
        """Execute weekly analytics report (14 days)."""
        workflow.logger.info(f"📊 Starting Weekly Analytics for {brand}")

        try:
            graph_result = await workflow.execute_activity(
                run_daily_analytics_graph,
                args=[14, brand],  # 14 days for weekly
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(minutes=2),
                ),
            )

            result = {
                "success": graph_result["success"],
                "brand": brand,
                "period_days": 14,
                "report_markdown": graph_result["report_markdown"],
                "insights": graph_result["insights"],
                "recommendations": graph_result["recommendations"],
                "quality_score": graph_result["quality_score"],
                "telegram_sent": graph_result["telegram_sent"],
                "workflow_id": workflow.info().workflow_id,
                "completed_at": workflow.now().isoformat()
            }

            workflow.logger.info(f"🎉 Weekly analytics complete for {brand}")
            return result

        except Exception as e:
            workflow.logger.error(f"❌ Weekly analytics failed: {e}")
            raise
