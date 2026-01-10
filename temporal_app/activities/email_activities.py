"""
Email Assistant Activities
===========================

Temporal activities for email assistant workflow.
"""

from temporalio import activity
import structlog
from typing import Dict, Any

logger = structlog.get_logger(__name__)


@activity.defn
async def run_email_assistant_check(
    check_outlook: bool,
    check_godaddy: bool
) -> Dict[str, Any]:
    """
    Run email assistant graph to check and process emails.

    Args:
        check_outlook: Check Microsoft Outlook account
        check_godaddy: Check GoDaddy Mail account

    Returns:
        Execution summary with counts and results
    """
    activity.logger.info(
        "email_assistant_check_start",
        check_outlook=check_outlook,
        check_godaddy=check_godaddy
    )

    try:
        # Import here to avoid circular imports
        from langgraph_agents.email_assistant_graph import EmailAssistantGraph

        # Initialize graph
        graph = EmailAssistantGraph()
        await graph.initialize()

        # Run email check
        result = await graph.check_emails()

        activity.logger.info(
            "email_assistant_check_complete",
            new_emails=result["new_emails_count"],
            important=result["important_count"],
            spam=result["spam_count"]
        )

        return result

    except Exception as e:
        activity.logger.error(f"email_assistant_check_failed: {str(e)}")
        raise


@activity.defn
async def send_daily_email_summary() -> Dict[str, Any]:
    """
    Send daily email summary to Telegram.

    Returns:
        Summary of sent notification
    """
    import httpx
    import os
    from datetime import datetime

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8419304001:AAHyxGeQiPRikGhOfFMnt1dbCxYgOWzKEso")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6398656014")

    activity.logger.info("send_daily_email_summary_start")

    try:
        # Fetch emails from Outlook and GoDaddy
        # TODO: Use actual MCP calls when integrated
        outlook_count = 3  # Mock for now
        godaddy_count = 2  # Mock for now

        # Build summary message
        today = datetime.now().strftime("%d %B %Y")
        total = outlook_count + godaddy_count

        if total == 0:
            message = f"""📬 Günlük Mail Özeti

📅 {today}

✨ Dün hiç yeni mail gelmedi!

İyi günler! ☀️"""
        else:
            message = f"""📬 Günlük Mail Özeti

📅 {today}

📊 Toplam {total} yeni mail:

⭐ Önemli (2):
  • John Boss: Q1 Budget Review Meeting
  • Client Name: Order Confirmation \\#12345

💼 İş (1):
  • Vendor Support: Your ticket has been resolved

📰 Newsletter (1): Shop Newsletter

🗑️ Spam (1): Otomatik filtrelendi

━━━━━━━━━━━━━━━━━━━━━━

📈 Özet:
  • Outlook: {outlook_count} mail
  • GoDaddy: {godaddy_count} mail
  • Yanıt bekleyen: 2

💡 Detay için /check yazın

İyi günler! ☀️"""

        # Send to Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=30)
            result = response.json()

        if result.get("ok"):
            activity.logger.info(
                "send_daily_email_summary_complete",
                message_id=result["result"]["message_id"]
            )
            return {
                "success": True,
                "message_id": result["result"]["message_id"],
                "emails_count": total
            }
        else:
            activity.logger.error(f"send_daily_email_summary_failed: {result.get('description')}")
            return {
                "success": False,
                "error": result.get("description")
            }

    except Exception as e:
        activity.logger.error(f"send_daily_email_summary_error: {str(e)}")
        raise


@activity.defn
async def process_pending_approvals() -> Dict[str, Any]:
    """
    Check Telegram for approval responses and send approved emails.

    Returns:
        Summary of processed approvals
    """
    activity.logger.info("process_pending_approvals_start")

    try:
        # TODO: Implementation
        # 1. Call telegram-bot MCP: get_updates()
        # 2. Parse callback_data (e.g., "approve:email_reply:12345")
        # 3. For approved replies:
        #    - Get reply draft from memory/state
        #    - Send email via microsoft-outlook or godaddy-mail MCP
        #    - Update pattern usage count
        # 4. For rejected replies:
        #    - Log rejection
        #    - Don't send email

        # Mock for now
        result = {
            "processed": 0,
            "sent": 0,
            "rejected": 0
        }

        activity.logger.info(
            "process_pending_approvals_complete",
            processed=result["processed"],
            sent=result["sent"]
        )

        return result

    except Exception as e:
        activity.logger.error(f"process_pending_approvals_failed: {str(e)}")
        raise
