#!/usr/bin/env python3
"""
Retouche (Pomandi Tailoring System) MCP Server

MCP server for managing credit notes and customer operations in Retouche system.
Operations:
- Find/create customers
- Create credit notes (invoices with document_type='credit_note')
- List invoices and credit notes

Database: PostgreSQL (Retouche production DB on Heroku/Coolify)
"""

import os
import json
import asyncio
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

import asyncpg
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Database connection - Retouche production database
DATABASE_URL = os.getenv(
    "RETOUCHE_DATABASE_URL",
    # Default to local for testing - update with production URL
    "postgres://postgres:123456@localhost:5432/mytailorshop"
)

server = Server("retouche")

# Helper to serialize dates and decimals
def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def to_json(data):
    return json.dumps(data, default=json_serial, indent=2, ensure_ascii=False)


# ============================================
# CUSTOMER TOOLS
# ============================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="find_customer",
            description="Find customer by name in Retouche database. Returns customer ID if found.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Customer name to search for (case-insensitive partial match)"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="create_customer",
            description="Create a new customer in Retouche database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Customer full name"
                    },
                    "email": {
                        "type": "string",
                        "description": "Customer email (optional)"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Customer phone (optional)"
                    },
                    "address": {
                        "type": "string",
                        "description": "Customer address (optional)"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="create_credit_note",
            description="Create a credit note (invoice with document_type='credit_note') in Retouche system.",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "integer",
                        "description": "Customer ID from factuur_customer table"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Customer name"
                    },
                    "invoice_date": {
                        "type": "string",
                        "description": "Invoice date (YYYY-MM-DD)"
                    },
                    "total_amount": {
                        "type": "number",
                        "description": "Total amount including VAT"
                    },
                    "description": {
                        "type": "string",
                        "description": "Credit note description/reason"
                    },
                    "bon_number": {
                        "type": "string",
                        "description": "Original receipt/bon number if available (optional)"
                    },
                    "vat_rate": {
                        "type": "number",
                        "description": "VAT rate percentage (default: 21.00 for Belgium)",
                        "default": 21.00
                    }
                },
                "required": ["customer_name", "invoice_date", "total_amount", "description"]
            }
        ),
        Tool(
            name="list_credit_notes",
            description="List all credit notes from Retouche system.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of records to return (default: 20)"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Filter by customer name (optional)"
                    }
                }
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool execution."""

    try:
        if name == "find_customer":
            result = await find_customer(
                name=arguments["name"]
            )
            return [TextContent(type="text", text=to_json(result))]

        elif name == "create_customer":
            result = await create_customer(
                name=arguments["name"],
                email=arguments.get("email"),
                phone=arguments.get("phone"),
                address=arguments.get("address")
            )
            return [TextContent(type="text", text=to_json(result))]

        elif name == "create_credit_note":
            result = await create_credit_note(
                customer_id=arguments.get("customer_id"),
                customer_name=arguments["customer_name"],
                invoice_date=arguments["invoice_date"],
                total_amount=arguments["total_amount"],
                description=arguments["description"],
                bon_number=arguments.get("bon_number"),
                vat_rate=arguments.get("vat_rate", 21.00)
            )
            return [TextContent(type="text", text=to_json(result))]

        elif name == "list_credit_notes":
            result = await list_credit_notes(
                limit=arguments.get("limit", 20),
                customer_name=arguments.get("customer_name")
            )
            return [TextContent(type="text", text=to_json(result))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        error_msg = f"Error in {name}: {str(e)}"
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]


# ============================================
# DATABASE OPERATIONS
# ============================================

async def get_db_connection():
    """Get database connection."""
    return await asyncpg.connect(DATABASE_URL)


async def find_customer(name: str) -> dict:
    """Find customer by name (case-insensitive partial match)."""
    conn = await get_db_connection()
    try:
        # Search in factuur_customer table
        row = await conn.fetchrow(
            """
            SELECT id, name, email, phone, address, created_at
            FROM factuur_customer
            WHERE LOWER(name) LIKE LOWER($1)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            f"%{name}%"
        )

        if row:
            return {
                "found": True,
                "customer": {
                    "id": row["id"],
                    "name": row["name"],
                    "email": row["email"],
                    "phone": row["phone"],
                    "address": row["address"],
                    "created_at": row["created_at"]
                }
            }
        else:
            return {
                "found": False,
                "message": f"No customer found matching: {name}"
            }
    finally:
        await conn.close()


async def create_customer(name: str, email: Optional[str] = None,
                         phone: Optional[str] = None, address: Optional[str] = None) -> dict:
    """Create a new customer."""
    conn = await get_db_connection()
    try:
        # Insert into factuur_customer
        row = await conn.fetchrow(
            """
            INSERT INTO factuur_customer (name, email, phone, address, created_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            RETURNING id, name, email, phone, address, created_at
            """,
            name, email, phone, address
        )

        return {
            "success": True,
            "customer": {
                "id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "address": row["address"],
                "created_at": row["created_at"]
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        await conn.close()


async def create_credit_note(customer_id: Optional[int], customer_name: str,
                            invoice_date: str, total_amount: float, description: str,
                            bon_number: Optional[str] = None, vat_rate: float = 21.00) -> dict:
    """Create a credit note (invoice with document_type='credit_note')."""
    conn = await get_db_connection()
    try:
        # Calculate VAT
        total_decimal = Decimal(str(total_amount))
        vat_rate_decimal = Decimal(str(vat_rate))

        # Belgium VAT calculation: total includes VAT
        subtotal = (total_decimal / (Decimal('1') + vat_rate_decimal / Decimal('100'))).quantize(Decimal('0.01'))
        vat_amount = (total_decimal - subtotal).quantize(Decimal('0.01'))

        # Get next invoice number
        last_invoice = await conn.fetchrow(
            "SELECT MAX(invoice_number) as max_num FROM factuur_invoice"
        )
        next_invoice_number = (last_invoice["max_num"] or 0) + 1

        # Company details (Pomandi/Asia Fam)
        company_name = "Asia Fam BV"
        company_address = "Bredabaan 299, 2930 Brasschaat"
        company_vat = "BE 0791.452.593"
        company_email = "info@pomandi.com"

        # Parse invoice date
        invoice_dt = datetime.strptime(invoice_date, "%Y-%m-%d").date()

        # Build notes
        notes = f"Credit note: {description}"
        if bon_number:
            notes = f"Credit note voor bon {bon_number}: {description}"

        # Insert invoice
        invoice_row = await conn.fetchrow(
            """
            INSERT INTO factuur_invoice (
                document_type, customer_id, invoice_number,
                company_name, company_address, company_vat, company_email,
                client_name, client_address,
                invoice_date, due_date, notes, status,
                subtotal, vat_amount, total_amount,
                created_at, updated_at
            ) VALUES (
                'credit_note', $1, $2,
                $3, $4, $5, $6,
                $7, '',
                $8, $8, $9, 'approved',
                $10, $11, $12,
                NOW(), NOW()
            )
            RETURNING id, invoice_number
            """,
            customer_id, next_invoice_number,
            company_name, company_address, company_vat, company_email,
            customer_name,
            invoice_dt, notes,
            float(subtotal), float(vat_amount), float(total_decimal)
        )

        invoice_id = invoice_row["id"]
        invoice_number = invoice_row["invoice_number"]

        # Create invoice item
        item_description = description
        if bon_number:
            item_description = f"Terugbetaling - Bon {bon_number}"

        await conn.execute(
            """
            INSERT INTO factuur_invoiceitem (
                invoice_id, description, quantity, unit_price, vat_rate, total_price
            ) VALUES ($1, $2, 1, $3, $4, $3)
            """,
            invoice_id, item_description, float(total_decimal), float(vat_rate_decimal)
        )

        return {
            "success": True,
            "credit_note": {
                "id": invoice_id,
                "invoice_number": invoice_number,
                "document_type": "credit_note",
                "customer_name": customer_name,
                "invoice_date": invoice_date,
                "subtotal": float(subtotal),
                "vat_amount": float(vat_amount),
                "total_amount": float(total_decimal),
                "description": description,
                "status": "approved"
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        await conn.close()


async def list_credit_notes(limit: int = 20, customer_name: Optional[str] = None) -> dict:
    """List credit notes."""
    conn = await get_db_connection()
    try:
        query = """
            SELECT
                i.id, i.invoice_number, i.document_type,
                i.client_name, i.invoice_date, i.total_amount,
                i.status, i.notes, i.created_at
            FROM factuur_invoice i
            WHERE i.document_type = 'credit_note'
        """
        params = []

        if customer_name:
            query += " AND LOWER(i.client_name) LIKE LOWER($1)"
            params.append(f"%{customer_name}%")

        query += " ORDER BY i.invoice_date DESC, i.created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        rows = await conn.fetch(query, *params)

        credit_notes = []
        for row in rows:
            credit_notes.append({
                "id": row["id"],
                "invoice_number": row["invoice_number"],
                "document_type": row["document_type"],
                "customer_name": row["client_name"],
                "invoice_date": row["invoice_date"],
                "total_amount": row["total_amount"],
                "status": row["status"],
                "notes": row["notes"],
                "created_at": row["created_at"]
            })

        return {
            "count": len(credit_notes),
            "credit_notes": credit_notes
        }
    finally:
        await conn.close()


# ============================================
# MAIN
# ============================================

async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
