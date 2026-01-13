#!/usr/bin/env python3
"""
Retouche'da olup Saleor'da olmayan müşterileri Saleor'a aktarır.
Email notification göndermeden müşteri oluşturur.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "mcp-servers/saleor/.env")

# Eksik müşteri emailleri (test@example.com hariç)
MISSING_EMAILS = [
    "corvannoort@kpnmail.nl",
    "denislagana@yahoo.com",
    "erik_3355@hotmail.com",
    "kyano2404@hotmail.com",
    "leone.daf@gmail.com",
    "sofijob18@gmail.com"
]


async def get_retouche_customer_details():
    """Retouche'dan eksik müşterilerin detaylarını çek."""

    db_url = os.getenv(
        "RETOUCHE_DATABASE_URL",
        "postgres://postgres:iQ9bMYcfhLs7i9TrBPFDx84eNpbwmaYHYNnNGYRnH19Z9kkJgilZZWi6q00aNSMD@91.98.235.81:5436/postgres"
    )

    print("Retouche'dan müşteri detayları çekiliyor...")

    conn = await asyncpg.connect(db_url)

    # Email listesini SQL için hazırla
    email_list = ", ".join([f"'{e}'" for e in MISSING_EMAILS])

    query = f"""
    SELECT
        unique_id,
        name,
        email,
        phone,
        land,
        straat,
        huisnummer,
        bus,
        postcode,
        stad
    FROM tailoring_customer
    WHERE LOWER(email) IN ({email_list.lower()})
    """

    rows = await conn.fetch(query)
    await conn.close()

    customers = []
    for row in rows:
        # İsmi first/last name olarak ayır
        name_parts = (row["name"] or "").strip().split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Adresi birleştir
        address_parts = []
        if row["straat"]:
            addr = row["straat"]
            if row["huisnummer"]:
                addr += f" {row['huisnummer']}"
            if row["bus"]:
                addr += f" bus {row['bus']}"
            address_parts.append(addr)

        customers.append({
            "id": row["unique_id"],
            "email": row["email"],
            "first_name": first_name,
            "last_name": last_name,
            "phone": row["phone"] or "",
            "street_address": address_parts[0] if address_parts else "",
            "postal_code": row["postcode"] or "",
            "city": row["stad"] or "",
            "country": row["land"] or "BE"
        })

    return customers


async def create_saleor_customer(client, headers, customer):
    """Saleor'da müşteri oluştur (email göndermeden)."""

    api_url = os.getenv("SALEOR_API_URL", "https://api.pomandi.com/graphql/")

    # customerCreate mutation - redirectUrl verilmezse email gitmez
    # isConfirmed: true ile direkt onaylı hesap oluşturulur
    mutation = """
    mutation CustomerCreate($input: UserCreateInput!) {
        customerCreate(input: $input) {
            user {
                id
                email
                firstName
                lastName
            }
            errors {
                field
                message
                code
            }
        }
    }
    """

    # Password oluştur (isim + 12)
    password_base = customer["first_name"][:6] if customer["first_name"] else "user"
    password = f"{password_base}12"

    input_data = {
        "email": customer["email"],
        "firstName": customer["first_name"],
        "lastName": customer["last_name"],
        "isActive": True,
        "note": f"Migrated from Retouche (ID: {customer['id']})",
        "metadata": [
            {"key": "migrated_from", "value": "retouche"},
            {"key": "retouche_id", "value": str(customer["id"])},
            {"key": "phone", "value": customer["phone"]}
        ]
    }

    # Adres varsa ekle
    if customer["street_address"] or customer["city"]:
        input_data["defaultShippingAddress"] = {
            "firstName": customer["first_name"],
            "lastName": customer["last_name"],
            "streetAddress1": customer["street_address"],
            "city": customer["city"],
            "postalCode": customer["postal_code"],
            "country": "BE",
            "phone": customer["phone"]
        }
        input_data["defaultBillingAddress"] = input_data["defaultShippingAddress"]

    response = await client.post(
        api_url,
        json={"query": mutation, "variables": {"input": input_data}},
        headers=headers
    )

    data = response.json()

    if "errors" in data:
        return {"success": False, "error": data["errors"]}

    result = data.get("data", {}).get("customerCreate", {})

    if result.get("errors"):
        return {"success": False, "error": result["errors"]}

    return {"success": True, "user": result.get("user")}


async def main():
    print("="*60)
    print("RETOUCHE → SALEOR MÜŞTERİ AKTARIMI")
    print("(Email bildirimi KAPALARI)")
    print("="*60)
    print()

    # Retouche'dan detayları çek
    customers = await get_retouche_customer_details()

    print(f"\n{len(customers)} müşteri bulundu:")
    for c in customers:
        print(f"  - {c['email']}: {c['first_name']} {c['last_name']}")

    if not customers:
        print("\nAktarılacak müşteri bulunamadı!")
        return

    # Saleor'a bağlan
    api_url = os.getenv("SALEOR_API_URL", "https://api.pomandi.com/graphql/")
    email = os.getenv("SALEOR_EMAIL")
    password = os.getenv("SALEOR_PASSWORD")

    print("\nSaleor'a bağlanılıyor...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Login
        login_mutation = """
        mutation TokenCreate($email: String!, $password: String!) {
            tokenCreate(email: $email, password: $password) {
                token
                errors { field message }
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
        token = data["data"]["tokenCreate"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        print("Bağlantı başarılı!\n")

        # Her müşteriyi oluştur
        print("Müşteriler oluşturuluyor...")
        print("-" * 60)

        success_count = 0
        error_count = 0

        for customer in customers:
            result = await create_saleor_customer(client, headers, customer)

            if result["success"]:
                user = result["user"]
                print(f"✅ {customer['email']}")
                print(f"   → Saleor ID: {user['id']}")
                success_count += 1
            else:
                print(f"❌ {customer['email']}")
                print(f"   → Hata: {result['error']}")
                error_count += 1

        print("-" * 60)
        print(f"\n📊 SONUÇ:")
        print(f"   Başarılı: {success_count}")
        print(f"   Hatalı: {error_count}")


if __name__ == "__main__":
    asyncio.run(main())
