#!/usr/bin/env python3
"""
LLM-Powered Email Assistant
============================

LangGraph agent that uses Claude to:
- Intelligently analyze and categorize emails
- Generate natural language summaries
- Execute actions (move, delete, archive, reply)
- Learn from patterns over time

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    EMAIL ASSISTANT GRAPH                     │
└─────────────────────────────────────────────────────────────┘

  START
    │
    ▼
┌──────────────┐
│ fetch_emails │──── Microsoft Graph API
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ analyze_llm  │──── Claude analyzes each email
└──────┬───────┘     (category, importance, action)
       │
       ▼
┌──────────────┐
│ plan_actions │──── Decide what actions to take
└──────┬───────┘     (based on rules + LLM suggestions)
       │
       ▼
┌──────────────┐
│execute_actions│──── Move spam, archive newsletters, etc.
└──────┬───────┘     (with confirmation if needed)
       │
       ▼
┌──────────────┐
│ gen_summary  │──── Claude generates smart summary
└──────┬───────┘
       │
       ▼
┌──────────────┐
│send_telegram │──── Send to Telegram with action buttons
└──────┬───────┘
       │
       ▼
     END
"""

import asyncio
import json
import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import TypedDict, List, Dict, Any, Optional, Literal, Annotated
from dataclasses import dataclass
import operator
from pathlib import Path

# LangGraph imports
from langgraph.graph import StateGraph, END

# Claude CLI path - uses CLAUDE_CODE_OAUTH_TOKEN from environment
CLAUDE_CLI_PATH = "/home/claude/.local/bin/claude"


# =============================================================================
# Configuration
# =============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8419304001:AAHyxGeQiPRikGhOfFMnt1dbCxYgOWzKEso")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6398656014")


def load_env():
    """Load environment variables from .env files"""
    env_paths = [
        Path("/app/.env"),
        Path("/home/claude/.claude/agents/agent-runner/.env"),
        Path("/home/claude/.claude/agents/unified-analytics/mcp-servers/.env"),
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        if key not in os.environ or key.startswith("MICROSOFT_"):
                            os.environ[key] = value


load_env()


# =============================================================================
# State Schema
# =============================================================================

class EmailData(TypedDict):
    """Single email data structure"""
    id: str
    from_email: str
    from_name: str
    subject: str
    preview: str
    received_at: str
    is_read: bool
    has_attachments: bool
    importance: str
    source: Literal["outlook", "godaddy"]


class EmailAnalysis(TypedDict):
    """LLM analysis result for an email"""
    email_id: str
    category: Literal["important", "work", "personal", "newsletter", "spam", "automated"]
    importance_score: float  # 0-1
    summary: str  # One-line summary
    suggested_action: Literal["keep", "archive", "spam", "delete", "reply"]
    action_reason: str
    requires_response: bool
    response_urgency: Optional[Literal["immediate", "today", "this_week", "no_rush"]]


class PlannedAction(TypedDict):
    """Action to be executed"""
    email_id: str
    action: Literal["move_to_spam", "move_to_archive", "delete", "mark_read", "flag"]
    reason: str
    confirmed: bool  # False = needs user confirmation


class EmailAssistantState(TypedDict):
    """Full state for the email assistant graph"""
    # Input
    days_back: int
    auto_execute_actions: bool  # If True, execute without confirmation

    # Fetched emails
    emails: List[EmailData]
    fetch_error: Optional[str]

    # LLM Analysis
    analyses: List[EmailAnalysis]
    analysis_error: Optional[str]

    # Actions
    planned_actions: List[PlannedAction]
    executed_actions: List[Dict[str, Any]]
    action_errors: List[str]

    # Summary
    summary_text: str
    summary_stats: Dict[str, int]

    # Telegram
    telegram_sent: bool
    telegram_message_id: Optional[int]

    # Execution tracking
    steps_completed: Annotated[List[str], operator.add]


# =============================================================================
# MCP-based Email Fetching (directly uses MCP server handler functions)
# =============================================================================

# Add MCP server path to import path
import sys
_mcp_path = str(Path(__file__).parent.parent / "mcp-servers" / "microsoft-outlook")
if _mcp_path not in sys.path:
    sys.path.insert(0, _mcp_path)

async def fetch_outlook_emails(days: int = 1) -> List[EmailData]:
    """Fetch emails using MCP server handler directly."""
    try:
        # Import handler from MCP server
        from server import handle_get_recent_emails

        # Call the MCP handler directly - it handles auth internally
        result = await handle_get_recent_emails(days=days, top=50, unread_only=False)

        emails = []
        for msg in result.get("emails", []):
            emails.append(EmailData(
                id=msg.get("id", ""),
                from_email=msg.get("from", ""),
                from_name=msg.get("from_name", "Unknown"),
                subject=msg.get("subject", "(No Subject)"),
                preview=msg.get("preview", "")[:300],
                received_at=msg.get("received", ""),
                is_read=msg.get("isRead", False),
                has_attachments=msg.get("hasAttachments", False),
                importance=msg.get("importance", "normal"),
                source="outlook"
            ))

        return emails

    except Exception as e:
        print(f"   ❌ MCP handler error: {e}")
        # Fallback to direct API
        return await fetch_outlook_emails_direct(days)


async def fetch_outlook_emails_direct(days: int = 1) -> List[EmailData]:
    """Direct API fallback - fetch emails from Microsoft Graph API."""
    client_id = os.environ.get("MICROSOFT_CLIENT_ID")
    refresh_token = os.environ.get("MICROSOFT_REFRESH_TOKEN")

    if not client_id or not refresh_token:
        raise Exception("Microsoft credentials not configured")

    # Get token
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.ReadWrite offline_access"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")
        token = response.json()["access_token"]

    # Fetch emails
    since_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    url = "https://graph.microsoft.com/v1.0/me/messages"
    params = {
        "$top": 50,
        "$orderby": "receivedDateTime desc",
        "$filter": f"receivedDateTime ge {since_date}",
        "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,importance,bodyPreview"
    }
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Outlook API error: {response.status_code}")

        emails = []
        for msg in response.json().get("value", []):
            sender = msg.get("from", {}).get("emailAddress", {})
            emails.append(EmailData(
                id=msg.get("id", ""),
                from_email=sender.get("address", ""),
                from_name=sender.get("name", "Unknown"),
                subject=msg.get("subject", "(No Subject)"),
                preview=msg.get("bodyPreview", "")[:300],
                received_at=msg.get("receivedDateTime", ""),
                is_read=msg.get("isRead", False),
                has_attachments=msg.get("hasAttachments", False),
                importance=msg.get("importance", "normal"),
                source="outlook"
            ))

        return emails


async def get_microsoft_token() -> str:
    """Get Microsoft access token using MCP server's auth."""
    try:
        from server import get_access_token
        return await get_access_token()
    except Exception as e:
        # Fallback to direct token refresh
        client_id = os.environ.get("MICROSOFT_CLIENT_ID")
        refresh_token = os.environ.get("MICROSOFT_REFRESH_TOKEN")

        if not client_id or not refresh_token:
            raise Exception("Microsoft credentials not configured")

        token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        data = {
            "client_id": client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.ReadWrite offline_access"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data, timeout=30)
            if response.status_code != 200:
                raise Exception(f"Token refresh failed: {response.text}")
            return response.json()["access_token"]


async def move_email_to_folder(email_id: str, folder: str) -> bool:
    """Move email to a specific folder (spam, archive, deleted)"""
    token = await get_microsoft_token()

    # Map folder names to well-known folder IDs
    folder_map = {
        "spam": "junkemail",
        "archive": "archive",
        "deleted": "deleteditems",
        "inbox": "inbox"
    }

    destination = folder_map.get(folder, folder)

    url = f"https://graph.microsoft.com/v1.0/me/messages/{email_id}/move"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=headers,
            json={"destinationId": destination},
            timeout=30
        )
        return response.status_code == 201


async def delete_email(email_id: str) -> bool:
    """Permanently delete an email"""
    token = await get_microsoft_token()

    url = f"https://graph.microsoft.com/v1.0/me/messages/{email_id}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        response = await client.delete(url, headers=headers, timeout=30)
        return response.status_code == 204


# =============================================================================
# LLM Functions (using Claude CLI subprocess)
# =============================================================================

def _query_claude_subprocess(prompt: str, timeout_seconds: int = 60) -> str:
    """
    Call Claude CLI directly via subprocess.
    Uses CLAUDE_CODE_OAUTH_TOKEN from environment.

    This avoids all async context conflicts with LangGraph.
    """
    import subprocess
    import tempfile
    import os

    try:
        # Write prompt to temp file to avoid shell escaping issues
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            # Build clean env - remove ANTHROPIC_API_KEY which conflicts with OAuth token
            clean_env = {k: v for k, v in os.environ.items() if k != 'ANTHROPIC_API_KEY'}

            # Call Claude CLI with --print flag for non-interactive output
            result = subprocess.run(
                [CLAUDE_CLI_PATH, "--print", "--output-format", "text", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=clean_env  # Pass env WITHOUT ANTHROPIC_API_KEY
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                print(f"   ⚠️ Claude CLI error (code {result.returncode}): {result.stderr[:200]}")
                return ""

        finally:
            # Clean up temp file
            try:
                os.unlink(prompt_file)
            except:
                pass

    except subprocess.TimeoutExpired:
        print(f"   ⚠️ Claude CLI timeout after {timeout_seconds}s")
        return ""
    except Exception as e:
        print(f"   ⚠️ Claude CLI error: {e}")
        return ""


async def query_claude(prompt: str, max_tokens: int = 4096) -> str:
    """
    Query Claude using CLI subprocess.
    Uses CLAUDE_CODE_OAUTH_TOKEN environment variable.
    Runs in thread pool to avoid blocking async event loop.
    """
    import asyncio
    try:
        return await asyncio.to_thread(_query_claude_subprocess, prompt, 90)
    except Exception as e:
        print(f"   ⚠️ Claude query error: {e}")
        return ""


def analyze_with_rules(emails: List[EmailData]) -> List[EmailAnalysis]:
    """Rule-based email analysis (fallback when LLM unavailable)."""
    analyses = []

    for email in emails:
        sender = email["from_email"].lower()
        subject = email["subject"].lower()

        # Default values
        category = "work"
        importance_score = 0.5
        suggested_action = "keep"
        action_reason = "Normal email"
        requires_response = False
        response_urgency = None

        # Important patterns - failures, critical notifications
        if "failed" in subject or "error" in subject or "critical" in subject:
            category = "important"
            importance_score = 0.9
            suggested_action = "keep"
            action_reason = "Requires attention - possible issue"
            requires_response = False
        elif "urgent" in subject or email["importance"] == "high":
            category = "important"
            importance_score = 0.85
            suggested_action = "keep"
            action_reason = "Marked as urgent"
            requires_response = True
            response_urgency = "today"

        # Work patterns - GitHub, business domains
        elif "github.com" in sender:
            category = "work"
            importance_score = 0.6
            suggested_action = "keep" if "failed" in subject else "archive"
            action_reason = "GitHub notification"

        # Newsletter patterns
        elif any(domain in sender for domain in [
            "newsletter", "marketing", "promo", "linkedin.com", "skool.com",
            "realtor.com", "zillow.com", "redfin.com", "temu", "aliexpress"
        ]):
            category = "newsletter"
            importance_score = 0.2
            suggested_action = "archive"
            action_reason = "Newsletter or promotional"

        # Automated patterns
        elif any(kw in subject for kw in ["receipt", "confirmation", "order", "delivery"]):
            category = "automated"
            importance_score = 0.3
            suggested_action = "archive"
            action_reason = "Automated notification"

        # Spam patterns
        elif any(kw in subject for kw in ["winner", "prize", "free", "limited time", "act now"]):
            category = "spam"
            importance_score = 0.1
            suggested_action = "spam"
            action_reason = "Potential spam"

        # Build summary
        summary = f"{email['from_name']}: {email['subject'][:50]}"

        analyses.append(EmailAnalysis(
            email_id=email["id"],
            category=category,
            importance_score=importance_score,
            summary=summary,
            suggested_action=suggested_action,
            action_reason=action_reason,
            requires_response=requires_response,
            response_urgency=response_urgency
        ))

    return analyses


async def analyze_emails_with_llm(emails: List[EmailData]) -> List[EmailAnalysis]:
    """Use Claude Agent SDK to analyze and categorize emails"""

    if not emails:
        return []

    # Build email list for analysis
    email_list = []
    for i, email in enumerate(emails):
        email_list.append(f"""
Email {i+1}:
- ID: {email['id'][:20]}...
- From: {email['from_name']} <{email['from_email']}>
- Subject: {email['subject']}
- Preview: {email['preview'][:200]}
- Time: {email['received_at']}
- Read: {email['is_read']}
- Importance: {email['importance']}
""")

    prompt = f"""Analyze these emails and categorize each one. For each email, determine:

1. **category**: One of: important, work, personal, newsletter, spam, automated
2. **importance_score**: 0.0 to 1.0 (1.0 = very important)
3. **summary**: One short sentence describing the email
4. **suggested_action**: One of: keep, archive, spam, delete
5. **action_reason**: Why this action is suggested
6. **requires_response**: true/false
7. **response_urgency**: immediate, today, this_week, no_rush, or null

Classification Guidelines:
- **important**: Requires immediate attention (failures, urgent business, critical notifications)
- **work**: Work-related but not urgent (GitHub notifications, business emails)
- **personal**: Personal correspondence
- **newsletter**: Marketing, newsletters, subscriptions
- **spam**: Unwanted promotional, scam attempts
- **automated**: System notifications, receipts, confirmations

Action Guidelines:
- **keep**: Important emails that should stay in inbox
- **archive**: Read but not urgent, can be archived
- **spam**: Move to spam folder
- **delete**: Safe to delete (obvious spam, expired promos)

EMAILS TO ANALYZE:
{"".join(email_list)}

Respond with a JSON array of analyses. Example:
[
  {{"email_id": "ABC123...", "category": "work", "importance_score": 0.6, "summary": "GitHub workflow failed", "suggested_action": "keep", "action_reason": "CI failure needs attention", "requires_response": false, "response_urgency": null}}
]

Return ONLY the JSON array, no other text."""

    try:
        response_text = await query_claude(prompt)

        # Clean up response (remove markdown code blocks if present)
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        analyses = json.loads(response_text)

        # Map back to full email IDs
        result = []
        for i, analysis in enumerate(analyses):
            if i < len(emails):
                analysis["email_id"] = emails[i]["id"]
                result.append(EmailAnalysis(**analysis))

        return result

    except Exception as e:
        print(f"   ❌ LLM analysis error: {e}")
        # Fallback to rule-based
        return analyze_with_rules(emails)


async def generate_smart_summary(
    emails: List[EmailData],
    analyses: List[EmailAnalysis],
    executed_actions: List[Dict[str, Any]]
) -> str:
    """Use Claude Agent SDK to generate a natural language summary"""

    # Build context
    stats = {
        "total": len(emails),
        "unread": sum(1 for e in emails if not e["is_read"]),
        "important": sum(1 for a in analyses if a["category"] == "important"),
        "work": sum(1 for a in analyses if a["category"] == "work"),
        "newsletter": sum(1 for a in analyses if a["category"] == "newsletter"),
        "spam": sum(1 for a in analyses if a["category"] == "spam"),
        "needs_response": sum(1 for a in analyses if a.get("requires_response")),
    }

    # Get important email summaries
    important_summaries = [
        f"- {a['summary']}"
        for a in analyses
        if a["category"] in ["important", "work"] and a["importance_score"] > 0.5
    ][:5]

    # Actions taken
    actions_taken = [
        f"- {a['action']}: {a.get('reason', 'N/A')}"
        for a in executed_actions
    ][:5]

    prompt = f"""Generate a brief, friendly daily email summary in Turkish. Be conversational and helpful.

STATISTICS:
- Total emails: {stats['total']}
- Unread: {stats['unread']}
- Important: {stats['important']}
- Work: {stats['work']}
- Newsletter: {stats['newsletter']}
- Spam: {stats['spam']}
- Needs response: {stats['needs_response']}

IMPORTANT EMAILS:
{chr(10).join(important_summaries) if important_summaries else "- Bugün önemli bir mail yok"}

ACTIONS TAKEN:
{chr(10).join(actions_taken) if actions_taken else "- Otomatik aksiyon alınmadı"}

Write a summary that:
1. Starts with a greeting based on time of day
2. Highlights what needs attention
3. Mentions any actions taken
4. Ends with a helpful tip or reminder

Keep it under 500 characters. Use emojis sparingly. Be direct and useful."""

    try:
        response = await query_claude(prompt)

        # Check if response is valid (not empty and not an error message)
        if response and len(response) > 50:
            # Check for error indicators
            error_keywords = ["invalid", "error", "api key", "unauthorized", "failed"]
            if not any(kw in response.lower() for kw in error_keywords):
                return response

        # If response is empty or contains error, use fallback
        print(f"   ⚠️ LLM response invalid, using fallback")
        return generate_fallback_summary(stats, important_summaries, actions_taken)

    except Exception as e:
        print(f"   ❌ Summary generation error: {e}")
        # Fallback to static summary
        return generate_fallback_summary(stats, important_summaries, actions_taken)


def generate_fallback_summary(
    stats: Dict[str, int],
    important_summaries: List[str],
    actions_taken: List[str]
) -> str:
    """Generate a static summary when LLM is not available"""
    today = datetime.now().strftime("%d %B %Y")
    hour = datetime.now().hour

    # Time-based greeting
    if hour < 12:
        greeting = "Günaydın! ☀️"
    elif hour < 18:
        greeting = "İyi günler!"
    else:
        greeting = "İyi akşamlar! 🌙"

    message = f"""📬 Günlük Mail Özeti

📅 {today}

{greeting}

📊 Toplam {stats['total']} yeni mail ({stats['unread']} okunmamış)

"""

    if stats['important'] > 0:
        message += f"⭐ Önemli: {stats['important']}\n"
        for summary in important_summaries[:3]:
            message += f"  {summary}\n"
        message += "\n"

    if stats['work'] > 0:
        message += f"💼 İş: {stats['work']}\n"

    if stats['newsletter'] > 0:
        message += f"📰 Newsletter: {stats['newsletter']}\n"

    if stats['spam'] > 0:
        message += f"🗑️ Spam: {stats['spam']}\n"

    if actions_taken:
        message += "\n⚡ Aksiyonlar:\n"
        for action in actions_taken[:3]:
            message += f"  {action}\n"

    message += "\nİyi günler! 🚀"

    return message


# =============================================================================
# Telegram Functions
# =============================================================================

async def send_telegram_message(text: str, buttons: List[Dict] = None) -> Dict:
    """Send message to Telegram with optional inline buttons"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": buttons
        }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30)
        return response.json()


# =============================================================================
# LangGraph Nodes
# =============================================================================

async def fetch_emails_node(state: EmailAssistantState) -> Dict:
    """Node: Fetch emails from all sources"""
    print("📥 Fetching emails...")

    try:
        emails = await fetch_outlook_emails(days=state.get("days_back", 1))
        print(f"   Found {len(emails)} emails from Outlook")

        return {
            "emails": emails,
            "fetch_error": None,
            "steps_completed": ["fetch_emails"]
        }
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {
            "emails": [],
            "fetch_error": str(e),
            "steps_completed": ["fetch_emails_failed"]
        }


async def analyze_with_llm_node(state: EmailAssistantState) -> Dict:
    """Node: Use LLM to analyze emails"""
    print("🤖 Analyzing emails with LLM...")

    if not state.get("emails"):
        return {
            "analyses": [],
            "analysis_error": "No emails to analyze",
            "steps_completed": ["analyze_skipped"]
        }

    try:
        analyses = await analyze_emails_with_llm(state["emails"])
        print(f"   Analyzed {len(analyses)} emails")

        # Print summary
        categories = {}
        for a in analyses:
            cat = a["category"]
            categories[cat] = categories.get(cat, 0) + 1
        print(f"   Categories: {categories}")

        return {
            "analyses": analyses,
            "analysis_error": None,
            "steps_completed": ["analyze_llm"]
        }
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {
            "analyses": [],
            "analysis_error": str(e),
            "steps_completed": ["analyze_failed"]
        }


async def plan_actions_node(state: EmailAssistantState) -> Dict:
    """Node: Plan actions based on analysis"""
    print("📋 Planning actions...")

    planned = []

    for analysis in state.get("analyses", []):
        action = analysis.get("suggested_action")

        if action == "spam":
            planned.append(PlannedAction(
                email_id=analysis["email_id"],
                action="move_to_spam",
                reason=analysis.get("action_reason", "Identified as spam"),
                confirmed=state.get("auto_execute_actions", False)
            ))
        elif action == "archive":
            planned.append(PlannedAction(
                email_id=analysis["email_id"],
                action="move_to_archive",
                reason=analysis.get("action_reason", "Safe to archive"),
                confirmed=state.get("auto_execute_actions", False)
            ))
        elif action == "delete":
            planned.append(PlannedAction(
                email_id=analysis["email_id"],
                action="delete",
                reason=analysis.get("action_reason", "Safe to delete"),
                confirmed=False  # Always require confirmation for delete
            ))

    print(f"   Planned {len(planned)} actions")

    return {
        "planned_actions": planned,
        "steps_completed": ["plan_actions"]
    }


async def execute_actions_node(state: EmailAssistantState) -> Dict:
    """Node: Execute confirmed actions"""
    print("⚡ Executing actions...")

    executed = []
    errors = []

    for action in state.get("planned_actions", []):
        if not action.get("confirmed"):
            continue

        try:
            email_id = action["email_id"]
            action_type = action["action"]

            if action_type == "move_to_spam":
                success = await move_email_to_folder(email_id, "spam")
            elif action_type == "move_to_archive":
                success = await move_email_to_folder(email_id, "archive")
            elif action_type == "delete":
                success = await delete_email(email_id)
            else:
                success = False

            if success:
                executed.append({
                    "email_id": email_id,
                    "action": action_type,
                    "reason": action.get("reason"),
                    "success": True
                })
                print(f"   ✅ {action_type}: {email_id[:20]}...")
            else:
                errors.append(f"Failed: {action_type} on {email_id[:20]}")

        except Exception as e:
            errors.append(f"Error: {str(e)}")

    print(f"   Executed {len(executed)} actions, {len(errors)} errors")

    return {
        "executed_actions": executed,
        "action_errors": errors,
        "steps_completed": ["execute_actions"]
    }


async def generate_summary_node(state: EmailAssistantState) -> Dict:
    """Node: Generate smart summary with LLM"""
    print("📝 Generating summary...")

    try:
        summary = await generate_smart_summary(
            state.get("emails", []),
            state.get("analyses", []),
            state.get("executed_actions", [])
        )

        # Calculate stats
        analyses = state.get("analyses", [])
        stats = {
            "total": len(state.get("emails", [])),
            "important": sum(1 for a in analyses if a["category"] == "important"),
            "work": sum(1 for a in analyses if a["category"] == "work"),
            "newsletter": sum(1 for a in analyses if a["category"] == "newsletter"),
            "spam": sum(1 for a in analyses if a["category"] == "spam"),
            "actions_taken": len(state.get("executed_actions", []))
        }

        return {
            "summary_text": summary,
            "summary_stats": stats,
            "steps_completed": ["generate_summary"]
        }
    except Exception as e:
        print(f"   ❌ Error: {e}")
        # Fallback to basic summary
        return {
            "summary_text": f"📬 {len(state.get('emails', []))} yeni mail var.",
            "summary_stats": {"total": len(state.get("emails", []))},
            "steps_completed": ["generate_summary_fallback"]
        }


async def send_telegram_node(state: EmailAssistantState) -> Dict:
    """Node: Send summary to Telegram"""
    print("📤 Sending to Telegram...")

    # Build message
    summary = state.get("summary_text", "Mail özeti hazır.")
    stats = state.get("summary_stats", {})

    # Format message with HTML
    today = datetime.now().strftime("%d %B %Y")

    message = f"""📬 <b>Günlük Mail Özeti</b>
📅 {today}

{summary}

━━━━━━━━━━━━━━━━━━━━━━
📊 <b>İstatistikler:</b>
• Toplam: {stats.get('total', 0)}
• Önemli: {stats.get('important', 0)}
• İş: {stats.get('work', 0)}
• Newsletter: {stats.get('newsletter', 0)}
• Spam: {stats.get('spam', 0)}
• Alınan aksiyon: {stats.get('actions_taken', 0)}"""

    # Add action buttons for future commands
    buttons = [
        [
            {"text": "🗑️ Spam Temizle", "callback_data": "action:clean_spam"},
            {"text": "📁 Arşivle", "callback_data": "action:archive_newsletters"}
        ],
        [
            {"text": "🔄 Yenile", "callback_data": "action:refresh"},
            {"text": "⚙️ Ayarlar", "callback_data": "action:settings"}
        ]
    ]

    try:
        result = await send_telegram_message(message, buttons)

        if result.get("ok"):
            msg_id = result["result"]["message_id"]
            print(f"   ✅ Sent! Message ID: {msg_id}")
            return {
                "telegram_sent": True,
                "telegram_message_id": msg_id,
                "steps_completed": ["send_telegram"]
            }
        else:
            print(f"   ❌ Failed: {result}")
            # Try without buttons
            result2 = await send_telegram_message(message.replace("<b>", "").replace("</b>", ""))
            return {
                "telegram_sent": result2.get("ok", False),
                "telegram_message_id": result2.get("result", {}).get("message_id"),
                "steps_completed": ["send_telegram_fallback"]
            }
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {
            "telegram_sent": False,
            "telegram_message_id": None,
            "steps_completed": ["send_telegram_failed"]
        }


# =============================================================================
# Graph Builder
# =============================================================================

def build_email_assistant_graph() -> StateGraph:
    """Build the LangGraph email assistant"""

    # Create graph
    graph = StateGraph(EmailAssistantState)

    # Add nodes
    graph.add_node("fetch_emails", fetch_emails_node)
    graph.add_node("analyze_llm", analyze_with_llm_node)
    graph.add_node("plan_actions", plan_actions_node)
    graph.add_node("execute_actions", execute_actions_node)
    graph.add_node("generate_summary", generate_summary_node)
    graph.add_node("send_telegram", send_telegram_node)

    # Add edges
    graph.set_entry_point("fetch_emails")
    graph.add_edge("fetch_emails", "analyze_llm")
    graph.add_edge("analyze_llm", "plan_actions")
    graph.add_edge("plan_actions", "execute_actions")
    graph.add_edge("execute_actions", "generate_summary")
    graph.add_edge("generate_summary", "send_telegram")
    graph.add_edge("send_telegram", END)

    return graph.compile()


# =============================================================================
# Main Entry Point
# =============================================================================

async def run_email_assistant(
    days_back: int = 1,
    auto_execute: bool = False
) -> Dict[str, Any]:
    """Run the email assistant graph"""

    print("\n" + "="*60)
    print(f"🤖 LLM Email Assistant - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")

    # Build graph
    graph = build_email_assistant_graph()

    # Initial state
    initial_state = EmailAssistantState(
        days_back=days_back,
        auto_execute_actions=auto_execute,
        emails=[],
        fetch_error=None,
        analyses=[],
        analysis_error=None,
        planned_actions=[],
        executed_actions=[],
        action_errors=[],
        summary_text="",
        summary_stats={},
        telegram_sent=False,
        telegram_message_id=None,
        steps_completed=[]
    )

    # Run graph
    result = await graph.ainvoke(initial_state)

    print("\n" + "="*60)
    print("✨ Completed!")
    print(f"Steps: {' → '.join(result.get('steps_completed', []))}")
    print("="*60 + "\n")

    return result


async def main():
    """Main entry point"""
    result = await run_email_assistant(days_back=1, auto_execute=False)

    if result.get("telegram_sent"):
        print(f"✅ Summary sent to Telegram (ID: {result.get('telegram_message_id')})")
    else:
        print("❌ Failed to send summary")


if __name__ == "__main__":
    asyncio.run(main())
