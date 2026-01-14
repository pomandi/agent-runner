"""
Email Assistant Workflow
=========================

Temporal workflow for email monitoring and management.
Triggered manually by user command - no automatic scheduling.
"""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta

with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.email_activities import (
        run_email_assistant_check,
        process_pending_approvals,
        send_daily_email_summary
    )

# Note: Use workflow.logger inside workflow methods instead of structlog
# structlog causes sandbox restriction issues with Temporal


@workflow.defn
class EmailAssistantWorkflow:
    """
    Email monitoring and management workflow.

    Trigger: Manual (via user command or API)
    Duration: ~10 minutes max
    Retries: 3 attempts with exponential backoff

    Flow:
    1. Run email assistant check (LangGraph agent)
    2. Process pending approvals if any (Telegram callbacks)
    """

    @workflow.run
    async def run(
        self,
        check_outlook: bool = True,
        check_godaddy: bool = True
    ) -> dict:
        """
        Execute email assistant workflow.

        Args:
            check_outlook: Check Microsoft Outlook account
            check_godaddy: Check GoDaddy Mail account

        Returns:
            Execution summary with counts and results
        """
        workflow.logger.info(
            "🔔 Starting email assistant workflow",
            check_outlook=check_outlook,
            check_godaddy=check_godaddy
        )

        # Step 1: Run email assistant check (LangGraph agent)
        result = await workflow.execute_activity(
            run_email_assistant_check,
            args=[check_outlook, check_godaddy],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=10),
                maximum_interval=timedelta(minutes=1),
                backoff_coefficient=2.0
            )
        )

        workflow.logger.info(
            "📊 Email check completed",
            new_emails=result.get("new_emails_count", 0),
            important=result.get("important_count", 0),
            spam=result.get("spam_count", 0),
            archived=result.get("archived_count", 0),
            notifications_sent=result.get("notification_sent", False),
            pending_approval=result.get("pending_approval_count", 0)
        )

        # Step 2: Process pending approvals if any
        if result.get("pending_approval_count", 0) > 0:
            workflow.logger.info("⏳ Processing pending approvals...")

            try:
                approval_result = await workflow.execute_activity(
                    process_pending_approvals,
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=2)
                )

                result["approvals_processed"] = approval_result.get("processed", 0)
                result["replies_sent"] = approval_result.get("sent", 0)

                workflow.logger.info(
                    "✅ Approvals processed",
                    processed=approval_result.get("processed", 0),
                    sent=approval_result.get("sent", 0)
                )
            except Exception as e:
                workflow.logger.error("❌ Approval processing failed", error=str(e))
                result["approval_error"] = str(e)

        workflow.logger.info(
            "✨ Email assistant workflow completed",
            duration=workflow.info().get_current_history_length()
        )

        return result


@workflow.defn
class DailyEmailSummaryWorkflow:
    """
    Daily email summary workflow.

    Trigger: Scheduled (06:00 UTC = 07:00 Amsterdam)
    Duration: ~1 minute max
    Retries: 3 attempts

    Flow:
    1. Fetch email counts from Outlook and GoDaddy
    2. Build summary message
    3. Send to Telegram
    """

    @workflow.run
    async def run(self) -> dict:
        """
        Execute daily email summary workflow.

        Returns:
            Summary of sent notification
        """
        workflow.logger.info("📬 Starting daily email summary workflow")

        result = await workflow.execute_activity(
            send_daily_email_summary,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0
            )
        )

        if result.get("success"):
            workflow.logger.info(
                "✅ Daily email summary sent",
                message_id=result.get("message_id"),
                emails_count=result.get("emails_count")
            )
        else:
            workflow.logger.error(
                "❌ Daily email summary failed",
                error=result.get("error")
            )

        return result
