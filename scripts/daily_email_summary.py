#!/usr/bin/env python3
"""
Daily Email Summary Bot
========================

Her sabah Telegram'a mail özeti gönderir.

Kullanım:
    python scripts/daily_email_summary.py

Environment Variables:
    TELEGRAM_BOT_TOKEN - Bot token
    TELEGRAM_CHAT_ID - Chat ID
"""

import asyncio
import httpx
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Telegram Bot Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8419304001:AAHyxGeQiPRikGhOfFMnt1dbCxYgOWzKEso")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6398656014")


async def send_telegram_message(text: str, parse_mode: str = "Markdown") -> Dict[str, Any]:
    """Send message to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode
        }, timeout=30)
        return response.json()


async def fetch_outlook_emails() -> List[Dict[str, Any]]:
    """Fetch emails from Outlook (last 24 hours)."""
    # TODO: Integrate with Microsoft Outlook MCP
    # For now, return mock data
    return [
        {
            "id": "1",
            "from_email": "boss@company.com",
            "from_name": "John Boss",
            "subject": "Q1 Budget Review Meeting",
            "received_at": datetime.now().isoformat(),
            "is_important": True,
            "category": "work"
        },
        {
            "id": "2",
            "from_email": "client@firma.nl",
            "from_name": "Client Name",
            "subject": "Order Confirmation #12345",
            "received_at": datetime.now().isoformat(),
            "is_important": True,
            "category": "work"
        },
        {
            "id": "3",
            "from_email": "newsletter@shop.com",
            "from_name": "Shop Newsletter",
            "subject": "50% Korting deze week!",
            "received_at": datetime.now().isoformat(),
            "is_important": False,
            "category": "newsletter"
        }
    ]


async def fetch_godaddy_emails() -> List[Dict[str, Any]]:
    """Fetch emails from GoDaddy (last 24 hours)."""
    # TODO: Integrate with GoDaddy Mail MCP
    # For now, return mock data
    return [
        {
            "id": "4",
            "from_email": "support@vendor.com",
            "from_name": "Vendor Support",
            "subject": "Your ticket has been resolved",
            "received_at": datetime.now().isoformat(),
            "is_important": False,
            "category": "automated"
        },
        {
            "id": "5",
            "from_email": "spam@marketing.com",
            "from_name": "Marketing",
            "subject": "Win a FREE iPhone!!!",
            "received_at": datetime.now().isoformat(),
            "is_important": False,
            "category": "spam"
        }
    ]


def categorize_emails(emails: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Categorize emails by type."""
    categories = {
        "important": [],
        "work": [],
        "newsletter": [],
        "automated": [],
        "spam": []
    }

    for email in emails:
        category = email.get("category", "work")
        if email.get("is_important"):
            categories["important"].append(email)
        elif category in categories:
            categories[category].append(email)
        else:
            categories["work"].append(email)

    return categories


def escape_markdown(text: str) -> str:
    """Escape special markdown characters."""
    # Only escape underscores that might break markdown
    return text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")


def build_summary_message(
    outlook_emails: List[Dict[str, Any]],
    godaddy_emails: List[Dict[str, Any]]
) -> str:
    """Build the daily summary message."""

    all_emails = outlook_emails + godaddy_emails
    total_count = len(all_emails)

    if total_count == 0:
        return """📬 Günlük Mail Özeti

📅 {}

✨ Dün hiç yeni mail gelmedi!

İyi günler! ☀️""".format(datetime.now().strftime("%d %B %Y"))

    # Categorize
    categories = categorize_emails(all_emails)

    # Build message
    today = datetime.now().strftime("%d %B %Y")

    message = f"""📬 Günlük Mail Özeti

📅 {today}

📊 Toplam {total_count} yeni mail:
"""

    # Important emails
    if categories["important"]:
        message += f"\n⭐ Önemli ({len(categories['important'])}):\n"
        for email in categories["important"][:5]:  # Max 5
            subject = escape_markdown(email['subject'][:40])
            from_name = escape_markdown(email['from_name'])
            message += f"  • {from_name}: {subject}\n"

    # Work emails
    work_count = len(categories["work"])
    if work_count > 0:
        message += f"\n💼 İş ({work_count}):\n"
        for email in categories["work"][:3]:  # Max 3
            subject = escape_markdown(email['subject'][:40])
            from_name = escape_markdown(email['from_name'])
            message += f"  • {from_name}: {subject}\n"
        if work_count > 3:
            message += f"  ... ve {work_count - 3} mail daha\n"

    # Newsletter
    newsletter_count = len(categories["newsletter"])
    if newsletter_count > 0:
        names = ", ".join([escape_markdown(e["from_name"]) for e in categories["newsletter"][:3]])
        message += f"\n📰 Newsletter ({newsletter_count}): {names}"
        if newsletter_count > 3:
            message += f" +{newsletter_count - 3}"
        message += "\n"

    # Automated
    auto_count = len(categories["automated"])
    if auto_count > 0:
        message += f"\n🤖 Otomatik ({auto_count}): Bildirimler, sistem mesajları\n"

    # Spam
    spam_count = len(categories["spam"])
    if spam_count > 0:
        message += f"\n🗑️ Spam ({spam_count}): Otomatik filtrelendi\n"

    # Summary stats
    needs_response = sum(1 for e in all_emails if e.get("is_important"))

    message += f"""
━━━━━━━━━━━━━━━━━━━━━━

📈 Özet:
  • Outlook: {len(outlook_emails)} mail
  • GoDaddy: {len(godaddy_emails)} mail
  • Yanıt bekleyen: {needs_response}

💡 Detay için /check yazın

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
        outlook_emails = await fetch_outlook_emails()
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
            await send_telegram_message(f"⚠️ *Email Summary Error*\n\n{str(e)}")
        except:
            pass

        raise


async def main():
    """Main entry point."""
    await run_daily_summary()


if __name__ == "__main__":
    asyncio.run(main())
