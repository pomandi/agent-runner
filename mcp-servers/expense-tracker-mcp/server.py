#!/usr/bin/env python3
"""
Pomandi Expense Tracker MCP Server

MCP server for managing expense tracking operations:
- Vendor management (list, details, update instructions)
- Transaction tracking (list, status, close)
- Invoice extraction and matching
- Q4 accounting progress tracking

Database: PostgreSQL on Coolify (Hetzner)
"""

import os
import json
import asyncio
import base64
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

import asyncpg
import boto3
from botocore.config import Config
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# R2 Configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "f5f1d9e1d40f4f7a73138489c9ed208d")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID", "d13929c785570bbf5cb9e04007b6fddc")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "pomandi-media")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-1de25a6a3db9483aa103360222346a62.r2.dev")

# Database connection
DATABASE_URL = os.getenv(
    "EXPENSE_TRACKER_DATABASE_URL",
    "postgres://postgres:CRwL8EMFSrtno9HMFwikI48y1iCPrs3W9MY6SE7ukLRRteyWt4u5hOfdHFGzlGFb@91.98.235.81:5434/postgres"
)

server = Server("expense-tracker")

# Helper to serialize dates and decimals
def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def to_json(data):
    return json.dumps(data, default=json_serial, indent=2, ensure_ascii=False)

def _parse_quarter(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        cleaned = value.strip().upper()
        if cleaned.startswith("Q"):
            cleaned = cleaned[1:]
        if "-" in cleaned:
            cleaned = cleaned.split("-", 1)[0]
        if cleaned.isdigit():
            quarter = int(cleaned)
            if 1 <= quarter <= 4:
                return quarter
    raise ValueError("Invalid quarter format. Expected 'Q4-2025', 'Q4', or '4'.")

def _parse_date(value, field_name):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    raise ValueError(f"Invalid {field_name}. Expected 'YYYY-MM-DD'.")


# ============================================
# VENDOR TOOLS
# ============================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # Vendor tools
        Tool(
            name="list_vendors",
            description="List all vendors with their transaction counts and match status. Use for getting overview of all vendors alphabetically.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "enum": ["all", "complete", "incomplete"],
                        "description": "Filter by completion status. 'complete' = all transactions matched, 'incomplete' = has unmatched transactions"
                    },
                    "quarter": {
                        "type": "string",
                        "description": "Filter by fiscal quarter (e.g., 'Q4-2025')"
                    }
                }
            }
        ),
        Tool(
            name="get_vendor_details",
            description="Get detailed vendor information including all transactions, invoices, and match status. Use when working on a specific vendor.",
            inputSchema={
                "type": "object",
                "properties": {
                    "vendor_id": {"type": "integer", "description": "Vendor ID"},
                    "vendor_name": {"type": "string", "description": "Vendor name (alternative to ID)"}
                }
            }
        ),
        Tool(
            name="update_vendor_instructions",
            description="Update vendor's collection instructions and notes. Use after learning how to collect invoices from a vendor.",
            inputSchema={
                "type": "object",
                "properties": {
                    "vendor_id": {"type": "integer", "description": "Vendor ID"},
                    "collection_instructions": {"type": "string", "description": "How to collect invoices (e.g., 'Check email from billing@vendor.com')"},
                    "invoice_source": {
                        "type": "string",
                        "enum": ["email", "physical_mail", "portal", "api", "unknown"],
                        "description": "Source of invoices"
                    },
                    "requires_manual_download": {"type": "boolean", "description": "Whether invoices need manual download from portal"},
                    "notes": {"type": "string", "description": "Additional notes about this vendor"}
                },
                "required": ["vendor_id"]
            }
        ),
        Tool(
            name="get_next_vendor",
            description="Get the next incomplete vendor in alphabetical order. Use to continue processing vendors sequentially.",
            inputSchema={
                "type": "object",
                "properties": {
                    "after_vendor": {"type": "string", "description": "Get vendor after this name (for pagination)"}
                }
            }
        ),

        # Transaction tools
        Tool(
            name="list_transactions",
            description="List transactions with optional filters. Returns transaction details with match status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "vendor_id": {"type": "integer", "description": "Filter by vendor ID"},
                    "status": {
                        "type": "string",
                        "enum": ["all", "matched", "pending", "unmatched"],
                        "description": "Filter by invoice status"
                    },
                    "quarter": {"type": "string", "description": "Filter by fiscal quarter (e.g., 'Q4-2025')"},
                    "date_from": {"type": "string", "description": "Filter by execution date from (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "Filter by execution date to (YYYY-MM-DD)"},
                    "limit": {"type": "integer", "description": "Max transactions to return (default: 50)"}
                }
            }
        ),
        Tool(
            name="close_transaction",
            description="Close a transaction without an invoice. Use 'pending_review' for transactions to check later. IMPORTANT: 'no_invoice_expected' and 'invoice_lost' require explicit human approval - do not use without user confirmation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "integer", "description": "Transaction ID"},
                    "reason": {
                        "type": "string",
                        "enum": ["pending_review", "no_invoice_expected", "invoice_lost", "internal_transfer", "bank_fee", "other"],
                        "description": "Reason for closing. Use 'pending_review' for later review. 'no_invoice_expected'/'invoice_lost' require human approval."
                    },
                    "notes": {"type": "string", "description": "Additional notes"},
                    "human_approved": {"type": "boolean", "description": "Required for 'no_invoice_expected' and 'invoice_lost' reasons. Set true only if user explicitly approved."}
                },
                "required": ["transaction_id", "reason"]
            }
        ),

        # Invoice tools
        Tool(
            name="list_invoices",
            description="List invoices with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "vendor_id": {"type": "integer", "description": "Filter by vendor ID"},
                    "status": {
                        "type": "string",
                        "enum": ["all", "pending", "matched", "unmatched"],
                        "description": "Filter by status"
                    },
                    "extraction_status": {
                        "type": "string",
                        "enum": ["all", "pending", "completed", "failed"],
                        "description": "Filter by extraction status"
                    },
                    "date_from": {"type": "string", "description": "Filter by invoice date from (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "Filter by invoice date to (YYYY-MM-DD)"},
                    "limit": {"type": "integer", "description": "Max invoices to return (default: 50)"}
                }
            }
        ),
        Tool(
            name="extract_invoice",
            description="Update invoice with extracted data from image/PDF. Use after reading an invoice file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "integer", "description": "Invoice ID"},
                    "invoice_number": {"type": "string", "description": "Invoice number from document"},
                    "invoice_date": {"type": "string", "description": "Invoice date (YYYY-MM-DD)"},
                    "total_amount": {"type": "number", "description": "Total amount"},
                    "vat_amount": {"type": "number", "description": "VAT amount (if visible)"},
                    "currency": {"type": "string", "description": "Currency (default: EUR)"},
                    "vendor_name": {"type": "string", "description": "Vendor name as shown on invoice"},
                    "vendor_id": {"type": "integer", "description": "Vendor ID to link to"},
                    "description": {"type": "string", "description": "Invoice description/notes"}
                },
                "required": ["invoice_id", "total_amount"]
            }
        ),
        Tool(
            name="match_invoice_transaction",
            description="Create a match between an invoice and a transaction. Use after extracting invoice data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "integer", "description": "Invoice ID"},
                    "transaction_id": {"type": "integer", "description": "Transaction ID"},
                    "match_type": {
                        "type": "string",
                        "enum": ["exact", "manual", "partial", "estimated"],
                        "description": "Type of match"
                    },
                    "notes": {"type": "string", "description": "Notes about the match"}
                },
                "required": ["invoice_id", "transaction_id"]
            }
        ),
        Tool(
            name="get_invoice_file_url",
            description="Get the file URL for an invoice to download/view it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "integer", "description": "Invoice ID"}
                },
                "required": ["invoice_id"]
            }
        ),
        Tool(
            name="update_invoice",
            description="Update invoice fields (vendor_id, status, etc.). Use to reassign invoice to different vendor or remove vendor assignment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "integer", "description": "Invoice ID"},
                    "vendor_id": {"type": ["integer", "null"], "description": "New vendor ID, or null to remove vendor assignment"},
                    "status": {"type": "string", "enum": ["pending", "matched", "unmatched", "duplicate", "rejected"], "description": "New status"},
                    "notes": {"type": "string", "description": "Notes to add"}
                },
                "required": ["invoice_id"]
            }
        ),

        # Progress & reporting tools
        Tool(
            name="get_accounting_progress",
            description="Get overall accounting progress for a quarter. Shows completion percentage, vendors done, transactions matched.",
            inputSchema={
                "type": "object",
                "properties": {
                    "quarter": {"type": "string", "description": "Fiscal quarter (e.g., 'Q4-2025'). Default: current quarter"}
                }
            }
        ),
        Tool(
            name="get_summary_report",
            description="Generate a summary report for accounting. Shows all vendors with their status, useful for accountant handoff.",
            inputSchema={
                "type": "object",
                "properties": {
                    "quarter": {"type": "string", "description": "Fiscal quarter"},
                    "include_details": {"type": "boolean", "description": "Include transaction-level details"}
                }
            }
        ),

        # Utility tools
        Tool(
            name="search_transactions",
            description="Search transactions by counterparty name, amount, or description.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "amount": {"type": "number", "description": "Search by amount (with 1% tolerance)"},
                    "date_from": {"type": "string", "description": "Date range start (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "Date range end (YYYY-MM-DD)"}
                }
            }
        ),
        Tool(
            name="find_matching_transaction",
            description="Find a transaction that matches an invoice amount and date. Use for auto-matching.",
            inputSchema={
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Invoice amount"},
                    "date": {"type": "string", "description": "Expected payment date (YYYY-MM-DD)"},
                    "vendor_id": {"type": "integer", "description": "Vendor ID to filter by"},
                    "tolerance_days": {"type": "integer", "description": "Date tolerance in days (default: 7)"}
                },
                "required": ["amount"]
            }
        ),
        Tool(
            name="search_invoices",
            description="Search invoices by invoice number, amount, or filename. Use for finding specific invoices quickly without loading full list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_number": {"type": "string", "description": "Search by invoice number (partial match)"},
                    "amount": {"type": "number", "description": "Search by amount (with 2% tolerance)"},
                    "file_name": {"type": "string", "description": "Search in file name (partial match)"},
                    "query": {"type": "string", "description": "General search in invoice_number, file_name, vendor_name"},
                    "limit": {"type": "integer", "description": "Max results (default: 10)"}
                }
            }
        ),
        Tool(
            name="upload_invoice",
            description="Upload an invoice file from local path to R2 storage and create invoice record. Use for invoices downloaded from email or other sources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Local file path to upload (e.g., /tmp/invoice.pdf)"},
                    "vendor_id": {"type": "integer", "description": "Vendor ID to associate with"},
                    "vendor_name": {"type": "string", "description": "Vendor name (alternative to ID, will lookup)"},
                    "file_name": {"type": "string", "description": "Optional: override filename for storage"}
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="bulk_close_matched",
            description="Close all matched transactions that don't have closure_reason set. Use to fix transactions that were matched but not properly closed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "If true, only show what would be closed without actually closing"}
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await _handle_tool(conn, name, arguments)
        return [TextContent(type="text", text=to_json(result))]
    finally:
        await conn.close()


async def _handle_tool(conn: asyncpg.Connection, name: str, args: dict) -> dict:
    """Route tool calls to handlers"""

    # Vendor tools
    if name == "list_vendors":
        return await _list_vendors(conn, args)
    elif name == "get_vendor_details":
        return await _get_vendor_details(conn, args)
    elif name == "update_vendor_instructions":
        return await _update_vendor_instructions(conn, args)
    elif name == "get_next_vendor":
        return await _get_next_vendor(conn, args)

    # Transaction tools
    elif name == "list_transactions":
        return await _list_transactions(conn, args)
    elif name == "close_transaction":
        return await _close_transaction(conn, args)
    elif name == "search_transactions":
        return await _search_transactions(conn, args)
    elif name == "find_matching_transaction":
        return await _find_matching_transaction(conn, args)
    elif name == "search_invoices":
        return await _search_invoices(conn, args)

    # Invoice tools
    elif name == "list_invoices":
        return await _list_invoices(conn, args)
    elif name == "extract_invoice":
        return await _extract_invoice(conn, args)
    elif name == "match_invoice_transaction":
        return await _match_invoice_transaction(conn, args)
    elif name == "get_invoice_file_url":
        return await _get_invoice_file_url(conn, args)
    elif name == "update_invoice":
        return await _update_invoice(conn, args)
    elif name == "upload_invoice":
        return await _upload_invoice(conn, args)
    elif name == "bulk_close_matched":
        return await _bulk_close_matched(conn, args)

    # Progress tools
    elif name == "get_accounting_progress":
        return await _get_accounting_progress(conn, args)
    elif name == "get_summary_report":
        return await _get_summary_report(conn, args)

    else:
        return {"error": f"Unknown tool: {name}"}


# ============================================
# VENDOR HANDLERS
# ============================================

async def _list_vendors(conn: asyncpg.Connection, args: dict) -> dict:
    """List all vendors with transaction counts and match status"""

    params = []
    join_condition = "t.vendor_id = v.id"
    if 'quarter' in args:
        try:
            quarter = _parse_quarter(args['quarter'])
        except ValueError as exc:
            return {"error": str(exc)}
        join_condition += " AND t.fiscal_quarter = $1"
        params.append(quarter)

    query = f"""
        SELECT
            v.id,
            v.name,
            v.invoice_source,
            v.requires_manual_download,
            COUNT(t.id) as transaction_count,
            COUNT(CASE WHEN t.invoice_status = 'matched' THEN 1 END) as matched_count,
            COUNT(CASE WHEN t.invoice_status != 'matched' AND t.invoice_status != 'closed' THEN 1 END) as pending_count,
            COALESCE(SUM(ABS(t.amount)), 0) as total_amount
        FROM vendors v
        LEFT JOIN transactions t ON {join_condition}
        GROUP BY v.id, v.name, v.invoice_source, v.requires_manual_download
        ORDER BY v.name
    """

    rows = await conn.fetch(query, *params)

    vendors = []
    for row in rows:
        status = "complete" if row['pending_count'] == 0 and row['transaction_count'] > 0 else "incomplete"
        if row['transaction_count'] == 0:
            status = "no_transactions"

        vendors.append({
            "id": row['id'],
            "name": row['name'],
            "invoice_source": row['invoice_source'],
            "requires_manual_download": row['requires_manual_download'],
            "transaction_count": row['transaction_count'],
            "matched_count": row['matched_count'],
            "pending_count": row['pending_count'],
            "total_amount": row['total_amount'],
            "status": status,
            "progress": f"{row['matched_count']}/{row['transaction_count']}"
        })

    # Apply filters
    status_filter = args.get('status_filter', 'all')
    if status_filter == 'complete':
        vendors = [v for v in vendors if v['status'] == 'complete']
    elif status_filter == 'incomplete':
        vendors = [v for v in vendors if v['status'] == 'incomplete']

    complete_count = len([v for v in vendors if v['status'] == 'complete'])
    incomplete_count = len([v for v in vendors if v['status'] == 'incomplete'])

    return {
        "total": len(vendors),
        "complete": complete_count,
        "incomplete": incomplete_count,
        "vendors": vendors
    }


async def _get_vendor_details(conn: asyncpg.Connection, args: dict) -> dict:
    """Get detailed vendor info with transactions and invoices"""

    vendor_id = args.get('vendor_id')
    vendor_name = args.get('vendor_name')

    if vendor_name and not vendor_id:
        row = await conn.fetchrow("SELECT id FROM vendors WHERE LOWER(name) = LOWER($1)", vendor_name)
        if row:
            vendor_id = row['id']
        else:
            return {"error": f"Vendor not found: {vendor_name}"}

    if not vendor_id:
        return {"error": "Either vendor_id or vendor_name required"}

    # Get vendor info
    vendor = await conn.fetchrow("""
        SELECT id, name, collection_instructions, invoice_source,
               requires_manual_download, notes
        FROM vendors WHERE id = $1
    """, vendor_id)

    if not vendor:
        return {"error": f"Vendor not found: {vendor_id}"}

    # Get transactions
    transactions = await conn.fetch("""
        SELECT id, execution_date, amount, counterparty_name, communication,
               invoice_status, fiscal_quarter, closed_at, closure_reason
        FROM transactions
        WHERE vendor_id = $1
        ORDER BY execution_date DESC
    """, vendor_id)

    # Get invoices
    invoices = await conn.fetch("""
        SELECT id, file_name, invoice_number, invoice_date, total_amount,
               status, extraction_status, detected_vendor_name
        FROM invoices
        WHERE vendor_id = $1
        ORDER BY invoice_date DESC NULLS LAST
    """, vendor_id)

    # Get matches
    matches = await conn.fetch("""
        SELECT m.id, m.transaction_id, m.invoice_id, m.match_type, m.matched_at
        FROM transaction_invoice_matches m
        JOIN transactions t ON t.id = m.transaction_id
        WHERE t.vendor_id = $1
    """, vendor_id)

    matched_count = len([t for t in transactions if t['invoice_status'] == 'matched'])
    pending_count = len([t for t in transactions if t['invoice_status'] not in ('matched', 'closed')])

    return {
        "vendor": dict(vendor),
        "summary": {
            "transaction_count": len(transactions),
            "matched_count": matched_count,
            "pending_count": pending_count,
            "invoice_count": len(invoices),
            "status": "complete" if pending_count == 0 else "incomplete"
        },
        "transactions": [dict(t) for t in transactions],
        "invoices": [dict(i) for i in invoices],
        "matches": [dict(m) for m in matches]
    }


async def _update_vendor_instructions(conn: asyncpg.Connection, args: dict) -> dict:
    """Update vendor collection instructions"""

    vendor_id = args['vendor_id']

    updates = []
    params = [vendor_id]
    param_idx = 2

    if 'collection_instructions' in args:
        updates.append(f"collection_instructions = ${param_idx}")
        params.append(args['collection_instructions'])
        param_idx += 1

    if 'invoice_source' in args:
        updates.append(f"invoice_source = ${param_idx}")
        params.append(args['invoice_source'])
        param_idx += 1

    if 'requires_manual_download' in args:
        updates.append(f"requires_manual_download = ${param_idx}")
        params.append(args['requires_manual_download'])
        param_idx += 1

    if 'notes' in args:
        updates.append(f"notes = ${param_idx}")
        params.append(args['notes'])
        param_idx += 1

    if not updates:
        return {"error": "No fields to update"}

    updates.append("updated_at = NOW()")

    query = f"UPDATE vendors SET {', '.join(updates)} WHERE id = $1 RETURNING id, name"
    result = await conn.fetchrow(query, *params)

    return {"success": True, "vendor": dict(result)}


async def _get_next_vendor(conn: asyncpg.Connection, args: dict) -> dict:
    """Get next incomplete vendor alphabetically"""

    after_vendor = args.get('after_vendor', '')

    query = """
        SELECT
            v.id, v.name,
            COUNT(t.id) as transaction_count,
            COUNT(CASE WHEN t.invoice_status = 'matched' THEN 1 END) as matched_count,
            COUNT(CASE WHEN t.invoice_status NOT IN ('matched', 'closed') THEN 1 END) as pending_count
        FROM vendors v
        LEFT JOIN transactions t ON t.vendor_id = v.id
        WHERE LOWER(v.name) > LOWER($1)
        GROUP BY v.id, v.name
        HAVING COUNT(CASE WHEN t.invoice_status NOT IN ('matched', 'closed') THEN 1 END) > 0
        ORDER BY v.name
        LIMIT 1
    """

    row = await conn.fetchrow(query, after_vendor)

    if not row:
        return {"message": "No more incomplete vendors!", "complete": True}

    return {
        "vendor_id": row['id'],
        "vendor_name": row['name'],
        "transaction_count": row['transaction_count'],
        "matched_count": row['matched_count'],
        "pending_count": row['pending_count'],
        "progress": f"{row['matched_count']}/{row['transaction_count']}"
    }


# ============================================
# TRANSACTION HANDLERS
# ============================================

async def _list_transactions(conn: asyncpg.Connection, args: dict) -> dict:
    """List transactions with filters"""

    conditions = []
    params = []
    param_idx = 1

    if 'vendor_id' in args:
        conditions.append(f"t.vendor_id = ${param_idx}")
        params.append(args['vendor_id'])
        param_idx += 1

    status = args.get('status', 'all')
    if status == 'matched':
        conditions.append("t.invoice_status = 'matched'")
    elif status == 'pending':
        conditions.append("t.invoice_status = 'pending'")
    elif status == 'unmatched':
        conditions.append("t.invoice_status NOT IN ('matched', 'closed')")

    if 'quarter' in args:
        try:
            quarter = _parse_quarter(args['quarter'])
        except ValueError as exc:
            return {"error": str(exc)}
        conditions.append(f"t.fiscal_quarter = ${param_idx}")
        params.append(quarter)
        param_idx += 1

    if 'date_from' in args:
        try:
            date_from = _parse_date(args['date_from'], "date_from")
        except ValueError as exc:
            return {"error": str(exc)}
        conditions.append(f"t.execution_date >= ${param_idx}")
        params.append(date_from)
        param_idx += 1

    if 'date_to' in args:
        try:
            date_to = _parse_date(args['date_to'], "date_to")
        except ValueError as exc:
            return {"error": str(exc)}
        conditions.append(f"t.execution_date <= ${param_idx}")
        params.append(date_to)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit = args.get('limit', 50)

    query = f"""
        SELECT t.id, t.execution_date, t.amount, t.counterparty_name,
               t.communication, t.invoice_status, t.fiscal_quarter,
               v.name as vendor_name
        FROM transactions t
        LEFT JOIN vendors v ON v.id = t.vendor_id
        {where_clause}
        ORDER BY t.execution_date DESC
        LIMIT {limit}
    """

    rows = await conn.fetch(query, *params)

    return {
        "count": len(rows),
        "transactions": [dict(r) for r in rows]
    }


async def _close_transaction(conn: asyncpg.Connection, args: dict) -> dict:
    """Close a transaction without invoice"""

    tx_id = args['transaction_id']
    reason = args['reason']
    notes = args.get('notes', '')
    human_approved = args.get('human_approved', False)

    # Require human approval for permanent closure reasons
    protected_reasons = ['no_invoice_expected', 'invoice_lost']
    if reason in protected_reasons and not human_approved:
        return {
            "error": f"Human approval required for '{reason}' closure",
            "message": f"The reason '{reason}' requires explicit user confirmation. Use 'pending_review' instead, or set human_approved=true if user explicitly approved.",
            "suggestion": "Use reason='pending_review' to mark for later review without losing the transaction"
        }

    await conn.execute("""
        UPDATE transactions SET
            invoice_status = 'closed',
            closed_at = NOW(),
            closure_reason = $2,
            notes = COALESCE(notes || E'\n', '') || $3
        WHERE id = $1
    """, tx_id, reason, notes)

    return {"success": True, "transaction_id": tx_id, "status": "closed", "reason": reason}


async def _search_transactions(conn: asyncpg.Connection, args: dict) -> dict:
    """Search transactions"""

    conditions = []
    params = []
    param_idx = 1

    if 'query' in args:
        conditions.append(f"""
            (LOWER(counterparty_name) LIKE LOWER(${param_idx})
             OR LOWER(communication) LIKE LOWER(${param_idx}))
        """)
        params.append(f"%{args['query']}%")
        param_idx += 1

    if 'amount' in args:
        amt = args['amount']
        tolerance = amt * 0.01  # 1% tolerance
        conditions.append(f"ABS(ABS(amount) - ${param_idx}) < ${param_idx + 1}")
        params.extend([amt, tolerance])
        param_idx += 2

    if 'date_from' in args:
        conditions.append(f"execution_date >= ${param_idx}")
        # Convert date string to date object
        date_from_str = args['date_from']
        if isinstance(date_from_str, str):
            date_from_obj = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            params.append(date_from_obj)
        else:
            params.append(date_from_str)
        param_idx += 1

    if 'date_to' in args:
        conditions.append(f"execution_date <= ${param_idx}")
        # Convert date string to date object
        date_to_str = args['date_to']
        if isinstance(date_to_str, str):
            date_to_obj = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            params.append(date_to_obj)
        else:
            params.append(date_to_str)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT t.id, t.execution_date, t.amount, t.counterparty_name,
               t.invoice_status, v.name as vendor_name
        FROM transactions t
        LEFT JOIN vendors v ON v.id = t.vendor_id
        {where_clause}
        ORDER BY t.execution_date DESC
        LIMIT 20
    """

    rows = await conn.fetch(query, *params)
    return {"count": len(rows), "transactions": [dict(r) for r in rows]}


async def _find_matching_transaction(conn: asyncpg.Connection, args: dict) -> dict:
    """Find transaction matching invoice amount/date"""

    amount = args['amount']
    tolerance = amount * 0.01  # 1% tolerance

    conditions = [
        "ABS(ABS(t.amount) - $1) < $2",
        "t.invoice_status NOT IN ('matched', 'closed')"
    ]
    params = [amount, tolerance]
    param_idx = 3

    if 'vendor_id' in args:
        conditions.append(f"t.vendor_id = ${param_idx}")
        params.append(args['vendor_id'])
        param_idx += 1

    if 'date' in args:
        tolerance_days = args.get('tolerance_days', 7)
        conditions.append(f"ABS(t.execution_date - ${param_idx}) <= {tolerance_days}")
        # Convert date string to date object
        date_str = args['date']
        if isinstance(date_str, str):
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            params.append(date_obj)
        else:
            params.append(date_str)
        param_idx += 1

    query = f"""
        SELECT t.id, t.execution_date, t.amount, t.counterparty_name,
               t.invoice_status, v.name as vendor_name
        FROM transactions t
        LEFT JOIN vendors v ON v.id = t.vendor_id
        WHERE {' AND '.join(conditions)}
        ORDER BY ABS(ABS(t.amount) - $1)
        LIMIT 5
    """

    rows = await conn.fetch(query, *params)

    if not rows:
        return {"found": False, "message": "No matching transactions found"}

    return {
        "found": True,
        "best_match": dict(rows[0]),
        "other_candidates": [dict(r) for r in rows[1:]]
    }


async def _search_invoices(conn: asyncpg.Connection, args: dict) -> dict:
    """Search invoices by invoice_number, amount, file_name, or general query"""

    conditions = []
    params = []
    param_idx = 1

    if 'invoice_number' in args:
        conditions.append(f"LOWER(invoice_number) LIKE LOWER(${param_idx})")
        params.append(f"%{args['invoice_number']}%")
        param_idx += 1

    if 'amount' in args:
        amt = args['amount']
        tolerance = amt * 0.02  # 2% tolerance
        conditions.append(f"ABS(total_amount - ${param_idx}) < ${param_idx + 1}")
        params.extend([amt, tolerance])
        param_idx += 2

    if 'file_name' in args:
        conditions.append(f"LOWER(file_name) LIKE LOWER(${param_idx})")
        params.append(f"%{args['file_name']}%")
        param_idx += 1

    if 'query' in args:
        conditions.append(f"""
            (LOWER(COALESCE(invoice_number, '')) LIKE LOWER(${param_idx})
             OR LOWER(COALESCE(file_name, '')) LIKE LOWER(${param_idx})
             OR LOWER(COALESCE(detected_vendor_name, '')) LIKE LOWER(${param_idx}))
        """)
        params.append(f"%{args['query']}%")
        param_idx += 1

    if not conditions:
        return {"error": "At least one search parameter required: invoice_number, amount, file_name, or query"}

    where_clause = f"WHERE {' AND '.join(conditions)}"
    limit = args.get('limit', 10)

    query = f"""
        SELECT id, file_name, invoice_number, invoice_date, total_amount,
               status, extraction_status, detected_vendor_name, vendor_id, file_path
        FROM invoices
        {where_clause}
        ORDER BY invoice_date DESC NULLS LAST
        LIMIT {limit}
    """

    rows = await conn.fetch(query, *params)
    return {"count": len(rows), "invoices": [dict(r) for r in rows]}


# ============================================
# INVOICE HANDLERS
# ============================================

async def _list_invoices(conn: asyncpg.Connection, args: dict) -> dict:
    """List invoices with filters"""

    conditions = []
    params = []
    param_idx = 1

    if 'vendor_id' in args:
        conditions.append(f"vendor_id = ${param_idx}")
        params.append(args['vendor_id'])
        param_idx += 1

    status = args.get('status', 'all')
    if status != 'all':
        conditions.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1

    extraction = args.get('extraction_status', 'all')
    if extraction != 'all':
        conditions.append(f"extraction_status = ${param_idx}")
        params.append(extraction)
        param_idx += 1

    if 'date_from' in args:
        try:
            date_from = _parse_date(args['date_from'], "date_from")
        except ValueError as exc:
            return {"error": str(exc)}
        conditions.append(f"invoice_date >= ${param_idx}")
        params.append(date_from)
        param_idx += 1

    if 'date_to' in args:
        try:
            date_to = _parse_date(args['date_to'], "date_to")
        except ValueError as exc:
            return {"error": str(exc)}
        conditions.append(f"invoice_date <= ${param_idx}")
        params.append(date_to)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit = args.get('limit', 50)

    query = f"""
        SELECT id, file_name, file_path, invoice_number, invoice_date,
               total_amount, status, extraction_status, detected_vendor_name,
               vendor_id
        FROM invoices
        {where_clause}
        ORDER BY created_at DESC
        LIMIT {limit}
    """

    rows = await conn.fetch(query, *params)
    return {"count": len(rows), "invoices": [dict(r) for r in rows]}


async def _extract_invoice(conn: asyncpg.Connection, args: dict) -> dict:
    """Update invoice with extracted data"""

    invoice_id = args['invoice_id']

    updates = ["extraction_status = 'completed'", "extracted_at = NOW()"]
    params = [invoice_id]
    param_idx = 2

    fields = ['invoice_number', 'total_amount', 'vat_amount',
              'currency', 'description']

    for field in fields:
        if field in args:
            updates.append(f"{field} = ${param_idx}")
            params.append(args[field])
            param_idx += 1

    # Handle invoice_date separately - convert string to date
    if 'invoice_date' in args:
        updates.append(f"invoice_date = ${param_idx}")
        date_str = args['invoice_date']
        if isinstance(date_str, str):
            # Parse YYYY-MM-DD string to date object
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            params.append(date_obj)
        else:
            params.append(date_str)
        param_idx += 1

    if 'vendor_name' in args:
        updates.append(f"detected_vendor_name = ${param_idx}")
        params.append(args['vendor_name'])
        param_idx += 1

    if 'vendor_id' in args:
        updates.append(f"vendor_id = ${param_idx}")
        params.append(args['vendor_id'])
        param_idx += 1

    query = f"""
        UPDATE invoices SET {', '.join(updates)}
        WHERE id = $1
        RETURNING id, invoice_number, total_amount, extraction_status
    """

    result = await conn.fetchrow(query, *params)
    return {"success": True, "invoice": dict(result)}


async def _match_invoice_transaction(conn: asyncpg.Connection, args: dict) -> dict:
    """Create match between invoice and transaction, and close the transaction"""

    invoice_id = args['invoice_id']
    transaction_id = args['transaction_id']
    match_type = args.get('match_type', 'manual')
    notes = args.get('notes', '')

    # Create match
    await conn.execute("""
        INSERT INTO transaction_invoice_matches
            (transaction_id, invoice_id, match_type, confidence_score, matched_by, matched_at)
        VALUES ($1, $2, $3, 1.00, 'mcp', NOW())
    """, transaction_id, invoice_id, match_type)

    # Update statuses AND close the transaction with invoice
    await conn.execute("""
        UPDATE transactions
        SET invoice_status = 'matched',
            closed_at = NOW(),
            closure_reason = 'with_invoice'
        WHERE id = $1
    """, transaction_id)
    await conn.execute("UPDATE invoices SET status = 'matched' WHERE id = $1", invoice_id)

    return {
        "success": True,
        "match": {
            "invoice_id": invoice_id,
            "transaction_id": transaction_id,
            "match_type": match_type
        }
    }


async def _get_invoice_file_url(conn: asyncpg.Connection, args: dict) -> dict:
    """Get invoice file URL"""

    invoice_id = args['invoice_id']

    row = await conn.fetchrow("""
        SELECT id, file_name, file_path
        FROM invoices WHERE id = $1
    """, invoice_id)

    if not row:
        return {"error": f"Invoice not found: {invoice_id}"}

    # Construct URL from file_path (R2 bucket)
    file_url = None
    if row['file_path']:
        # file_path is already a full URL like https://pub-....r2.dev/invoices/...
        if row['file_path'].startswith('http'):
            file_url = row['file_path']
        else:
            file_url = f"https://pub-1de25a6a3db9483aa103360222346a62.r2.dev/{row['file_path']}"

    return {
        "invoice_id": row['id'],
        "file_name": row['file_name'],
        "file_path": row['file_path'],
        "file_url": file_url
    }


async def _update_invoice(conn: asyncpg.Connection, args: dict) -> dict:
    """Update invoice fields (vendor_id, status, notes)"""

    invoice_id = args['invoice_id']

    # Check invoice exists
    existing = await conn.fetchrow("SELECT id, vendor_id, status FROM invoices WHERE id = $1", invoice_id)
    if not existing:
        return {"error": f"Invoice not found: {invoice_id}"}

    updates = []
    params = [invoice_id]
    param_idx = 2

    # Handle vendor_id (can be null to remove assignment)
    if 'vendor_id' in args:
        vendor_id = args['vendor_id']
        if vendor_id is None:
            updates.append("vendor_id = NULL")
        else:
            updates.append(f"vendor_id = ${param_idx}")
            params.append(vendor_id)
            param_idx += 1

    if 'status' in args:
        updates.append(f"status = ${param_idx}")
        params.append(args['status'])
        param_idx += 1

    if 'notes' in args:
        updates.append(f"notes = ${param_idx}")
        params.append(args['notes'])
        param_idx += 1

    if not updates:
        return {"error": "No fields to update"}

    updates.append("updated_at = NOW()")

    query = f"""
        UPDATE invoices
        SET {', '.join(updates)}
        WHERE id = $1
        RETURNING id, vendor_id, status, file_name
    """

    result = await conn.fetchrow(query, *params)
    return {
        "success": True,
        "invoice": dict(result),
        "message": f"Invoice {invoice_id} updated"
    }


async def _upload_invoice(conn: asyncpg.Connection, args: dict) -> dict:
    """Upload invoice file from local path to R2 and create invoice record"""

    file_path = args['file_path']
    vendor_id = args.get('vendor_id')
    vendor_name = args.get('vendor_name')

    # Lookup vendor by name if needed
    if vendor_name and not vendor_id:
        row = await conn.fetchrow("SELECT id FROM vendors WHERE LOWER(name) LIKE LOWER($1)", f"%{vendor_name}%")
        if row:
            vendor_id = row['id']

    # Read local file
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    with open(file_path, "rb") as f:
        file_content = f.read()

    # Determine filename
    original_filename = args.get('file_name') or os.path.basename(file_path)

    # Generate unique filename with UUID
    file_ext = os.path.splitext(original_filename)[1] or '.pdf'
    unique_id = uuid.uuid4().hex[:8]
    safe_filename = original_filename.replace(' ', '_').replace('(', '').replace(')', '')
    base_name = os.path.splitext(safe_filename)[0]
    storage_filename = f"{base_name}_{unique_id}{file_ext}"

    # Determine vendor folder
    vendor_folder = "unknown"
    if vendor_id:
        vendor_row = await conn.fetchrow("SELECT name FROM vendors WHERE id = $1", vendor_id)
        if vendor_row:
            vendor_folder = vendor_row['name'].lower().replace(' ', '-').replace('/', '-')[:30]

    # Upload to R2
    date_prefix = datetime.now().strftime("%Y/%m")
    r2_path = f"invoices/{date_prefix}/{vendor_folder}/{storage_filename}"

    try:
        if R2_SECRET_KEY:
            s3 = boto3.client(
                "s3",
                endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=R2_ACCESS_KEY,
                aws_secret_access_key=R2_SECRET_KEY,
                config=Config(signature_version="s3v4")
            )

            # Determine content type
            content_type = "application/pdf" if file_ext.lower() == ".pdf" else "image/jpeg"

            s3.put_object(
                Bucket=R2_BUCKET,
                Key=r2_path,
                Body=file_content,
                ContentType=content_type
            )

            file_url = f"{R2_PUBLIC_URL}/{r2_path}"
        else:
            # No R2 credentials, save locally and use local path
            local_storage = f"/tmp/invoices/{date_prefix}/{vendor_folder}"
            os.makedirs(local_storage, exist_ok=True)
            local_file = f"{local_storage}/{storage_filename}"
            with open(local_file, "wb") as f:
                f.write(file_content)
            file_url = local_file
    except Exception as e:
        return {"error": f"Upload failed: {str(e)}"}

    # Create invoice record in database
    invoice = await conn.fetchrow("""
        INSERT INTO invoices (file_name, file_path, vendor_id, status, extraction_status, created_at, invoice_date)
        VALUES ($1, $2, $3, 'pending', 'pending', NOW(), CURRENT_DATE)
        RETURNING id, file_name, file_path, vendor_id, status, extraction_status
    """, original_filename, file_url, vendor_id)

    return {
        "success": True,
        "invoice_id": invoice['id'],
        "file_name": invoice['file_name'],
        "file_url": file_url,
        "vendor_id": vendor_id,
        "message": f"Invoice uploaded successfully. Use extract_invoice with invoice_id={invoice['id']} to extract data."
    }


# ============================================
# PROGRESS HANDLERS
# ============================================

async def _get_accounting_progress(conn: asyncpg.Connection, args: dict) -> dict:
    """Get overall accounting progress"""

    quarter = args.get('quarter', 'Q4-2025')
    try:
        quarter = _parse_quarter(quarter)
    except ValueError as exc:
        return {"error": str(exc)}

    # Overall transaction stats
    tx_stats = await conn.fetchrow("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN invoice_status = 'matched' THEN 1 END) as matched,
            COUNT(CASE WHEN invoice_status = 'closed' THEN 1 END) as closed,
            COUNT(CASE WHEN invoice_status NOT IN ('matched', 'closed') THEN 1 END) as pending,
            COALESCE(SUM(ABS(amount)), 0) as total_amount,
            COALESCE(SUM(CASE WHEN invoice_status = 'matched' THEN ABS(amount) END), 0) as matched_amount
        FROM transactions
        WHERE fiscal_quarter = $1
    """, quarter)

    # Vendor stats
    vendor_stats = await conn.fetchrow("""
        SELECT
            COUNT(DISTINCT v.id) as total_vendors,
            COUNT(DISTINCT CASE WHEN NOT EXISTS (
                SELECT 1 FROM transactions t
                WHERE t.vendor_id = v.id
                AND t.invoice_status NOT IN ('matched', 'closed')
                AND t.fiscal_quarter = $1
            ) THEN v.id END) as complete_vendors
        FROM vendors v
        WHERE EXISTS (SELECT 1 FROM transactions t WHERE t.vendor_id = v.id AND t.fiscal_quarter = $1)
    """, quarter)

    # Invoice stats
    inv_stats = await conn.fetchrow("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'matched' THEN 1 END) as matched,
            COUNT(CASE WHEN extraction_status = 'pending' THEN 1 END) as pending_extraction
        FROM invoices
    """)

    total = tx_stats['total'] or 1
    matched = tx_stats['matched'] or 0

    return {
        "quarter": quarter,
        "progress_percent": round((matched / total) * 100, 1),
        "transactions": {
            "total": tx_stats['total'],
            "matched": tx_stats['matched'],
            "closed": tx_stats['closed'],
            "pending": tx_stats['pending'],
            "total_amount": tx_stats['total_amount'],
            "matched_amount": tx_stats['matched_amount']
        },
        "vendors": {
            "total": vendor_stats['total_vendors'],
            "complete": vendor_stats['complete_vendors'],
            "incomplete": vendor_stats['total_vendors'] - vendor_stats['complete_vendors']
        },
        "invoices": {
            "total": inv_stats['total'],
            "matched": inv_stats['matched'],
            "pending_extraction": inv_stats['pending_extraction']
        }
    }


async def _get_summary_report(conn: asyncpg.Connection, args: dict) -> dict:
    """Generate summary report for accountant"""

    quarter = args.get('quarter', 'Q4-2025')
    try:
        quarter = _parse_quarter(quarter)
    except ValueError as exc:
        return {"error": str(exc)}
    include_details = args.get('include_details', False)

    # Get all vendors with their status
    vendors = await conn.fetch("""
        SELECT
            v.id, v.name, v.invoice_source, v.collection_instructions,
            COUNT(t.id) as tx_count,
            COUNT(CASE WHEN t.invoice_status = 'matched' THEN 1 END) as matched,
            COUNT(CASE WHEN t.invoice_status = 'closed' THEN 1 END) as closed,
            COUNT(CASE WHEN t.invoice_status NOT IN ('matched', 'closed') THEN 1 END) as pending,
            COALESCE(SUM(ABS(t.amount)), 0) as total_amount
        FROM vendors v
        LEFT JOIN transactions t ON t.vendor_id = v.id AND t.fiscal_quarter = $1
        GROUP BY v.id, v.name, v.invoice_source, v.collection_instructions
        HAVING COUNT(t.id) > 0
        ORDER BY v.name
    """, quarter)

    report = {
        "quarter": quarter,
        "generated_at": datetime.now().isoformat(),
        "vendors": []
    }

    for v in vendors:
        vendor_data = {
            "name": v['name'],
            "status": "complete" if v['pending'] == 0 else "incomplete",
            "progress": f"{v['matched']}/{v['tx_count']}",
            "total_amount": v['total_amount'],
            "invoice_source": v['invoice_source']
        }

        if include_details and v['pending'] > 0:
            # Get pending transactions
            pending_tx = await conn.fetch("""
                SELECT execution_date, amount, counterparty_name
                FROM transactions
                WHERE vendor_id = $1 AND invoice_status NOT IN ('matched', 'closed')
                ORDER BY execution_date DESC
            """, v['id'])
            vendor_data['pending_transactions'] = [dict(t) for t in pending_tx]

        report['vendors'].append(vendor_data)

    complete = len([v for v in report['vendors'] if v['status'] == 'complete'])
    report['summary'] = {
        "total_vendors": len(report['vendors']),
        "complete_vendors": complete,
        "incomplete_vendors": len(report['vendors']) - complete
    }

    return report


async def _bulk_close_matched(conn: asyncpg.Connection, args: dict) -> dict:
    """Close all matched transactions that don't have closure_reason set"""

    dry_run = args.get('dry_run', False)

    # Find matched transactions without closure
    transactions = await conn.fetch("""
        SELECT t.id, t.amount, t.counterparty_name, t.execution_date, v.name as vendor_name
        FROM transactions t
        LEFT JOIN vendors v ON t.vendor_id = v.id
        WHERE t.invoice_status = 'matched'
        AND (t.closure_reason IS NULL OR t.closed_at IS NULL)
        ORDER BY t.execution_date DESC
    """)

    if dry_run:
        return {
            "dry_run": True,
            "would_close": len(transactions),
            "transactions": [
                {
                    "id": t['id'],
                    "amount": float(t['amount']),
                    "vendor": t['vendor_name'] or t['counterparty_name'],
                    "date": t['execution_date'].isoformat() if t['execution_date'] else None
                }
                for t in transactions
            ]
        }

    # Actually close them
    if transactions:
        await conn.execute("""
            UPDATE transactions
            SET closed_at = NOW(),
                closure_reason = 'with_invoice'
            WHERE invoice_status = 'matched'
            AND (closure_reason IS NULL OR closed_at IS NULL)
        """)

    return {
        "success": True,
        "closed_count": len(transactions),
        "message": f"Closed {len(transactions)} matched transactions"
    }


# ============================================
# MAIN
# ============================================

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
