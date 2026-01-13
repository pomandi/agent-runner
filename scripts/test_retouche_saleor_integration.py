#!/usr/bin/env python3
"""
Retouche-Saleor entegrasyon testi.
Django'dan bağımsız olarak API'yi test eder.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
import httpx
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "mcp-servers/saleor/.env")

# Saleor API ayarları
SALEOR_API_URL = os.getenv('SALEOR_URL', 'https://api.pomandi.com/graphql/')
SALEOR_EMAIL = os.getenv('SALEOR_EMAIL', 'nurullah_cevik1989@hotmail.com')
SALEOR_PASSWORD = os.getenv('SALEOR_PASSWORD')

# Retouche DB
RETOUCHE_DB_URL = os.getenv(
    "RETOUCHE_DATABASE_URL",
    "postgres://postgres:iQ9bMYcfhLs7i9TrBPFDx84eNpbwmaYHYNnNGYRnH19Z9kkJgilZZWi6q00aNSMD@91.98.235.81:5436/postgres"
)


async def test_saleor_connection():
    """Saleor API bağlantısını test et."""
    print("1. Saleor API bağlantısı test ediliyor...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        mutation = """
        mutation TokenCreate($email: String!, $password: String!) {
            tokenCreate(email: $email, password: $password) {
                token
                errors { field message }
            }
        }
        """

        response = await client.post(
            SALEOR_API_URL,
            json={
                "query": mutation,
                "variables": {"email": SALEOR_EMAIL, "password": SALEOR_PASSWORD}
            }
        )

        data = response.json()
        token = data.get("data", {}).get("tokenCreate", {}).get("token")

        if token:
            print("   ✅ Saleor API bağlantısı başarılı")
            return token
        else:
            print(f"   ❌ Saleor API bağlantısı başarısız: {data}")
            return None


async def get_sample_retouche_customer():
    """Retouche'dan örnek müşteri çek."""
    print("\n2. Retouche'dan örnek müşteri çekiliyor...")

    conn = await asyncpg.connect(RETOUCHE_DB_URL)

    query = """
    SELECT
        unique_id,
        name,
        email,
        phone,
        straat,
        huisnummer,
        bus,
        postcode,
        stad,
        service_type,
        order_ready,
        is_picked_up,
        created_at
    FROM tailoring_customer
    WHERE email IS NOT NULL AND email != ''
    ORDER BY created_at DESC
    LIMIT 1
    """

    row = await conn.fetchrow(query)
    await conn.close()

    if row:
        print(f"   Müşteri: {row['name']} ({row['email']})")
        print(f"   ID: {row['unique_id']}, Oluşturulma: {row['created_at']}")
        return dict(row)
    else:
        print("   ⚠️ Müşteri bulunamadı")
        return None


async def sync_customer_to_saleor(token, customer):
    """Müşteriyi Saleor'a senkronize et."""
    print("\n3. Müşteri Saleor'a senkronize ediliyor...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {token}"}

        # Önce var mı kontrol et
        check_query = """
        query FindCustomer($email: String!) {
            customers(filter: {search: $email}, first: 1) {
                edges {
                    node {
                        id
                        email
                        firstName
                        lastName
                        metadata { key value }
                    }
                }
            }
        }
        """

        response = await client.post(
            SALEOR_API_URL,
            json={"query": check_query, "variables": {"email": customer["email"]}},
            headers=headers
        )

        data = response.json()
        edges = data.get("data", {}).get("customers", {}).get("edges", [])

        if edges:
            existing = edges[0]["node"]
            print(f"   Saleor'da mevcut: {existing['id']}")

            # Metadata kontrol et
            metadata = {m["key"]: m["value"] for m in existing.get("metadata", [])}
            if metadata.get("retouche_id"):
                print(f"   Retouche ID zaten kayıtlı: {metadata['retouche_id']}")
            else:
                print("   Retouche metadata ekleniyor...")
                # Update metadata
                update_mutation = """
                mutation UpdateMetadata($id: ID!, $input: [MetadataInput!]!) {
                    updateMetadata(id: $id, input: $input) {
                        errors { field message }
                    }
                }
                """

                metadata_input = [
                    {"key": "retouche_customer", "value": "true"},
                    {"key": "retouche_id", "value": str(customer["unique_id"])},
                    {"key": "retouche_phone", "value": customer["phone"] or ""},
                ]

                await client.post(
                    SALEOR_API_URL,
                    json={
                        "query": update_mutation,
                        "variables": {"id": existing["id"], "input": metadata_input}
                    },
                    headers=headers
                )
                print("   ✅ Metadata güncellendi")

            return existing

        # Yoksa oluştur
        print("   Saleor'da mevcut değil, oluşturuluyor...")

        # İsmi ayır
        name_parts = (customer["name"] or "").strip().split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Adres
        street = ""
        if customer["straat"]:
            street = customer["straat"]
            if customer["huisnummer"]:
                street += f" {customer['huisnummer']}"
            if customer["bus"]:
                street += f" bus {customer['bus']}"

        create_mutation = """
        mutation CustomerCreate($input: UserCreateInput!) {
            customerCreate(input: $input) {
                user { id email firstName lastName }
                errors { field message code }
            }
        }
        """

        input_data = {
            "email": customer["email"],
            "firstName": first_name,
            "lastName": last_name,
            "isActive": True,
            "note": f"Retouche müşterisi (ID: {customer['unique_id']})",
            "metadata": [
                {"key": "retouche_customer", "value": "true"},
                {"key": "retouche_id", "value": str(customer["unique_id"])},
                {"key": "retouche_phone", "value": customer["phone"] or ""},
            ]
        }

        if street or customer["stad"]:
            input_data["defaultShippingAddress"] = {
                "firstName": first_name,
                "lastName": last_name,
                "streetAddress1": street,
                "city": customer["stad"] or "",
                "postalCode": customer["postcode"] or "",
                "country": "BE",
                "phone": customer["phone"] or ""
            }

        response = await client.post(
            SALEOR_API_URL,
            json={"query": create_mutation, "variables": {"input": input_data}},
            headers=headers
        )

        data = response.json()
        result = data.get("data", {}).get("customerCreate", {})

        if result.get("errors"):
            print(f"   ❌ Hata: {result['errors']}")
            return None

        user = result.get("user")
        if user:
            print(f"   ✅ Oluşturuldu: {user['id']}")
            return user

        return None


async def main():
    print("="*60)
    print("RETOUCHE-SALEOR ENTEGRASYON TESTİ")
    print("="*60)

    # Saleor bağlantısı
    token = await test_saleor_connection()
    if not token:
        return

    # Örnek müşteri
    customer = await get_sample_retouche_customer()
    if not customer:
        return

    # Senkronize et
    result = await sync_customer_to_saleor(token, customer)

    print("\n" + "="*60)
    if result:
        print("✅ ENTEGRASYON TESTİ BAŞARILI")
        print(f"   Retouche ID: {customer['unique_id']}")
        print(f"   Saleor ID: {result['id']}")
    else:
        print("❌ ENTEGRASYON TESTİ BAŞARISIZ")

    print("\n📝 NOT: Retouche Django app'i yeniden başlatıldığında")
    print("   yeni müşteriler otomatik olarak Saleor'a senkronize olacak.")


if __name__ == "__main__":
    asyncio.run(main())
