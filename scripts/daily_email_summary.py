#!/usr/bin/env python3
"""
Daily Email Summary Bot
========================

Her sabah Telegram'a gerçek mail özeti gönderir.
Microsoft Outlook'tan mailleri çeker ve kategorize eder.

Kullanım:
    python scripts/daily_email_summary.py

Environment Variables:
    TELEGRAM_BOT_TOKEN - Bot token
    TELEGRAM_CHAT_ID - Chat ID
    MICROSOFT_CLIENT_ID - Azure App Client ID
    MICROSOFT_REFRESH_TOKEN - OAuth2 Refresh Token
"""

import asyncio
import httpx
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from pathlib import Path

# Telegram Bot Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8419304001:AAHyxGeQiPRikGhOfFMnt1dbCxYgOWzKEso")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6398656014")


def load_microsoft_env():
    """Load Microsoft credentials from .env files"""
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
                        if key.startswith("MICROSOFT_") or key not in os.environ:
                            os.environ[key] = value


# Load env on import
load_microsoft_env()


async def get_microsoft_access_token() -> str:
    """Get valid access token from Microsoft"""
    client_id = os.environ.get("MICROSOFT_CLIENT_ID")
    refresh_token = os.environ.get("MICROSOFT_REFRESH_TOKEN")

    if not client_id or not refresh_token:
        raise Exception("Microsoft credentials not configured")

    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "https://graph.microsoft.com/Mail.Read offline_access"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")
        return response.json()["access_token"]


async def fetch_outlook_emails(days: int = 1) -> List[Dict[str, Any]]:
    """Fetch emails from Microsoft Outlook (last N days)."""
    try:
        token = await get_microsoft_access_token()

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
                print(f"⚠️ Outlook API error: {response.status_code}")
                return []

            emails = response.json().get("value", [])

            # Normalize to standard format
            normalized = []
            for email in emails:
                sender = email.get("from", {}).get("emailAddress", {})
                normalized.append({
                    "id": email.get("id"),
                    "from_email": sender.get("address", ""),
                    "from_name": sender.get("name", "Unknown"),
                    "subject": email.get("subject", "(No Subject)"),
                    "received_at": email.get("receivedDateTime", ""),
                    "is_read": email.get("isRead", False),
                    "has_attachments": email.get("hasAttachments", False),
                    "importance": email.get("importance", "normal"),
                    "preview": email.get("bodyPreview", "")[:200],
                    "source": "outlook"
                })

            return normalized

    except Exception as e:
        print(f"⚠️ Outlook fetch error: {e}")
        return []


async def fetch_godaddy_emails() -> List[Dict[str, Any]]:
    """Fetch emails from GoDaddy Mail (placeholder for future implementation)."""
    # TODO: Implement GoDaddy Mail integration
    return []


def categorize_email(email: Dict[str, Any]) -> str:
    """Categorize email based on sender and subject"""
    sender_email = email.get("from_email", "").lower()
    subject = email.get("subject", "").lower()
    importance = email.get("importance", "normal")

    # Important - GitHub failures, Google Merchant, Claude status, high importance
    if "github.com" in sender_email and "failed" in subject:
        return "important"
    if "google" in sender_email and "merchant" in sender_email:
        return "important"
    if "statuspage" in sender_email:
        return "important"
    if importance == "high":
        return "important"

    # Work - GitHub, business domains
    if "github.com" in sender_email:
        return "work"
    if any(domain in sender_email for domain in ["pomandi", "saleor", "coolify"]):
        return "work"

    # Newsletter/Marketing
    newsletter_domains = [
        "realtor.com", "zillow.com", "redfin.com", "temu",
        "linkedin.com", "skool.com", "newsletter", "marketing",
        "promo", "deals", "offer"
    ]
    if any(domain in sender_email for domain in newsletter_domains):
        return "newsletter"

    # Default to work
    return "work"


def categorize_emails(emails: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Categorize all emails"""
    categories = {
        "important": [],
        "work": [],
        "newsletter": [],
    }

    for email in emails:
        cat = categorize_email(email)
        categories[cat].append(email)

    return categories


async def send_telegram_message(text: str) -> Dict[str, Any]:
    """Send message to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        }, timeout=30)
        return response.json()


def build_summary_message(
    outlook_emails: List[Dict[str, Any]],
    godaddy_emails: List[Dict[str, Any]]
) -> str:
    """Build the daily summary message."""

    all_emails = outlook_emails + godaddy_emails
    total_count = len(all_emails)
    unread_count = sum(1 for e in all_emails if not e.get("is_read"))

    today = datetime.now().strftime("%d %B %Y")

    if total_count == 0:
        return f"""📬 Günlük Mail Özeti

📅 {today}

✨ Son 24 saatte hiç yeni mail gelmedi!

İyi günler! ☀️"""

    # Categorize
    categories = categorize_emails(all_emails)

    # Build message
    message = f"""📬 Günlük Mail Özeti

📅 {today}

📊 Toplam {total_count} yeni mail ({unread_count} okunmamış)

"""

    # Important emails
    if categories["important"]:
        message += f"⭐ Önemli ({len(categories['important'])}):\n"
        for email in categories["important"][:5]:
            name = email['from_name'][:20]
            subject = email['subject'][:40]
            message += f"  • {name}: {subject}\n"
        message += "\n"

    # Work emails
    if categories["work"]:
        message += f"💼 İş ({len(categories['work'])}):\n"
        for email in categories["work"][:3]:
            name = email['from_name'][:20]
            subject = email['subject'][:40]
            message += f"  • {name}: {subject}\n"
        if len(categories["work"]) > 3:
            message += f"  ... ve {len(categories['work']) - 3} mail daha\n"
        message += "\n"

    # Newsletter
    if categories["newsletter"]:
        names = [e["from_name"][:15] for e in categories["newsletter"][:3]]
        message += f"📰 Newsletter ({len(categories['newsletter'])}): {', '.join(names)}"
        if len(categories["newsletter"]) > 3:
            message += f" +{len(categories['newsletter']) - 3}"
        message += "\n\n"

    # Summary
    message += f"""━━━━━━━━━━━━━━━━━━━━━━

📈 Özet:
  • Outlook: {len(outlook_emails)} mail
  • GoDaddy: {len(godaddy_emails)} mail
  • Önemli: {len(categories['important'])}
  • Okunmamış: {unread_count}

İyi günler! ☀️"""

    return message


async def run_daily_summary():
    """Run the daily email summary."""

    print(f"\n{'='*50}")
    print(f"📬 Daily Email Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    try:
        # Fetch emails
        print("📥 Fetching Outlook emails...")
        outlook_emails = await fetch_outlook_emails(days=1)
        print(f"   Found {len(outlook_emails)} emails")

        print("📥 Fetching GoDaddy emails...")
        godaddy_emails = await fetch_godaddy_emails()
        print(f"   Found {len(godaddy_emails)} emails")

        # Build message
        print("\n📝 Building summary...")
        message = build_summary_message(outlook_emails, godaddy_emails)

        # Send to Telegram
        print("📤 Sending to Telegram...")
        result = await send_telegram_message(message)

        if result.get("ok"):
            print(f"✅ Message sent! (ID: {result['result']['message_id']})")
        else:
            print(f"❌ Failed: {result.get('description', 'Unknown error')}")

        print(f"\n{'='*50}")
        print("✨ Done!")
        print(f"{'='*50}\n")

        return result

    except Exception as e:
        error_msg = f"❌ Daily summary failed: {str(e)}"
        print(error_msg)

        # Try to send error notification
        try:
            await send_telegram_message(f"⚠️ Email Summary Error\n\n{str(e)}")
        except:
            pass

        raise


async def main():
    """Main entry point."""
    await run_daily_summary()


if __name__ == "__main__":
    asyncio.run(main())
