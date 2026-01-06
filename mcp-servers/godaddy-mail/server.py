#!/usr/bin/env python3
"""
GoDaddy Mail MCP Server
========================
MCP Server for GoDaddy email access via IMAP and SMTP.

Provides tools for:
- Reading emails from inbox (IMAP)
- Searching emails (IMAP)
- Getting email details (IMAP)
- Listing folders (IMAP)
- Reading/downloading attachments (IMAP)
- Sending emails (SMTP)
- Bulk email sending (SMTP)
- Template-based emails (SMTP)

Environment Variables Required (from .env):
- GODADDY_EMAIL: Email address (e.g., info@pomandi.com)
- GODADDY_PASSWORD: Email password

IMAP Settings:
- Server: imap.secureserver.net
- Port: 993 (SSL)

SMTP Settings:
- Server: smtp.secureserver.net
- Port: 587 (TLS)

Version: 2.0
"""

import asyncio
import json
import os
import sys
import email
import base64
import imaplib
import smtplib
import re
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta
from pathlib import Path
from email.header import decode_header
from email.utils import parsedate_to_datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Server info
SERVER_NAME = "godaddy-mail"
SERVER_VERSION = "2.0.0"

# IMAP Settings
IMAP_SERVER = "imap.secureserver.net"
IMAP_PORT = 993

# SMTP Settings
SMTP_SERVER = "smtp.secureserver.net"
SMTP_PORT = 587  # TLS
SMTP_PORT_SSL = 465  # SSL (alternative)

# Initialize MCP server
server = Server(SERVER_NAME)


def load_env():
    """Load environment variables from .env file (try multiple locations)"""
    env_paths = [
        Path("/app/.env"),  # Coolify deployment
        Path("/home/claude/.claude/agents/agent-runner/.env"),  # Agent runner local
        Path("/home/claude/.claude/agents/unified-analytics/mcp-servers/.env"),  # Legacy local
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
                        if key not in os.environ:
                            os.environ[key] = value
            break  # Use first found .env file


# Load env on import
load_env()


def get_config() -> dict:
    """Get GoDaddy mail configuration"""
    return {
        "email": os.getenv("GODADDY_EMAIL") or os.getenv("EMAIL_HOST_USER", "info@pomandi.com"),
        "password": os.getenv("GODADDY_PASSWORD") or os.getenv("EMAIL_HOST_PASSWORD"),
        "imap_server": IMAP_SERVER,
        "imap_port": IMAP_PORT,
    }


def decode_mime_header(header: str) -> str:
    """Decode MIME encoded header"""
    if not header:
        return ""

    decoded_parts = []
    for part, encoding in decode_header(header):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(encoding or 'utf-8', errors='replace'))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part.decode('utf-8', errors='replace'))
        else:
            decoded_parts.append(str(part))

    return ' '.join(decoded_parts)


def get_email_address(header: str) -> tuple:
    """Extract name and email from header"""
    if not header:
        return ("", "")

    # Decode first
    header = decode_mime_header(header)

    # Parse "Name <email>" format
    match = re.match(r'^(.+?)\s*<(.+?)>$', header)
    if match:
        return (match.group(1).strip().strip('"'), match.group(2))

    # Just email
    return ("", header.strip())


def connect_imap():
    """Connect to IMAP server"""
    config = get_config()

    if not config["password"]:
        raise Exception("GODADDY_PASSWORD not set in environment")

    mail = imaplib.IMAP4_SSL(config["imap_server"], config["imap_port"])
    mail.login(config["email"], config["password"])

    return mail


def connect_smtp():
    """Connect to SMTP server"""
    config = get_config()

    if not config["password"]:
        raise Exception("GODADDY_PASSWORD not set in environment")

    # Use TLS (port 587) - recommended
    smtp = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    smtp.login(config["email"], config["password"])

    return smtp


def parse_email_message(raw_email: bytes, uid: str) -> dict:
    """Parse raw email into structured format"""
    msg = email.message_from_bytes(raw_email)

    # Get headers
    subject = decode_mime_header(msg.get("Subject", "(No Subject)"))
    from_name, from_email = get_email_address(msg.get("From", ""))
    to_header = msg.get("To", "")

    # Parse date
    date_str = msg.get("Date", "")
    try:
        date_obj = parsedate_to_datetime(date_str) if date_str else None
        date_iso = date_obj.isoformat() if date_obj else None
    except (ValueError, TypeError):
        date_iso = date_str

    # Check for attachments and get body
    body = ""
    body_html = ""
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append({
                        "filename": decode_mime_header(filename),
                        "content_type": content_type,
                        "size": len(part.get_payload(decode=True) or b"")
                    })
            elif content_type == "text/plain" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        body = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                    except:
                        body = payload.decode('utf-8', errors='replace')
            elif content_type == "text/html" and not body_html:
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        body_html = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                    except:
                        body_html = payload.decode('utf-8', errors='replace')
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')
            except:
                body = payload.decode('utf-8', errors='replace')

    # If no plain text but have HTML, use that
    if not body and body_html:
        # Strip HTML tags for preview
        body = re.sub(r'<[^>]+>', '', body_html)
        body = re.sub(r'\s+', ' ', body).strip()

    return {
        "uid": uid,
        "subject": subject,
        "from_email": from_email,
        "from_name": from_name,
        "to": to_header,
        "date": date_iso,
        "body": body[:5000] if body else "",  # Limit body size
        "body_html": body_html[:10000] if body_html else "",
        "preview": (body or "")[:200],
        "has_attachments": len(attachments) > 0,
        "attachments": attachments
    }


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    Tool(
        name="get_inbox",
        description="Get emails from inbox. Returns subject, sender, date, preview.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of emails to retrieve (default: 20, max: 100)"
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of emails to skip for pagination (default: 0)"
                }
            }
        }
    ),
    Tool(
        name="search_emails",
        description="Search emails by various criteria (sender, subject, date range).",
        inputSchema={
            "type": "object",
            "properties": {
                "from_address": {
                    "type": "string",
                    "description": "Search by sender email/domain"
                },
                "subject": {
                    "type": "string",
                    "description": "Search in subject line"
                },
                "since": {
                    "type": "string",
                    "description": "Emails since date (YYYY-MM-DD)"
                },
                "before": {
                    "type": "string",
                    "description": "Emails before date (YYYY-MM-DD)"
                },
                "unseen": {
                    "type": "boolean",
                    "description": "Only unread emails (default: false)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 50)"
                }
            }
        }
    ),
    Tool(
        name="get_email",
        description="Get full email details including body content.",
        inputSchema={
            "type": "object",
            "properties": {
                "uid": {
                    "type": "string",
                    "description": "The UID of the email message"
                }
            },
            "required": ["uid"]
        }
    ),
    Tool(
        name="get_folders",
        description="List mail folders (INBOX, Sent, Drafts, etc.).",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    Tool(
        name="get_folder_emails",
        description="Get emails from a specific folder.",
        inputSchema={
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "Folder name (INBOX, Sent, Drafts, Trash, Spam)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of emails (default: 20)"
                }
            },
            "required": ["folder"]
        }
    ),
    Tool(
        name="get_attachments",
        description="Get list of attachments for an email.",
        inputSchema={
            "type": "object",
            "properties": {
                "uid": {
                    "type": "string",
                    "description": "The UID of the email message"
                }
            },
            "required": ["uid"]
        }
    ),
    Tool(
        name="download_attachment",
        description="Download an email attachment and save it to a specified path.",
        inputSchema={
            "type": "object",
            "properties": {
                "uid": {
                    "type": "string",
                    "description": "The UID of the email message"
                },
                "filename": {
                    "type": "string",
                    "description": "The filename of the attachment to download"
                },
                "save_path": {
                    "type": "string",
                    "description": "Full path where the file should be saved"
                }
            },
            "required": ["uid", "filename", "save_path"]
        }
    ),
    Tool(
        name="get_recent_emails",
        description="Get emails received in the last N days.",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days back (default: 7)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 50)"
                }
            }
        }
    ),
    Tool(
        name="get_unread_count",
        description="Get count of unread emails in inbox or specific folder.",
        inputSchema={
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "Folder name (default: INBOX)"
                }
            }
        }
    ),
    Tool(
        name="send_email",
        description="Send an email via SMTP. Supports plain text and HTML content.",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address (or comma-separated list)"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject"
                },
                "body": {
                    "type": "string",
                    "description": "Email body (plain text)"
                },
                "html_body": {
                    "type": "string",
                    "description": "Email body (HTML format, optional)"
                },
                "cc": {
                    "type": "string",
                    "description": "CC recipients (comma-separated, optional)"
                },
                "bcc": {
                    "type": "string",
                    "description": "BCC recipients (comma-separated, optional)"
                },
                "reply_to": {
                    "type": "string",
                    "description": "Reply-to address (optional)"
                }
            },
            "required": ["to", "subject", "body"]
        }
    ),
    Tool(
        name="send_bulk_emails",
        description="Send emails to multiple recipients. Each email is sent individually (not as group mail).",
        inputSchema={
            "type": "object",
            "properties": {
                "recipients": {
                    "type": "array",
                    "description": "List of recipient email addresses",
                    "items": {"type": "string"}
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject (same for all)"
                },
                "body": {
                    "type": "string",
                    "description": "Email body (plain text, same for all)"
                },
                "html_body": {
                    "type": "string",
                    "description": "Email body (HTML, optional)"
                },
                "personalize": {
                    "type": "boolean",
                    "description": "If true, replaces {email} placeholder with recipient's email"
                }
            },
            "required": ["recipients", "subject", "body"]
        }
    ),
    Tool(
        name="send_template_email",
        description="Send email using template with variable substitution. Use {{variable}} in subject/body.",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address"
                },
                "subject_template": {
                    "type": "string",
                    "description": "Subject template with {{variables}}"
                },
                "body_template": {
                    "type": "string",
                    "description": "Body template with {{variables}}"
                },
                "variables": {
                    "type": "object",
                    "description": "Key-value pairs for template variables"
                },
                "html_body_template": {
                    "type": "string",
                    "description": "HTML body template (optional)"
                }
            },
            "required": ["to", "subject_template", "body_template", "variables"]
        }
    )
]


# ============================================================================
# Tool Handlers
# ============================================================================

async def handle_get_inbox(limit: int = 20, offset: int = 0) -> dict:
    """Get inbox emails"""
    limit = min(limit, 100)

    mail = connect_imap()
    try:
        mail.select("INBOX")

        # Search all emails
        _, data = mail.uid('search', None, 'ALL')
        uids = data[0].split()

        # Get latest emails (reverse order)
        uids = list(reversed(uids))
        total = len(uids)

        # Apply pagination
        uids = uids[offset:offset + limit]

        emails = []
        for uid in uids:
            uid_str = uid.decode()
            _, msg_data = mail.uid('fetch', uid, '(RFC822)')

            if msg_data[0] is not None:
                raw_email = msg_data[0][1]
                parsed = parse_email_message(raw_email, uid_str)
                emails.append({
                    "uid": parsed["uid"],
                    "subject": parsed["subject"],
                    "from_email": parsed["from_email"],
                    "from_name": parsed["from_name"],
                    "date": parsed["date"],
                    "preview": parsed["preview"],
                    "has_attachments": parsed["has_attachments"]
                })

        return {
            "total_in_folder": total,
            "returned": len(emails),
            "offset": offset,
            "emails": emails
        }
    finally:
        mail.close()
        mail.logout()


async def handle_search_emails(
    from_address: str = None,
    subject: str = None,
    since: str = None,
    before: str = None,
    unseen: bool = False,
    limit: int = 50
) -> dict:
    """Search emails with criteria"""
    limit = min(limit, 100)

    mail = connect_imap()
    try:
        mail.select("INBOX")

        # Build search criteria
        criteria = []

        if from_address:
            criteria.append(f'FROM "{from_address}"')

        if subject:
            criteria.append(f'SUBJECT "{subject}"')

        if since:
            # Convert YYYY-MM-DD to DD-Mon-YYYY
            dt = datetime.strptime(since, "%Y-%m-%d")
            criteria.append(f'SINCE {dt.strftime("%d-%b-%Y")}')

        if before:
            dt = datetime.strptime(before, "%Y-%m-%d")
            criteria.append(f'BEFORE {dt.strftime("%d-%b-%Y")}')

        if unseen:
            criteria.append('UNSEEN')

        # Default to ALL if no criteria
        search_query = ' '.join(criteria) if criteria else 'ALL'

        _, data = mail.uid('search', None, search_query)
        uids = data[0].split()

        # Get latest first
        uids = list(reversed(uids))[:limit]

        emails = []
        for uid in uids:
            uid_str = uid.decode()
            _, msg_data = mail.uid('fetch', uid, '(RFC822)')

            if msg_data[0] is not None:
                raw_email = msg_data[0][1]
                parsed = parse_email_message(raw_email, uid_str)
                emails.append({
                    "uid": parsed["uid"],
                    "subject": parsed["subject"],
                    "from_email": parsed["from_email"],
                    "from_name": parsed["from_name"],
                    "date": parsed["date"],
                    "preview": parsed["preview"],
                    "has_attachments": parsed["has_attachments"]
                })

        return {
            "search_criteria": search_query,
            "total_found": len(data[0].split()) if data[0] else 0,
            "returned": len(emails),
            "emails": emails
        }
    finally:
        mail.close()
        mail.logout()


async def handle_get_email(uid: str) -> dict:
    """Get full email details"""
    mail = connect_imap()
    try:
        mail.select("INBOX")

        _, msg_data = mail.uid('fetch', uid.encode(), '(RFC822)')

        if msg_data[0] is None:
            raise Exception(f"Email with UID {uid} not found")

        raw_email = msg_data[0][1]
        parsed = parse_email_message(raw_email, uid)

        return parsed
    finally:
        mail.close()
        mail.logout()


async def handle_get_folders() -> dict:
    """List mail folders"""
    mail = connect_imap()
    try:
        _, folders_data = mail.list()

        folders = []
        for folder_info in folders_data:
            if folder_info:
                # Parse folder info: (flags) "delimiter" "name"
                match = re.match(r'\(([^)]*)\)\s+"([^"]*)"\s+"?([^"]*)"?', folder_info.decode())
                if match:
                    flags = match.group(1)
                    name = match.group(3)
                    folders.append({
                        "name": name,
                        "flags": flags
                    })

        return {
            "total_folders": len(folders),
            "folders": folders
        }
    finally:
        mail.logout()


async def handle_get_folder_emails(folder: str, limit: int = 20) -> dict:
    """Get emails from specific folder"""
    limit = min(limit, 100)

    mail = connect_imap()
    try:
        # Select folder (handle special names)
        status, _ = mail.select(folder)
        if status != 'OK':
            raise Exception(f"Could not select folder: {folder}")

        _, data = mail.uid('search', None, 'ALL')
        uids = data[0].split()

        # Get latest first
        uids = list(reversed(uids))[:limit]
        total = len(data[0].split()) if data[0] else 0

        emails = []
        for uid in uids:
            uid_str = uid.decode()
            _, msg_data = mail.uid('fetch', uid, '(RFC822)')

            if msg_data[0] is not None:
                raw_email = msg_data[0][1]
                parsed = parse_email_message(raw_email, uid_str)
                emails.append({
                    "uid": parsed["uid"],
                    "subject": parsed["subject"],
                    "from_email": parsed["from_email"],
                    "from_name": parsed["from_name"],
                    "date": parsed["date"],
                    "preview": parsed["preview"],
                    "has_attachments": parsed["has_attachments"]
                })

        return {
            "folder": folder,
            "total_in_folder": total,
            "returned": len(emails),
            "emails": emails
        }
    finally:
        mail.close()
        mail.logout()


async def handle_get_attachments(uid: str) -> dict:
    """Get email attachments"""
    mail = connect_imap()
    try:
        mail.select("INBOX")

        _, msg_data = mail.uid('fetch', uid.encode(), '(RFC822)')

        if msg_data[0] is None:
            raise Exception(f"Email with UID {uid} not found")

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        attachments = []
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    payload = part.get_payload(decode=True)
                    attachments.append({
                        "filename": decode_mime_header(filename),
                        "content_type": part.get_content_type(),
                        "size": len(payload) if payload else 0
                    })

        return {
            "uid": uid,
            "total_attachments": len(attachments),
            "attachments": attachments
        }
    finally:
        mail.close()
        mail.logout()


async def handle_download_attachment(uid: str, filename: str, save_path: str) -> dict:
    """Download email attachment"""
    mail = connect_imap()
    try:
        mail.select("INBOX")

        _, msg_data = mail.uid('fetch', uid.encode(), '(RFC822)')

        if msg_data[0] is None:
            raise Exception(f"Email with UID {uid} not found")

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Find the attachment
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                part_filename = decode_mime_header(part.get_filename() or "")
                if part_filename == filename or filename in part_filename:
                    payload = part.get_payload(decode=True)
                    if payload:
                        # Ensure directory exists
                        save_dir = Path(save_path).parent
                        save_dir.mkdir(parents=True, exist_ok=True)

                        # Write file
                        with open(save_path, 'wb') as f:
                            f.write(payload)

                        return {
                            "uid": uid,
                            "filename": part_filename,
                            "size": len(payload),
                            "saved_to": save_path,
                            "success": True
                        }

        raise Exception(f"Attachment '{filename}' not found in email {uid}")
    finally:
        mail.close()
        mail.logout()


async def handle_get_recent_emails(days: int = 7, limit: int = 50) -> dict:
    """Get recent emails"""
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return await handle_search_emails(since=since_date, limit=limit)


async def handle_get_unread_count(folder: str = "INBOX") -> dict:
    """Get unread email count"""
    mail = connect_imap()
    try:
        mail.select(folder)

        # Count unseen
        _, data = mail.uid('search', None, 'UNSEEN')
        unread = len(data[0].split()) if data[0] else 0

        # Count all
        _, data = mail.uid('search', None, 'ALL')
        total = len(data[0].split()) if data[0] else 0

        return {
            "folder": folder,
            "unread_count": unread,
            "total_count": total
        }
    finally:
        mail.close()
        mail.logout()


# ============================================================================
# SMTP Tool Handlers (NEW)
# ============================================================================

async def handle_send_email(
    to: str,
    subject: str,
    body: str,
    html_body: str = None,
    cc: str = None,
    bcc: str = None,
    reply_to: str = None
) -> dict:
    """Send a single email"""
    config = get_config()
    smtp = connect_smtp()

    try:
        # Create message
        if html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["From"] = config["email"]
        msg["To"] = to
        msg["Subject"] = subject

        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc
        if reply_to:
            msg["Reply-To"] = reply_to

        # Prepare recipient list
        recipients = [addr.strip() for addr in to.split(",")]
        if cc:
            recipients.extend([addr.strip() for addr in cc.split(",")])
        if bcc:
            recipients.extend([addr.strip() for addr in bcc.split(",")])

        # Send
        smtp.sendmail(config["email"], recipients, msg.as_string())

        return {
            "success": True,
            "from": config["email"],
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "sent_at": datetime.now().isoformat()
        }
    finally:
        smtp.quit()


async def handle_send_bulk_emails(
    recipients: list,
    subject: str,
    body: str,
    html_body: str = None,
    personalize: bool = False
) -> dict:
    """Send emails to multiple recipients individually"""
    config = get_config()
    smtp = connect_smtp()

    sent = []
    failed = []

    try:
        for recipient in recipients:
            try:
                # Personalize if requested
                current_body = body
                current_html = html_body
                current_subject = subject

                if personalize:
                    current_body = body.replace("{email}", recipient)
                    current_subject = subject.replace("{email}", recipient)
                    if html_body:
                        current_html = html_body.replace("{email}", recipient)

                # Create message
                if current_html:
                    msg = MIMEMultipart("alternative")
                    msg.attach(MIMEText(current_body, "plain", "utf-8"))
                    msg.attach(MIMEText(current_html, "html", "utf-8"))
                else:
                    msg = MIMEText(current_body, "plain", "utf-8")

                msg["From"] = config["email"]
                msg["To"] = recipient
                msg["Subject"] = current_subject

                # Send
                smtp.sendmail(config["email"], [recipient], msg.as_string())
                sent.append(recipient)

            except Exception as e:
                failed.append({
                    "email": recipient,
                    "error": str(e)
                })

        return {
            "success": len(failed) == 0,
            "total_recipients": len(recipients),
            "sent_count": len(sent),
            "failed_count": len(failed),
            "sent_to": sent,
            "failed": failed,
            "completed_at": datetime.now().isoformat()
        }
    finally:
        smtp.quit()


async def handle_send_template_email(
    to: str,
    subject_template: str,
    body_template: str,
    variables: dict,
    html_body_template: str = None
) -> dict:
    """Send email using templates with variable substitution"""
    config = get_config()

    # Replace variables in templates
    subject = subject_template
    body = body_template
    html_body = html_body_template

    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        subject = subject.replace(placeholder, str(value))
        body = body.replace(placeholder, str(value))
        if html_body:
            html_body = html_body.replace(placeholder, str(value))

    # Use regular send_email handler
    result = await handle_send_email(
        to=to,
        subject=subject,
        body=body,
        html_body=html_body
    )

    result["template_variables"] = variables
    return result


# Tool handler mapping
TOOL_HANDLERS = {
    # IMAP handlers
    "get_inbox": handle_get_inbox,
    "search_emails": handle_search_emails,
    "get_email": handle_get_email,
    "get_folders": handle_get_folders,
    "get_folder_emails": handle_get_folder_emails,
    "get_attachments": handle_get_attachments,
    "download_attachment": handle_download_attachment,
    "get_recent_emails": handle_get_recent_emails,
    "get_unread_count": handle_get_unread_count,
    # SMTP handlers (NEW)
    "send_email": handle_send_email,
    "send_bulk_emails": handle_send_bulk_emails,
    "send_template_email": handle_send_template_email
}


# ============================================================================
# MCP Server Handlers
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    if name not in TOOL_HANDLERS:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        handler = TOOL_HANDLERS[name]
        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        error_msg = str(e)
        return [TextContent(type="text", text=f"Error: {error_msg}")]


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
