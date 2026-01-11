"""
SEO Landing Optimizer Workflow

Temporal workflow for daily SEO landing page optimization.
Orchestrates Search Console analysis, page generation, and deployment.

Schedule: Daily at 06:00 Brussels time
"""
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any
import logging

# Import activities using safe imports
with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.seo_activities import (
        fetch_search_console_data,
        run_seo_optimizer_graph,
        get_existing_pages,
        save_page_config,
        trigger_coolify_deployment,
        save_seo_report,
        check_deployment_status,
    )

logger = logging.getLogger(__name__)


@workflow.defn
class SEOLandingOptimizerWorkflow:
    """
    SEO Landing Page Optimizer Workflow.

    Daily workflow that:
    1. Fetches Search Console data
    2. Analyzes keyword opportunities
    3. Generates one new landing page (if opportunity found)
    4. Saves config and triggers deployment
    5. Generates and saves report

    Schedule: Every day at 06:00 Europe/Brussels
    """

    @workflow.run
    async def run(
        self,
        mode: str = "generate",
        days: int = 28,
        skip_deployment: bool = False
    ) -> Dict[str, Any]:
        """
        Execute the SEO landing page optimizer workflow.

        Args:
            mode: Operation mode
                - "analyze": Only analyze, don't generate pages
                - "generate": Analyze and generate one page (default)
                - "report": Generate report only
            days: Number of days of Search Console data
            skip_deployment: Skip Coolify deployment (for testing)

        Returns:
            Workflow result with status, generated page info, and report
        """
        workflow.logger.info(f"🚀 Starting SEO Landing Optimizer: mode={mode}, days={days}")

        result = {
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id,
            "mode": mode,
            "started_at": workflow.now().isoformat(),
            "success": False,
            "steps_completed": [],
            "errors": []
        }

        try:
            # Step 1: Fetch Search Console data
            workflow.logger.info("📊 Step 1: Fetching Search Console data...")
            search_console_data = await workflow.execute_activity(
                fetch_search_console_data,
                args=[days],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=30),
                    maximum_interval=timedelta(minutes=2),
                    backoff_coefficient=2.0,
                ),
            )
            result["steps_completed"].append("fetch_search_console_data")
            result["search_console_summary"] = {
                "queries_count": len(search_console_data.get("top_queries", [])),
                "opportunities_count": len(search_console_data.get("keyword_opportunities", [])),
            }
            workflow.logger.info(
                f"✅ Search Console data fetched: "
                f"{result['search_console_summary']['queries_count']} queries"
            )

            # Step 2: Get existing pages
            workflow.logger.info("📑 Step 2: Checking existing pages...")
            existing_pages = await workflow.execute_activity(
                get_existing_pages,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            result["steps_completed"].append("get_existing_pages")
            result["existing_pages_count"] = len(existing_pages)
            workflow.logger.info(f"✅ Found {len(existing_pages)} existing pages")

            # Step 3: Run SEO optimizer graph (LangGraph)
            workflow.logger.info("🤖 Step 3: Running SEO optimizer graph...")
            optimizer_result = await workflow.execute_activity(
                run_seo_optimizer_graph,
                args=[mode, workflow.now().strftime("%Y-%m-%d"), search_console_data],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(seconds=30),
                ),
            )
            result["steps_completed"].append("run_seo_optimizer_graph")

            # Extract optimizer results
            result["selected_keyword"] = optimizer_result.get("selected_keyword")
            result["selected_template"] = optimizer_result.get("selected_template")
            result["config_validated"] = optimizer_result.get("config_validated", False)
            result["warnings"] = optimizer_result.get("warnings", [])

            if optimizer_result.get("selected_keyword"):
                workflow.logger.info(
                    f"✅ Selected keyword: {result['selected_keyword']} "
                    f"(template: {result['selected_template']})"
                )
            else:
                workflow.logger.warning("⚠️ No suitable keyword opportunity found")

            # Step 4: Save page config (if generated and valid)
            generated_config = optimizer_result.get("generated_config")
            if generated_config and optimizer_result.get("config_validated"):
                workflow.logger.info("💾 Step 4: Saving page config...")
                save_result = await workflow.execute_activity(
                    save_page_config,
                    args=[generated_config],
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                result["steps_completed"].append("save_page_config")
                result["config_saved"] = save_result.get("success", False)
                result["config_file_path"] = save_result.get("file_path")

                if save_result.get("success"):
                    workflow.logger.info(f"✅ Config saved: {save_result.get('file_path')}")
                else:
                    result["errors"].append(f"Failed to save config: {save_result.get('error')}")
                    workflow.logger.error(f"❌ Failed to save config: {save_result.get('error')}")

                # Step 5: Trigger deployment (if config saved and not skipped)
                if result.get("config_saved") and not skip_deployment:
                    workflow.logger.info("🚢 Step 5: Triggering Coolify deployment...")
                    deployment_result = await workflow.execute_activity(
                        trigger_coolify_deployment,
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                    result["steps_completed"].append("trigger_deployment")
                    result["deployment_triggered"] = deployment_result.get("success", False)
                    result["deployment_uuid"] = deployment_result.get("uuid")

                    if deployment_result.get("success"):
                        workflow.logger.info(f"✅ Deployment triggered: {deployment_result.get('uuid')}")

                        # Wait a bit and check status
                        await workflow.sleep(timedelta(seconds=30))

                        status_result = await workflow.execute_activity(
                            check_deployment_status,
                            args=[deployment_result.get("uuid")],
                            start_to_close_timeout=timedelta(minutes=1),
                        )
                        result["deployment_status"] = status_result.get("status")
                        workflow.logger.info(f"📋 Deployment status: {result['deployment_status']}")
                    else:
                        result["errors"].append(f"Deployment failed: {deployment_result.get('error')}")
                        workflow.logger.error(f"❌ Deployment failed: {deployment_result.get('error')}")
                else:
                    result["deployment_triggered"] = False
                    if skip_deployment:
                        workflow.logger.info("⏭️ Deployment skipped (skip_deployment=True)")
            else:
                result["config_saved"] = False
                if not generated_config:
                    workflow.logger.info("ℹ️ No page config generated (no keyword selected)")
                elif not optimizer_result.get("config_validated"):
                    workflow.logger.warning("⚠️ Config validation failed, skipping save")
                    result["errors"].append("Config validation failed")

            # Step 6: Save report
            report_content = optimizer_result.get("report_content", "")
            if report_content:
                workflow.logger.info("📝 Step 6: Saving SEO report...")
                report_result = await workflow.execute_activity(
                    save_seo_report,
                    args=[report_content, workflow.now().strftime("%Y-%m-%d"), {
                        "keyword": result.get("selected_keyword"),
                        "config_saved": result.get("config_saved"),
                        "deployment_triggered": result.get("deployment_triggered"),
                    }],
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                result["steps_completed"].append("save_report")
                result["report_saved"] = report_result.get("success", False)

                if report_result.get("success"):
                    workflow.logger.info("✅ Report saved")
                else:
                    result["errors"].append(f"Failed to save report: {report_result.get('error')}")

            # Mark success
            result["success"] = True
            result["completed_at"] = workflow.now().isoformat()

            # Summary log
            summary = (
                f"SEO Optimizer completed: "
                f"keyword={result.get('selected_keyword', 'None')}, "
                f"config_saved={result.get('config_saved', False)}, "
                f"deployed={result.get('deployment_triggered', False)}, "
                f"warnings={len(result.get('warnings', []))}, "
                f"errors={len(result.get('errors', []))}"
            )
            workflow.logger.info(f"🎉 {summary}")

            return result

        except Exception as e:
            result["success"] = False
            result["errors"].append(str(e))
            result["completed_at"] = workflow.now().isoformat()
            workflow.logger.error(f"❌ SEO Optimizer workflow failed: {e}")
            raise


@workflow.defn
class SEOWeeklyReportWorkflow:
    """
    Weekly SEO performance report workflow.

    Runs every Monday at 09:00 to generate performance report
    for pages created in the past week.
    """

    @workflow.run
    async def run(self) -> Dict[str, Any]:
        """
        Generate weekly SEO performance report.

        Returns:
            Report result with performance metrics
        """
        workflow.logger.info("📊 Starting SEO Weekly Report")

        result = {
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id,
            "report_type": "weekly",
            "started_at": workflow.now().isoformat(),
            "success": False,
        }

        try:
            # Fetch 7 days of Search Console data
            search_console_data = await workflow.execute_activity(
                fetch_search_console_data,
                args=[7],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            # Run optimizer in report mode
            optimizer_result = await workflow.execute_activity(
                run_seo_optimizer_graph,
                args=["report", workflow.now().strftime("%Y-%m-%d"), search_console_data],
                start_to_close_timeout=timedelta(minutes=10),
            )

            # Save report
            report_content = optimizer_result.get("report_content", "")
            if report_content:
                await workflow.execute_activity(
                    save_seo_report,
                    args=[report_content, workflow.now().strftime("%Y-%m-%d"), {
                        "report_type": "weekly"
                    }],
                    start_to_close_timeout=timedelta(minutes=1),
                )

            result["success"] = True
            result["report_generated"] = bool(report_content)
            result["completed_at"] = workflow.now().isoformat()

            workflow.logger.info("✅ SEO Weekly Report completed")
            return result

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["completed_at"] = workflow.now().isoformat()
            workflow.logger.error(f"❌ SEO Weekly Report failed: {e}")
            raise


# Workflow list for registration
SEO_WORKFLOWS = [
    SEOLandingOptimizerWorkflow,
    SEOWeeklyReportWorkflow,
]
