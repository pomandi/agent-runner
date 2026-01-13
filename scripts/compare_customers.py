#!/usr/bin/env python3
"""
Retouche ve Saleor veritabanlarındaki ortak müşterileri bulan script.
Email adresi üzerinden karşılaştırma yapar.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "mcp-servers/saleor/.env")


async def get_retouche_customers():
    """Retouche veritabanından müşterileri çek."""

    # Retouche database connection
    db_url = os.getenv(
        "RETOUCHE_DATABASE_URL",
        "postgres://postgres:iQ9bMYcfhLs7i9TrBPFDx84eNpbwmaYHYNnNGYRnH19Z9kkJgilZZWi6q00aNSMD@91.98.235.81:5436/postgres"
    )

    print("Retouche veritabanına bağlanılıyor...")

    try:
        conn = await asyncpg.connect(db_url)

        # Her iki tabloyu da kontrol et
        tables_to_check = [
            ("factuur_customer", "SELECT id, name, email, phone FROM factuur_customer WHERE email IS NOT NULL AND email != ''"),
            ("tailoring_customer", "SELECT unique_id as id, name, email, phone FROM tailoring_customer WHERE email IS NOT NULL AND email != ''")
        ]

        all_customers = []

        for table_name, query in tables_to_check:
            try:
                rows = await conn.fetch(query)
                print(f"  {table_name}: {len(rows)} müşteri bulundu")
                for row in rows:
                    all_customers.append({
                        "id": row["id"],
                        "name": row["name"],
                        "email": row["email"].lower().strip() if row["email"] else None,
                        "phone": row["phone"],
                        "source_table": table_name
                    })
            except Exception as e:
                print(f"  {table_name}: Tablo bulunamadı veya hata ({e})")

        await conn.close()

        # Unique emails
        unique_emails = set(c["email"] for c in all_customers if c["email"])
        print(f"  Toplam unique email: {len(unique_emails)}")

        return all_customers

    except Exception as e:
        print(f"Retouche bağlantı hatası: {e}")
        return []


async def get_saleor_customers():
    """Saleor GraphQL API'den müşterileri çek."""

    api_url = os.getenv("SALEOR_API_URL", "https://api.pomandi.com/graphql/")
    email = os.getenv("SALEOR_EMAIL", "nurullah_cevik1989@hotmail.com")
    password = os.getenv("SALEOR_PASSWORD")

    if not password:
        print("SALEOR_PASSWORD environment variable gerekli!")
        return []

    print("Saleor API'ye bağlanılıyor...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Login
        login_mutation = """
        mutation TokenCreate($email: String!, $password: String!) {
            tokenCreate(email: $email, password: $password) {
                token
                errors {
                    field
                    message
                }
            }
        }
        """

        response = await client.post(
            api_url,
            json={
                "query": login_mutation,
                "variables": {"email": email, "password": password}
            }
        )

        data = response.json()
        if data.get("data", {}).get("tokenCreate", {}).get("errors"):
            print(f"Saleor login hatası: {data['data']['tokenCreate']['errors']}")
            return []

        token = data["data"]["tokenCreate"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Fetch all customers with pagination
        all_customers = []
        has_next = True
        cursor = None
        page = 1

        customers_query = """
        query GetCustomers($first: Int!, $after: String) {
            customers(first: $first, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                edges {
                    node {
                        id
                        email
                        firstName
                        lastName
                        dateJoined
                        isActive
                        metadata {
                            key
                            value
                        }
                    }
                }
            }
        }
        """

        while has_next:
            variables = {"first": 100}
            if cursor:
                variables["after"] = cursor

            response = await client.post(
                api_url,
                json={"query": customers_query, "variables": variables},
                headers=headers
            )

            data = response.json()

            if "errors" in data:
                print(f"GraphQL hatası: {data['errors']}")
                break

            customers_data = data.get("data", {}).get("customers", {})
            edges = customers_data.get("edges", [])

            for edge in edges:
                node = edge["node"]
                metadata = {m["key"]: m["value"] for m in node.get("metadata", [])}

                all_customers.append({
                    "id": node["id"],
                    "email": node["email"].lower().strip() if node["email"] else None,
                    "name": f"{node.get('firstName', '')} {node.get('lastName', '')}".strip(),
                    "is_active": node["is_active"] if "is_active" in node else node.get("isActive"),
                    "date_joined": node.get("dateJoined"),
                    "migrated_from": metadata.get("migrated_from"),
                    "phone": metadata.get("phone")
                })

            page_info = customers_data.get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

            print(f"  Sayfa {page}: {len(edges)} müşteri çekildi")
            page += 1

        # Unique emails
        unique_emails = set(c["email"] for c in all_customers if c["email"])
        print(f"  Toplam Saleor müşteri: {len(all_customers)}")
        print(f"  Toplam unique email: {len(unique_emails)}")

        return all_customers


def compare_customers(retouche_customers, saleor_customers):
    """İki sistemdeki müşterileri karşılaştır."""

    print("\n" + "="*60)
    print("KARŞILAŞTIRMA SONUÇLARI")
    print("="*60)

    # Email setleri oluştur
    retouche_emails = {c["email"] for c in retouche_customers if c["email"]}
    saleor_emails = {c["email"] for c in saleor_customers if c["email"]}

    # Ortak emailler
    common_emails = retouche_emails & saleor_emails

    # Sadece Retouche'da olanlar
    only_retouche = retouche_emails - saleor_emails

    # Sadece Saleor'da olanlar
    only_saleor = saleor_emails - retouche_emails

    # Özet istatistikler
    print(f"\n📊 ÖZET İSTATİSTİKLER:")
    print(f"   Retouche müşteri sayısı: {len(retouche_customers)}")
    print(f"   Retouche unique email: {len(retouche_emails)}")
    print(f"   Saleor müşteri sayısı: {len(saleor_customers)}")
    print(f"   Saleor unique email: {len(saleor_emails)}")
    print(f"\n✅ ORTAK MÜŞTERİ (her iki DB'de): {len(common_emails)}")
    print(f"🔵 Sadece Retouche'da: {len(only_retouche)}")
    print(f"🟢 Sadece Saleor'da: {len(only_saleor)}")

    # Yüzdelik analiz
    if retouche_emails:
        retouche_overlap = (len(common_emails) / len(retouche_emails)) * 100
        print(f"\n📈 Retouche müşterilerinin Saleor'da olma oranı: {retouche_overlap:.1f}%")

    if saleor_emails:
        saleor_overlap = (len(common_emails) / len(saleor_emails)) * 100
        print(f"📈 Saleor müşterilerinin Retouche'da olma oranı: {saleor_overlap:.1f}%")

    # Ortak müşteri detayları
    if common_emails:
        print(f"\n📋 ORTAK MÜŞTERİ LİSTESİ (İlk 20):")
        print("-" * 60)

        # Retouche müşteri map
        retouche_map = {c["email"]: c for c in retouche_customers if c["email"]}
        saleor_map = {c["email"]: c for c in saleor_customers if c["email"]}

        for i, email in enumerate(sorted(common_emails)[:20], 1):
            r = retouche_map.get(email, {})
            s = saleor_map.get(email, {})
            print(f"{i:3}. {email}")
            print(f"     Retouche: {r.get('name', 'N/A')} (ID: {r.get('id', 'N/A')})")
            print(f"     Saleor:   {s.get('name', 'N/A')} (ID: {s.get('id', 'N/A')[:20]}...)")

        if len(common_emails) > 20:
            print(f"\n     ... ve {len(common_emails) - 20} müşteri daha")

    # Sadece Retouche'da olanlar (ilk 10)
    if only_retouche:
        print(f"\n🔵 SADECE RETOUCHE'DA OLANLAR (İlk 10):")
        print("-" * 60)
        retouche_map = {c["email"]: c for c in retouche_customers if c["email"]}
        for i, email in enumerate(sorted(only_retouche)[:10], 1):
            r = retouche_map.get(email, {})
            print(f"{i:3}. {email} - {r.get('name', 'N/A')}")

        if len(only_retouche) > 10:
            print(f"\n     ... ve {len(only_retouche) - 10} müşteri daha")

    # Migration analizi
    migrated_count = sum(1 for c in saleor_customers if c.get("migrated_from") == "retouche")
    print(f"\n🔄 MİGRASYON DURUMU:")
    print(f"   'migrated_from: retouche' metadata olan Saleor müşteri: {migrated_count}")

    return {
        "retouche_total": len(retouche_customers),
        "retouche_unique_emails": len(retouche_emails),
        "saleor_total": len(saleor_customers),
        "saleor_unique_emails": len(saleor_emails),
        "common_count": len(common_emails),
        "only_retouche": len(only_retouche),
        "only_saleor": len(only_saleor),
        "common_emails": list(common_emails)
    }


async def main():
    print("="*60)
    print("RETOUCHE - SALEOR MÜŞTERİ KARŞILAŞTIRMA")
    print("="*60)
    print()

    # Retouche müşterilerini çek
    retouche_customers = await get_retouche_customers()
    print()

    # Saleor müşterilerini çek
    saleor_customers = await get_saleor_customers()

    # Karşılaştır
    if retouche_customers and saleor_customers:
        results = compare_customers(retouche_customers, saleor_customers)

        print("\n" + "="*60)
        print("SONUÇ")
        print("="*60)
        print(f"\n🎯 {results['common_count']} müşteri HER İKİ VERİTABANINDA DA MEVCUT")
        print(f"   (Email adresi üzerinden eşleşme)")
    else:
        print("\n❌ Veritabanlarından veri çekilemedi!")
        if not retouche_customers:
            print("   - Retouche bağlantısı başarısız")
        if not saleor_customers:
            print("   - Saleor bağlantısı başarısız (SALEOR_PASSWORD gerekli)")


if __name__ == "__main__":
    asyncio.run(main())
