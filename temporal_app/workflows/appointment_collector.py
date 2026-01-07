"""
Appointment Collector Workflow - Collects appointment data from afspraak database.
"""
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any
import logging

# Import activities
with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.appointment_activities import (
        collect_appointments,
        analyze_appointments,
        save_appointment_report,
    )
    from temporal_app.monitoring import observe_workflow

logger = logging.getLogger(__name__)

@workflow.defn
@observe_workflow
class AppointmentCollectorWorkflow:
    """
    Appointment data collection and analysis workflow.

    Steps:
    1. Collect appointments from afspraak database
    2. Analyze appointment data (conversions, sources, etc.)
    3. Save report to agent_outputs

    Features:
    - Automatic retry on database failures
    - Activity timeout management
    - State persistence (crash recovery)
    - Configurable date range
    """

    @workflow.run
    async def run(self, days: int = 7) -> Dict[str, Any]:
        """
        Execute the appointment collection workflow.

        Args:
            days: Number of days to look back (default: 7)

        Returns:
            Collection results with statistics and report ID
        """
        workflow.logger.info(f"🚀 Starting appointment collector workflow for last {days} days")

        try:
            # Step 1: Collect appointments from database
            workflow.logger.info(f"📊 Step 1: Collecting appointments from last {days} days...")
            appointments_data = await workflow.execute_activity(
                collect_appointments,
                args=[days],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=10),
                    maximum_interval=timedelta(seconds=60),
                    backoff_coefficient=2.0,
                ),
            )

            total_appointments = appointments_data["total"]
            appointments = appointments_data["appointments"]
            workflow.logger.info(f"✅ Collected {total_appointments} appointments")

            # Step 2: Analyze appointments
            workflow.logger.info("🔍 Step 2: Analyzing appointment data...")
            analysis = await workflow.execute_activity(
                analyze_appointments,
                args=[appointments],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                ),
            )

            workflow.logger.info(
                f"✅ Analysis complete - Conversions: {analysis['total_conversions']}, "
                f"Top source: {analysis['top_source']}"
            )

            # Step 3: Save report to agent_outputs
            workflow.logger.info("💾 Step 3: Saving appointment report...")
            report_id = await workflow.execute_activity(
                save_appointment_report,
                args=[days, total_appointments, appointments, analysis],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                ),
            )

            workflow.logger.info(f"✅ Report saved with ID: {report_id}")

            # Build final result
            result = {
                "success": True,
                "days": days,
                "total_appointments": total_appointments,
                "analysis": analysis,
                "report_id": report_id,
                "collected_at": workflow.now().isoformat(),
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
            }

            workflow.logger.info("🎉 Appointment collector workflow completed successfully!")

            return result

        except Exception as e:
            workflow.logger.error(f"❌ Workflow failed: {e}")
            raise
