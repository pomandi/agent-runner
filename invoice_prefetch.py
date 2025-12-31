#!/usr/bin/env python3
"""
Invoice Pre-fetch Module

Scans emails from GoDaddy and Outlook for invoice attachments,
extracts metadata via OCR/regex, uploads to R2, and saves to database.

This module does NOT use AI for cost savings - matching is done via SQL later.
"""
import os
import re
import hashlib
import logging
import subprocess
import tempfile
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import json

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("invoice-prefetch")

# Email keywords for invoice search
INVOICE_KEYWORDS = [
    "invoice", "fatura", "factura", "facture", "rechnung",
    "receipt", "recu", "bon", "ticket", "billet",
    "booking", "reservation", "confirmation", "order",
    "payment", "betaling", "paiement", "kwitantie",
    "nota", "bon", "bewijs"
]

# Database connection
DATABASE_URL = os.environ.get(
    "EXPENSE_TRACKER_DB_URL",
    "postgres://postgres:4mXro2JijzR56SARkdGseBpUCw0M1JtdJMT5JbsRUbFPtcGmgnTd4eAEC4hdrEWP@46.224.117.155:5434/expense_tracker"
)

# R2 Storage
R2_BUCKET = os.environ.get("R2_BUCKET_NAME", "pomandi-media")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "https://pub-c6fa7f61f88d43ada51797e7d3a7b5cb.r2.dev")


@dataclass
class PrefetchRun:
    """Tracks a pre-fetch run"""
    id: Optional[int] = None
    started_at: Optional[datetime] = None
    status: str = "running"
    emails_scanned: int = 0
    attachments_found: int = 0
    invoices_created: int = 0
    duplicates_skipped: int = 0
    errors_count: int = 0
    error_details: List[str] = None
    triggered_by: str = "manual"
    email_accounts: List[str] = None
    days_back: int = 30
    keywords: List[str] = None

    def __post_init__(self):
        if self.error_details is None:
            self.error_details = []
        if self.email_accounts is None:
            self.email_accounts = ["godaddy", "outlook"]
        if self.keywords is None:
            self.keywords = INVOICE_KEYWORDS


@dataclass
class EmailAttachment:
    """Represents an email attachment"""
    email_uid: str
    email_account: str
    email_subject: str
    email_from: str
    email_date: str
    filename: str
    content: bytes
    mime_type: str


def get_db_connection():
    """Get PostgreSQL database connection"""
    return psycopg2.connect(DATABASE_URL)


def create_prefetch_run(run: PrefetchRun) -> int:
    """Create a new prefetch run record and return ID"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prefetch_runs (
                    status, emails_scanned, attachments_found, invoices_created,
                    duplicates_skipped, errors_count, error_details, triggered_by,
                    email_accounts, days_back, keywords
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                run.status, run.emails_scanned, run.attachments_found, run.invoices_created,
                run.duplicates_skipped, run.errors_count, json.dumps(run.error_details),
                run.triggered_by, json.dumps(run.email_accounts), run.days_back,
                json.dumps(run.keywords)
            ))
            run_id = cur.fetchone()[0]
            conn.commit()
            return run_id
    finally:
        conn.close()


def update_prefetch_run(run: PrefetchRun):
    """Update prefetch run record"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE prefetch_runs SET
                    status = %s,
                    completed_at = CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE NULL END,
                    emails_scanned = %s,
                    attachments_found = %s,
                    invoices_created = %s,
                    duplicates_skipped = %s,
                    errors_count = %s,
                    error_details = %s
                WHERE id = %s
            """, (
                run.status, run.status, run.emails_scanned, run.attachments_found,
                run.invoices_created, run.duplicates_skipped, run.errors_count,
                json.dumps(run.error_details), run.id
            ))
            conn.commit()
    finally:
        conn.close()


def check_invoice_exists_by_hash(file_hash: str) -> bool:
    """Check if invoice with this hash already exists"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM invoices WHERE file_hash = %s", (file_hash,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def check_invoice_exists_by_email(email_uid: str, email_account: str) -> bool:
    """Check if invoice from this email already exists"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM invoices WHERE source_email_uid = %s AND source_email_account = %s",
                (email_uid, email_account)
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def create_invoice_record(
    file_path: str,
    file_hash: str,
    original_filename: str,
    file_size: int,
    mime_type: str,
    email_uid: str,
    email_account: str,
    email_from: str,
    email_subject: str,
    email_date: str,
    detected_amount: Optional[float],
    detected_date: Optional[str],
    detected_vendor_name: Optional[str],
    ocr_text: Optional[str],
    ocr_confidence: Optional[float]
) -> int:
    """Create invoice record in database"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Generate unique inv_id
            inv_id = f"PRE-{datetime.now().strftime('%Y%m%d%H%M%S')}-{file_hash[:8]}"

            cur.execute("""
                INSERT INTO invoices (
                    inv_id, file_path, file_hash, original_filename, file_size, mime_type,
                    source_type, source_email_uid, source_email_account,
                    email_from, email_subject, email_date,
                    detected_amount, detected_date, detected_vendor_name,
                    ocr_text, ocr_confidence, prefetch_status, prefetched_at, status
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    'prefetch', %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, 'processed', NOW(), 'unmatched'
                )
                RETURNING id
            """, (
                inv_id, file_path, file_hash, original_filename, file_size, mime_type,
                email_uid, email_account,
                email_from, email_subject, email_date,
                detected_amount, detected_date, detected_vendor_name,
                ocr_text, ocr_confidence
            ))
            invoice_id = cur.fetchone()[0]
            conn.commit()
            return invoice_id
    finally:
        conn.close()


def extract_amount(text: str) -> Optional[float]:
    """Extract amount from text using regex patterns"""
    patterns = [
        # Total/Totaal patterns
        r"(?:total|totaal|bedrag|amount|montant|betrag)[:\s]*€?\s*(\d+[.,]\d{2})",
        r"(?:total|totaal|bedrag|amount|montant|betrag)[:\s]*(\d+[.,]\d{2})\s*(?:EUR|€)",
        # Currency symbol patterns
        r"€\s*(\d+[.,]\d{2})",
        r"(\d+[.,]\d{2})\s*€",
        r"(\d+[.,]\d{2})\s*EUR",
        # General amount pattern (larger amounts first)
        r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})",
    ]

    amounts = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                # Normalize the amount
                amount_str = match.replace(",", ".")
                # Handle thousands separator
                if amount_str.count(".") > 1:
                    # Multiple dots = thousands separators
                    parts = amount_str.split(".")
                    amount_str = "".join(parts[:-1]) + "." + parts[-1]
                amount = float(amount_str)
                if 0.01 <= amount <= 100000:  # Reasonable invoice range
                    amounts.append(amount)
            except ValueError:
                continue

    if amounts:
        # Return the highest amount (usually the total)
        return max(amounts)
    return None


def extract_date(text: str) -> Optional[str]:
    """Extract date from text using regex patterns"""
    patterns = [
        # DD/MM/YYYY or DD-MM-YYYY
        (r"(\d{2})[./-](\d{2})[./-](\d{4})", lambda m: f"{m[2]}-{m[1]}-{m[0]}"),
        # YYYY-MM-DD
        (r"(\d{4})[./-](\d{2})[./-](\d{2})", lambda m: f"{m[0]}-{m[1]}-{m[2]}"),
        # Month name patterns
        (r"(\d{1,2})\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{4})",
         lambda m: parse_month_date(m)),
    ]

    for pattern, formatter in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            try:
                date_str = formatter(groups)
                # Validate date
                datetime.strptime(date_str, "%Y-%m-%d")
                return date_str
            except (ValueError, IndexError):
                continue
    return None


def parse_month_date(groups: tuple) -> str:
    """Parse date with month name"""
    month_map = {
        "jan": "01", "january": "01", "feb": "02", "february": "02",
        "mar": "03", "march": "03", "apr": "04", "april": "04",
        "may": "05", "jun": "06", "june": "06",
        "jul": "07", "july": "07", "aug": "08", "august": "08",
        "sep": "09", "september": "09", "oct": "10", "october": "10",
        "nov": "11", "november": "11", "dec": "12", "december": "12"
    }
    day = groups[0].zfill(2)
    month = month_map.get(groups[1].lower()[:3], "01")
    year = groups[2]
    return f"{year}-{month}-{day}"


def extract_vendor_from_email(email_from: str, email_subject: str) -> Optional[str]:
    """Extract vendor name from email sender or subject"""
    # Extract domain from email
    if email_from:
        match = re.search(r"@([^.]+)\.", email_from)
        if match:
            domain = match.group(1)
            # Skip common email providers
            if domain.lower() not in ["gmail", "hotmail", "outlook", "yahoo", "live"]:
                return domain.capitalize()

    # Try to extract from subject
    if email_subject:
        # Common patterns
        patterns = [
            r"(?:from|van|de)\s+([A-Z][A-Za-z0-9]+)",
            r"([A-Z][A-Za-z0-9]+)\s+(?:invoice|receipt|order)",
        ]
        for pattern in patterns:
            match = re.search(pattern, email_subject, re.IGNORECASE)
            if match:
                return match.group(1)

    return None


def extract_text_from_pdf(pdf_content: bytes) -> Tuple[str, float]:
    """Extract text from PDF using pdf-parse or pytesseract"""
    try:
        # Try pdf-parse first (for text-based PDFs)
        import PyPDF2
        import io

        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        text_parts = []
        for page in pdf_reader.pages:
            text_parts.append(page.extract_text() or "")

        text = "\n".join(text_parts)
        if len(text.strip()) > 50:
            return text, 0.95  # High confidence for text extraction

        # Fall back to OCR for image-based PDFs
        return extract_text_with_ocr(pdf_content), 0.7

    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return "", 0.0


def extract_text_from_image(image_content: bytes) -> Tuple[str, float]:
    """Extract text from image using OCR"""
    return extract_text_with_ocr(image_content), 0.7


def extract_text_with_ocr(content: bytes) -> str:
    """Use pytesseract for OCR"""
    try:
        from PIL import Image
        import pytesseract
        import io

        # Handle PDFs
        if content[:4] == b'%PDF':
            # Convert PDF to image
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(content, dpi=150, first_page=1, last_page=1)
            if images:
                text = pytesseract.image_to_string(images[0])
                return text
            return ""

        # Handle images directly
        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image)
        return text

    except Exception as e:
        logger.warning(f"OCR failed: {e}")
        return ""


def upload_to_r2(content: bytes, filename: str) -> Optional[str]:
    """Upload file to Cloudflare R2"""
    try:
        import boto3
        from botocore.config import Config

        # Get R2 credentials
        r2_account_id = os.environ.get("R2_ACCOUNT_ID")
        r2_access_key = os.environ.get("R2_ACCESS_KEY_ID")
        r2_secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")

        if not all([r2_account_id, r2_access_key, r2_secret_key]):
            logger.warning("R2 credentials not configured, saving locally")
            # Save locally instead
            local_path = f"/tmp/invoices/{filename}"
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content)
            return local_path

        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
            config=Config(signature_version="s3v4")
        )

        # Generate unique path
        date_prefix = datetime.now().strftime("%Y/%m")
        r2_path = f"invoices/{date_prefix}/{filename}"

        s3.put_object(
            Bucket=R2_BUCKET,
            Key=r2_path,
            Body=content
        )

        return f"{R2_PUBLIC_URL}/{r2_path}"

    except Exception as e:
        logger.error(f"R2 upload failed: {e}")
        # Save locally as fallback
        local_path = f"/tmp/invoices/{filename}"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(content)
        return local_path


def search_godaddy_emails(days_back: int, keywords: List[str]) -> List[Dict]:
    """Search GoDaddy email for invoices using MCP tool via Claude CLI"""
    emails = []
    since_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    for keyword in keywords[:5]:  # Limit keywords to avoid too many searches
        try:
            # Use Claude CLI with MCP to search
            result = subprocess.run(
                [
                    "claude", "--print", "--mcp-config", "/app/.mcp.json",
                    "--allowedTools", "mcp__godaddy-mail__*",
                    "-p", f"""Use mcp__godaddy-mail__search_emails to search for emails:
- subject: {keyword}
- since: {since_date}
- limit: 50

Return JSON array with email info: [{{"uid": "...", "subject": "...", "from": "...", "date": "..."}}]
Only return the JSON, no explanation."""
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/app"
            )

            if result.returncode == 0:
                # Parse JSON from output
                output = result.stdout.strip()
                start = output.find("[")
                end = output.rfind("]")
                if start != -1 and end != -1:
                    email_list = json.loads(output[start:end+1])
                    for e in email_list:
                        e["account"] = "godaddy"
                    emails.extend(email_list)

        except Exception as e:
            logger.warning(f"GoDaddy search for '{keyword}' failed: {e}")
            continue

    # Deduplicate by UID
    seen_uids = set()
    unique_emails = []
    for e in emails:
        if e.get("uid") not in seen_uids:
            seen_uids.add(e.get("uid"))
            unique_emails.append(e)

    return unique_emails


def search_outlook_emails(days_back: int, keywords: List[str]) -> List[Dict]:
    """Search Outlook email for invoices using MCP tool via Claude CLI"""
    emails = []

    for keyword in keywords[:5]:
        try:
            result = subprocess.run(
                [
                    "claude", "--print", "--mcp-config", "/app/.mcp.json",
                    "--allowedTools", "mcp__microsoft-outlook__*",
                    "-p", f"""Use mcp__microsoft-outlook__search_emails to search for:
- query: {keyword}
- top: 50

Return JSON array: [{{"message_id": "...", "subject": "...", "from": "...", "date": "..."}}]
Only return the JSON."""
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/app"
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                start = output.find("[")
                end = output.rfind("]")
                if start != -1 and end != -1:
                    email_list = json.loads(output[start:end+1])
                    for e in email_list:
                        e["account"] = "outlook"
                        e["uid"] = e.get("message_id", "")
                    emails.extend(email_list)

        except Exception as e:
            logger.warning(f"Outlook search for '{keyword}' failed: {e}")
            continue

    # Deduplicate
    seen_uids = set()
    unique_emails = []
    for e in emails:
        if e.get("uid") not in seen_uids:
            seen_uids.add(e.get("uid"))
            unique_emails.append(e)

    return unique_emails


def get_email_attachments(email: Dict) -> List[Dict]:
    """Get attachments for an email using MCP tools"""
    attachments = []
    account = email.get("account", "godaddy")
    uid = email.get("uid", "")

    if not uid:
        return []

    try:
        if account == "godaddy":
            result = subprocess.run(
                [
                    "claude", "--print", "--mcp-config", "/app/.mcp.json",
                    "--allowedTools", "mcp__godaddy-mail__*",
                    "-p", f"""Use mcp__godaddy-mail__get_attachments with uid="{uid}"
Return JSON array: [{{"filename": "...", "content_type": "..."}}]
Only return the JSON."""
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd="/app"
            )
        else:
            result = subprocess.run(
                [
                    "claude", "--print", "--mcp-config", "/app/.mcp.json",
                    "--allowedTools", "mcp__microsoft-outlook__*",
                    "-p", f"""Use mcp__microsoft-outlook__get_attachments with message_id="{uid}"
Return JSON array: [{{"name": "...", "contentType": "...", "id": "..."}}]
Only return the JSON."""
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd="/app"
            )

        if result.returncode == 0:
            output = result.stdout.strip()
            start = output.find("[")
            end = output.rfind("]")
            if start != -1 and end != -1:
                att_list = json.loads(output[start:end+1])
                for att in att_list:
                    # Filter for PDF and images
                    content_type = att.get("content_type", att.get("contentType", ""))
                    filename = att.get("filename", att.get("name", ""))

                    if any(t in content_type.lower() for t in ["pdf", "image", "jpeg", "png"]):
                        attachments.append({
                            "filename": filename,
                            "content_type": content_type,
                            "id": att.get("id", ""),
                            "account": account,
                            "email_uid": uid
                        })
                    elif filename.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
                        attachments.append({
                            "filename": filename,
                            "content_type": content_type,
                            "id": att.get("id", ""),
                            "account": account,
                            "email_uid": uid
                        })

    except Exception as e:
        logger.warning(f"Get attachments failed for {uid}: {e}")

    return attachments


def download_attachment(attachment: Dict, email: Dict) -> Optional[bytes]:
    """Download attachment content using MCP tools"""
    account = attachment.get("account", "godaddy")
    email_uid = attachment.get("email_uid", "")
    filename = attachment.get("filename", "")
    att_id = attachment.get("id", "")

    temp_path = f"/tmp/dl_{hashlib.md5(filename.encode()).hexdigest()[:8]}_{filename}"

    try:
        if account == "godaddy":
            result = subprocess.run(
                [
                    "claude", "--print", "--mcp-config", "/app/.mcp.json",
                    "--allowedTools", "mcp__godaddy-mail__*",
                    "-p", f"""Use mcp__godaddy-mail__download_attachment to download:
- uid: "{email_uid}"
- filename: "{filename}"
- save_path: "{temp_path}"

Confirm when done."""
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/app"
            )
        else:
            result = subprocess.run(
                [
                    "claude", "--print", "--mcp-config", "/app/.mcp.json",
                    "--allowedTools", "mcp__microsoft-outlook__*",
                    "-p", f"""Use mcp__microsoft-outlook__download_attachment:
- message_id: "{email_uid}"
- attachment_id: "{att_id}"
- save_path: "{temp_path}"

Confirm when done."""
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/app"
            )

        if os.path.exists(temp_path):
            with open(temp_path, "rb") as f:
                content = f.read()
            os.remove(temp_path)
            return content

    except Exception as e:
        logger.warning(f"Download attachment failed: {e}")

    return None


def run_prefetch(
    days_back: int = 30,
    triggered_by: str = "manual",
    email_accounts: List[str] = None
) -> PrefetchRun:
    """
    Main pre-fetch function.
    Scans emails, downloads attachments, extracts metadata, saves to DB.
    """
    if email_accounts is None:
        email_accounts = ["godaddy", "outlook"]

    run = PrefetchRun(
        triggered_by=triggered_by,
        days_back=days_back,
        email_accounts=email_accounts
    )

    # Create run record
    run.id = create_prefetch_run(run)
    logger.info(f"[Prefetch] Starting run {run.id}, days_back={days_back}, accounts={email_accounts}")

    try:
        all_emails = []

        # Search emails
        if "godaddy" in email_accounts:
            godaddy_emails = search_godaddy_emails(days_back, INVOICE_KEYWORDS)
            all_emails.extend(godaddy_emails)
            logger.info(f"[Prefetch] Found {len(godaddy_emails)} emails from GoDaddy")

        if "outlook" in email_accounts:
            outlook_emails = search_outlook_emails(days_back, INVOICE_KEYWORDS)
            all_emails.extend(outlook_emails)
            logger.info(f"[Prefetch] Found {len(outlook_emails)} emails from Outlook")

        run.emails_scanned = len(all_emails)
        update_prefetch_run(run)

        # Process each email
        for email in all_emails:
            try:
                # Check if already processed
                if check_invoice_exists_by_email(email.get("uid", ""), email.get("account", "")):
                    run.duplicates_skipped += 1
                    continue

                # Get attachments
                attachments = get_email_attachments(email)
                run.attachments_found += len(attachments)

                for att in attachments:
                    try:
                        # Download attachment
                        content = download_attachment(att, email)
                        if not content:
                            continue

                        # Calculate hash
                        file_hash = hashlib.sha256(content).hexdigest()

                        # Check duplicate by hash
                        if check_invoice_exists_by_hash(file_hash):
                            run.duplicates_skipped += 1
                            continue

                        # Extract text
                        filename = att.get("filename", "unknown.pdf")
                        if filename.lower().endswith(".pdf"):
                            text, confidence = extract_text_from_pdf(content)
                        else:
                            text, confidence = extract_text_from_image(content)

                        # Extract metadata
                        detected_amount = extract_amount(text)
                        detected_date = extract_date(text)
                        detected_vendor = extract_vendor_from_email(
                            email.get("from", ""),
                            email.get("subject", "")
                        )

                        # Upload to R2
                        unique_filename = f"{file_hash[:12]}_{filename}"
                        file_path = upload_to_r2(content, unique_filename)

                        if not file_path:
                            run.errors_count += 1
                            run.error_details.append(f"Upload failed for {filename}")
                            continue

                        # Create invoice record
                        invoice_id = create_invoice_record(
                            file_path=file_path,
                            file_hash=file_hash,
                            original_filename=filename,
                            file_size=len(content),
                            mime_type=att.get("content_type", "application/pdf"),
                            email_uid=email.get("uid", ""),
                            email_account=email.get("account", ""),
                            email_from=email.get("from", ""),
                            email_subject=email.get("subject", ""),
                            email_date=email.get("date", ""),
                            detected_amount=detected_amount,
                            detected_date=detected_date,
                            detected_vendor_name=detected_vendor,
                            ocr_text=text[:5000] if text else None,  # Limit text size
                            ocr_confidence=confidence
                        )

                        run.invoices_created += 1
                        logger.info(f"[Prefetch] Created invoice {invoice_id} from {filename}")

                    except Exception as e:
                        run.errors_count += 1
                        run.error_details.append(f"Attachment error: {str(e)[:100]}")
                        logger.error(f"[Prefetch] Attachment error: {e}")

            except Exception as e:
                run.errors_count += 1
                run.error_details.append(f"Email error: {str(e)[:100]}")
                logger.error(f"[Prefetch] Email error: {e}")

        run.status = "completed"

    except Exception as e:
        run.status = "failed"
        run.error_details.append(f"Run failed: {str(e)}")
        logger.error(f"[Prefetch] Run failed: {e}")

    update_prefetch_run(run)
    logger.info(f"[Prefetch] Completed run {run.id}: {run.invoices_created} invoices created, "
                f"{run.duplicates_skipped} duplicates, {run.errors_count} errors")

    return run


if __name__ == "__main__":
    # Test run
    run = run_prefetch(days_back=7, triggered_by="test")
    print(f"Run completed: {run.status}")
    print(f"Invoices created: {run.invoices_created}")
