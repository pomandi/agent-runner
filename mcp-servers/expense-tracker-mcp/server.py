#!/usr/bin/env python3
"""
Expense Tracker MCP Server
Invoice extraction agent için expense-tracker-app API entegrasyonu
"""

import os
import requests
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("expense-tracker")

# API Configuration
API_URL = os.environ.get("EXPENSE_TRACKER_API_URL", "http://yw44sk08wwokcws4s88gcgs0.91.98.235.81.sslip.io")
MAX_EXTRACTION_ATTEMPTS = 3


def make_request(method: str, endpoint: str, data: Optional[dict] = None) -> dict:
    """Make HTTP request to expense-tracker API."""
    url = f"{API_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=data, timeout=30)
        else:
            return {"success": False, "error": f"Unsupported method: {method}"}

        if response.status_code in [200, 201]:
            return {"success": True, "data": response.json()}
        else:
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# TOOLS
# ============================================================

@mcp.tool()
def list_pending_invoices(limit: int = 10, vendor: Optional[str] = None) -> dict:
    """
    Extraction bekleyen faturaları listeler.

    Args:
        limit: Maksimum fatura sayısı (varsayılan: 10)
        vendor: Vendor adına göre filtrele (opsiyonel)

    Returns:
        Bekleyen faturaların listesi (id, fileName, filePath, vendorName, extractionAttempts)
    """
    endpoint = f"/api/invoices/extraction?limit={limit}"
    if vendor:
        endpoint += f"&vendor={vendor}"

    result = make_request("GET", endpoint)

    if not result["success"]:
        return result

    invoices = result["data"].get("invoices", [])

    return {
        "success": True,
        "count": len(invoices),
        "max_attempts": MAX_EXTRACTION_ATTEMPTS,
        "invoices": [
            {
                "id": inv["id"],
                "fileName": inv.get("fileName"),
                "filePath": inv.get("filePath"),
                "mimeType": inv.get("mimeType"),
                "vendorName": inv.get("vendorName"),
                "vendorId": inv.get("vendorId"),
                "extractionStatus": inv.get("extractionStatus"),
                "extractionAttempts": inv.get("extractionAttempts", 0),
                "totalAmount": inv.get("totalAmount"),
                "invoiceDate": inv.get("invoiceDate")
            }
            for inv in invoices
        ]
    }


@mcp.tool()
def get_invoice(invoice_id: int) -> dict:
    """
    Tek bir faturanın detaylı bilgilerini getirir.

    Args:
        invoice_id: Fatura ID

    Returns:
        Fatura detayları (tüm alanlar, dosya bilgileri, eşleşme bilgisi)
    """
    result = make_request("GET", f"/api/invoices/{invoice_id}")

    if not result["success"]:
        return result

    inv = result["data"]

    return {
        "success": True,
        "invoice": {
            "id": inv.get("id"),
            "invoiceNumber": inv.get("invoiceNumber"),
            "invoiceDate": inv.get("invoiceDate"),
            "dueDate": inv.get("dueDate"),
            "amount": inv.get("amount"),
            "vatAmount": inv.get("vatAmount"),
            "currency": inv.get("currency", "EUR"),
            "vendorId": inv.get("vendorId"),
            "vendorName": inv.get("vendorName"),
            "fileName": inv.get("fileName"),
            "filePath": inv.get("filePath"),
            "mimeType": inv.get("mimeType"),
            "fileSize": inv.get("fileSize"),
            "sourceType": inv.get("sourceType"),
            "status": inv.get("status"),
            "extractionStatus": inv.get("extractionStatus"),
            "extractionAttempts": inv.get("extractionAttempts", 0),
            "extractionError": inv.get("extractionError"),
            "extractionConfidence": inv.get("extractionConfidence"),
            "extractedData": inv.get("extractedData"),
            "match": inv.get("match")
        }
    }


@mcp.tool()
def get_invoice_file_url(invoice_id: int) -> dict:
    """
    Fatura dosyasının URL'ini döndürür. WebFetch ile analiz için kullanılır.

    Args:
        invoice_id: Fatura ID

    Returns:
        Dosya URL'i ve bilgileri
    """
    result = make_request("GET", f"/api/invoices/{invoice_id}")

    if not result["success"]:
        return result

    inv = result["data"]
    file_path = inv.get("filePath")

    if not file_path:
        return {
            "success": False,
            "error": f"Fatura #{invoice_id} için dosya bulunamadı"
        }

    return {
        "success": True,
        "invoice_id": invoice_id,
        "file_url": file_path,
        "file_name": inv.get("fileName"),
        "mime_type": inv.get("mimeType"),
        "file_size": inv.get("fileSize"),
        "vendor_name": inv.get("vendorName"),
        "hint": "Bu URL'i WebFetch veya Read tool ile kullanarak dosyayı analiz edebilirsiniz"
    }


@mcp.tool()
def mark_processing(invoice_id: int) -> dict:
    """
    Faturayı 'processing' olarak işaretler.
    Extraction başlamadan önce çağrılmalı.

    Args:
        invoice_id: Fatura ID

    Returns:
        İşlem sonucu
    """
    payload = {
        "invoiceId": invoice_id,
        "status": "processing"
    }

    result = make_request("POST", "/api/invoices/extraction", payload)

    if result["success"]:
        return {
            "success": True,
            "message": f"Fatura #{invoice_id} 'processing' olarak işaretlendi"
        }

    return result


@mcp.tool()
def update_extraction(
    invoice_id: int,
    status: str,
    invoice_number: Optional[str] = None,
    invoice_date: Optional[str] = None,
    due_date: Optional[str] = None,
    total_amount: Optional[float] = None,
    vat_amount: Optional[float] = None,
    currency: Optional[str] = None,
    vendor_name: Optional[str] = None,
    vendor_vat: Optional[str] = None,
    description: Optional[str] = None,
    confidence: float = 0.9,
    error: Optional[str] = None
) -> dict:
    """
    Fatura extraction sonucunu kaydeder.

    Args:
        invoice_id: Fatura ID (zorunlu)
        status: completed/partial/failed/unreadable (zorunlu)
        invoice_number: Fatura numarası
        invoice_date: Fatura tarihi (YYYY-MM-DD)
        due_date: Vade tarihi (YYYY-MM-DD)
        total_amount: Toplam tutar (sayı)
        vat_amount: KDV tutarı (sayı)
        currency: Para birimi (EUR/USD)
        vendor_name: Satıcı adı
        vendor_vat: BTW/VAT numarası
        description: Fatura açıklaması
        confidence: Güven skoru 0-1 (varsayılan: 0.9)
        error: Hata mesajı (failed/unreadable için)

    Returns:
        Güncelleme sonucu
    """
    if status not in ["completed", "partial", "failed", "unreadable"]:
        return {
            "success": False,
            "error": f"Geçersiz status: {status}. completed/partial/failed/unreadable olmalı"
        }

    payload = {
        "invoiceId": invoice_id,
        "status": status,
        "confidence": confidence
    }

    # Build extracted data
    extracted_data = {}
    if invoice_number:
        extracted_data["invoiceNumber"] = invoice_number
    if invoice_date:
        extracted_data["invoiceDate"] = invoice_date
    if due_date:
        extracted_data["dueDate"] = due_date
    if total_amount is not None:
        extracted_data["totalAmount"] = total_amount
    if vat_amount is not None:
        extracted_data["vatAmount"] = vat_amount
    if currency:
        extracted_data["currency"] = currency
    if vendor_name:
        extracted_data["vendorName"] = vendor_name
    if vendor_vat:
        extracted_data["vendorVat"] = vendor_vat
    if description:
        extracted_data["description"] = description

    if extracted_data:
        payload["extractedData"] = extracted_data

    if error:
        payload["error"] = error

    result = make_request("POST", "/api/invoices/extraction", payload)

    if result["success"]:
        inv = result["data"].get("invoice", {})
        return {
            "success": True,
            "message": f"Fatura #{invoice_id} güncellendi",
            "invoice": {
                "id": inv.get("id"),
                "extractionStatus": inv.get("extractionStatus"),
                "extractionAttempts": inv.get("extractionAttempts"),
                "extractedAt": inv.get("extractedAt")
            }
        }

    return result


@mcp.tool()
def mark_failed(invoice_id: int, error_message: str) -> dict:
    """
    Faturayı 'failed' olarak işaretler (tekrar denenebilir).

    Args:
        invoice_id: Fatura ID
        error_message: Hata mesajı

    Returns:
        İşlem sonucu
    """
    return update_extraction(
        invoice_id=invoice_id,
        status="failed",
        error=error_message,
        confidence=0
    )


@mcp.tool()
def mark_unreadable(invoice_id: int, reason: str) -> dict:
    """
    Faturayı 'unreadable' olarak işaretler (daha fazla denenmez).

    Args:
        invoice_id: Fatura ID
        reason: Okunamama nedeni

    Returns:
        İşlem sonucu
    """
    return update_extraction(
        invoice_id=invoice_id,
        status="unreadable",
        error=reason,
        confidence=0
    )


@mcp.tool()
def get_extraction_stats() -> dict:
    """
    Extraction istatistiklerini getirir.

    Returns:
        Pending, completed, failed sayıları
    """
    # Get pending count
    pending_result = make_request("GET", "/api/invoices/extraction?limit=100")

    if not pending_result["success"]:
        return pending_result

    pending_invoices = pending_result["data"].get("invoices", [])

    # Count by status
    pending_count = len([i for i in pending_invoices if i.get("extractionStatus") == "pending"])
    failed_count = len([i for i in pending_invoices if i.get("extractionStatus") == "failed"])

    return {
        "success": True,
        "stats": {
            "total_pending": len(pending_invoices),
            "status_pending": pending_count,
            "status_failed": failed_count,
            "max_attempts": MAX_EXTRACTION_ATTEMPTS
        },
        "hint": "list_pending_invoices ile detaylı liste alabilirsiniz"
    }


@mcp.tool()
def get_extraction_prompt() -> dict:
    """
    Fatura analizi için kullanılacak prompt'u döndürür.

    Returns:
        Claude Vision için analiz prompt'u
    """
    return {
        "success": True,
        "prompt": """Bu bir fatura görüntüsü. Lütfen aşağıdaki bilgileri çıkar:

1. invoiceNumber: Fatura numarası (Invoice #, Factuurnummer, Facture N°)
2. invoiceDate: Fatura tarihi (YYYY-MM-DD formatında)
3. dueDate: Ödeme vadesi (YYYY-MM-DD formatında, varsa)
4. totalAmount: Toplam tutar (sadece sayı, virgül yerine nokta)
5. vatAmount: KDV/BTW tutarı (sadece sayı, varsa)
6. currency: Para birimi (EUR, USD, vs.)
7. vendorName: Satıcı/firma adı
8. vendorVat: BTW/VAT numarası (varsa)
9. description: Fatura açıklaması (kısa, 1-2 cümle)

Eğer bir alan bulunamazsa belirtme.
Tutarları virgül yerine nokta ile yaz (60.29 gibi).
Tarihleri YYYY-MM-DD formatında yaz (2024-12-15 gibi).""",
        "usage": """
WebFetch tool ile fatura URL'ini açın ve bu prompt'u kullanın.
Sonra update_extraction tool ile sonuçları kaydedin.
"""
    }


if __name__ == "__main__":
    mcp.run()
