#!/usr/bin/env python3
"""
Invoice Extractor - Fatura bilgilerini cikaran script

Bu script Claude Code tarafindan calistirilir ve fatura bilgilerini cikarir.

Kullanim:
    python extract.py --invoice-id 123
    python extract.py --all-pending
    python extract.py --vendor "MyParcel"
    python extract.py --list  # Sadece pending faturalari listele
"""

import argparse
import json
import os
import sys
import requests
from typing import Optional, Dict, Any, List

# Ortam degiskenleri
API_URL = os.getenv("EXPENSE_TRACKER_API_URL", "http://yw44sk08wwokcws4s88gcgs0.91.98.235.81.sslip.io")
MAX_ATTEMPTS = 3  # Token tasarrufu icin maksimum deneme sayisi


def get_pending_invoices(vendor_name: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """Bekleyen faturalari getir (extraction API kullanarak)"""
    url = f"{API_URL}/api/invoices/extraction?limit={limit}"

    response = requests.get(url)
    if response.status_code != 200:
        print(f"Error fetching invoices: {response.status_code}")
        print(response.text)
        return []

    data = response.json()
    invoices = data.get("invoices", [])

    # Vendor filtresi
    if vendor_name:
        invoices = [inv for inv in invoices if (inv.get("vendorName") or "").lower() == vendor_name.lower()]

    return invoices


def get_invoice(invoice_id: int) -> Optional[Dict[str, Any]]:
    """Tek fatura bilgilerini getir"""
    url = f"{API_URL}/api/invoices/{invoice_id}"

    response = requests.get(url)
    if response.status_code != 200:
        print(f"Error fetching invoice {invoice_id}: {response.status_code}")
        return None

    return response.json()


def mark_processing(invoice_id: int) -> bool:
    """Faturayi 'processing' olarak isaretle"""
    url = f"{API_URL}/api/invoices/extraction"

    response = requests.post(url, json={
        "invoiceId": invoice_id,
        "status": "processing"
    }, headers={"Content-Type": "application/json"})

    return response.status_code == 200


def update_extraction(invoice_id: int, status: str, extracted_data: Optional[Dict] = None,
                      confidence: Optional[float] = None, error: Optional[str] = None) -> bool:
    """Extraction sonucunu guncelle"""
    url = f"{API_URL}/api/invoices/extraction"

    payload = {
        "invoiceId": invoice_id,
        "status": status
    }

    if extracted_data:
        payload["extractedData"] = extracted_data
    if confidence is not None:
        payload["confidence"] = confidence
    if error:
        payload["error"] = error

    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})

    if response.status_code != 200:
        print(f"Error updating extraction: {response.status_code}")
        print(response.text)
        return False

    return True


def print_invoice_for_extraction(invoice: Dict[str, Any]) -> None:
    """
    Fatura bilgilerini Claude Code'un analiz etmesi icin yazdir.

    Claude Code bu ciktiyi okuyup dosyayi analiz edecek.
    """
    file_url = invoice.get("filePath")
    file_name = invoice.get("fileName")
    attempts = invoice.get("extractionAttempts", 0)
    last_error = invoice.get("extractionError")

    print(f"\n{'='*60}")
    print(f"FATURA ANALIZI GEREKLI")
    print(f"{'='*60}")
    print(f"Invoice ID: {invoice.get('id')}")
    print(f"Dosya: {file_name}")
    print(f"URL: {file_url}")
    print(f"Mevcut Vendor: {invoice.get('vendorName', 'Bilinmiyor')}")
    print(f"Deneme: {attempts + 1}/{MAX_ATTEMPTS}")

    if last_error:
        print(f"Son Hata: {last_error}")

    print(f"{'='*60}")
    print(f"\nLutfen bu faturayi analiz edin ve su bilgileri cikarin:")
    print(f"- invoiceNumber: Fatura numarasi")
    print(f"- invoiceDate: Fatura tarihi (YYYY-MM-DD)")
    print(f"- dueDate: Odeme vadesi (YYYY-MM-DD)")
    print(f"- totalAmount: Toplam tutar (sayi)")
    print(f"- vatAmount: KDV tutari (sayi)")
    print(f"- currency: Para birimi (EUR/USD)")
    print(f"- description: Kisa aciklama")
    print(f"{'='*60}")
    print(f"\nSonra su komutu calistirin:")
    print(f"python extract.py --invoice-id {invoice.get('id')} --result '<JSON>'")
    print(f"\nOrnek JSON:")
    print(json.dumps({
        "invoiceNumber": "INV-2024-001",
        "invoiceDate": "2024-12-15",
        "dueDate": "2025-01-15",
        "totalAmount": 60.29,
        "vatAmount": 10.46,
        "currency": "EUR",
        "description": "Kargo hizmeti"
    }, indent=2))
    print(f"{'='*60}\n")


def process_single_invoice(invoice_id: int, result_json: Optional[str] = None,
                          dry_run: bool = False, status: str = "completed",
                          confidence: float = 0.9) -> bool:
    """Tek faturayi isle"""

    if result_json:
        # Sonuc JSON'i verildiyse, dogrudan guncelle
        try:
            extracted_data = json.loads(result_json)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return False

        if dry_run:
            print(f"[DRY-RUN] Would update invoice {invoice_id} with:")
            print(json.dumps(extracted_data, indent=2))
            return True

        # Guncelle
        success = update_extraction(
            invoice_id=invoice_id,
            status=status,
            extracted_data=extracted_data,
            confidence=confidence
        )

        if success:
            print(f"Invoice {invoice_id} updated successfully")
        return success

    else:
        # Sonuc yoksa, faturanin analiz edilmesini iste
        invoice = get_invoice(invoice_id)
        if not invoice:
            return False

        # Dosya URL'i var mi kontrol et
        if not invoice.get("filePath"):
            print(f"Invoice {invoice_id}: No file URL, skipping")
            update_extraction(invoice_id, "unreadable", error="No file URL")
            return False

        # Extraction durumunu kontrol et
        if invoice.get("extractionAttempts", 0) >= MAX_ATTEMPTS:
            print(f"Invoice {invoice_id}: Max attempts ({MAX_ATTEMPTS}) reached, skipping")
            return False

        # Processing olarak isaretle
        mark_processing(invoice_id)

        # Analiz istegi yazdir
        print_invoice_for_extraction(invoice)
        return True


def list_pending_invoices(vendor_name: Optional[str] = None, limit: int = 10) -> None:
    """Bekleyen faturalari listele"""
    invoices = get_pending_invoices(vendor_name, limit)

    if not invoices:
        print("No pending invoices found")
        return

    print(f"\n{'='*80}")
    print(f"BEKLEYEN FATURALAR ({len(invoices)} adet)")
    print(f"{'='*80}")

    for inv in invoices:
        attempts = inv.get("extractionAttempts", 0)
        status_icon = "!" if attempts > 0 else " "
        print(f"{status_icon} ID:{inv['id']:4d} | {inv.get('fileName', 'Unknown')[:30]:30s} | "
              f"Vendor: {inv.get('vendorName', '-')[:15]:15s} | Attempts: {attempts}/{MAX_ATTEMPTS}")

    print(f"{'='*80}")
    print(f"\nTek fatura islemek icin:")
    print(f"  python extract.py --invoice-id <ID>")
    print(f"\nTum pending faturalari islemek icin:")
    print(f"  python extract.py --all-pending")


def mark_failed(invoice_id: int, error: str) -> bool:
    """Faturayi failed olarak isaretle"""
    return update_extraction(
        invoice_id=invoice_id,
        status="failed",
        error=error
    )


def mark_unreadable(invoice_id: int, reason: str) -> bool:
    """Faturayi unreadable olarak isaretle (daha fazla denemeyecek)"""
    return update_extraction(
        invoice_id=invoice_id,
        status="unreadable",
        error=reason
    )


def main():
    parser = argparse.ArgumentParser(description="Invoice Extractor")
    parser.add_argument("--invoice-id", type=int, help="Tek fatura ID")
    parser.add_argument("--all-pending", action="store_true", help="Tum bekleyen faturalar")
    parser.add_argument("--list", action="store_true", help="Sadece bekleyen faturalari listele")
    parser.add_argument("--vendor", type=str, help="Vendor adina gore filtrele")
    parser.add_argument("--dry-run", action="store_true", help="Degisiklik yapmadan test et")
    parser.add_argument("--limit", type=int, default=10, help="Maksimum fatura sayisi")

    # Sonuc parametreleri
    parser.add_argument("--result", type=str, help="Extraction sonucu JSON")
    parser.add_argument("--status", type=str, default="completed",
                       choices=["completed", "partial", "failed", "unreadable"],
                       help="Extraction durumu")
    parser.add_argument("--confidence", type=float, default=0.9, help="Guven skoru (0-1)")
    parser.add_argument("--error", type=str, help="Hata mesaji (failed/unreadable icin)")

    args = parser.parse_args()

    # Sadece listele
    if args.list:
        list_pending_invoices(args.vendor, args.limit)
        sys.exit(0)

    # Tek fatura - sonuc ile
    if args.invoice_id and args.result:
        success = process_single_invoice(
            args.invoice_id,
            args.result,
            args.dry_run,
            args.status,
            args.confidence
        )
        sys.exit(0 if success else 1)

    # Tek fatura - failed/unreadable isaretle
    if args.invoice_id and args.error:
        if args.status == "unreadable":
            success = mark_unreadable(args.invoice_id, args.error)
        else:
            success = mark_failed(args.invoice_id, args.error)
        print(f"Invoice {args.invoice_id} marked as {args.status}")
        sys.exit(0 if success else 1)

    # Tek fatura - analiz istegi
    if args.invoice_id:
        success = process_single_invoice(args.invoice_id, dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    # Tum bekleyen faturalar
    if args.all_pending or args.vendor:
        invoices = get_pending_invoices(args.vendor, args.limit)

        if not invoices:
            print("No pending invoices found")
            sys.exit(0)

        print(f"\n{len(invoices)} fatura islenecek:")
        for inv in invoices:
            print(f"  - #{inv['id']}: {inv.get('fileName', 'Unknown')} ({inv.get('vendorName', 'Bilinmiyor')})")

        for inv in invoices:
            process_single_invoice(inv["id"], dry_run=args.dry_run)

        sys.exit(0)

    # Hicbir arguman verilmemisse, yardim goster
    parser.print_help()
    print("\n" + "="*60)
    print("HIZLI BASLANGIC")
    print("="*60)
    print("1. Bekleyen faturalari gor:")
    print("   python extract.py --list")
    print("\n2. Tek fatura analiz et:")
    print("   python extract.py --invoice-id 123")
    print("\n3. Sonucu kaydet:")
    print('   python extract.py --invoice-id 123 --result \'{"invoiceNumber":"INV-001","totalAmount":100}\'')
    print("="*60)
    sys.exit(1)


if __name__ == "__main__":
    main()
