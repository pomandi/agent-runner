#!/usr/bin/env python3
"""
MyParcel MCP Server
Pomandi gönderileri için MyParcel API entegrasyonu
"""

import os
import base64
import requests
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("myparcel")

# API Configuration
API_KEY = os.environ.get("MYPARCEL_API_KEY", "")
BASE_URL = "https://api.myparcel.nl"

# Carrier IDs
CARRIERS = {
    "postnl": 1,
    "bpost": 2,
    "dpd": 4,
    "instabox": 5,
    "ups": 8
}

# Package types
PACKAGE_TYPES = {
    "package": 1,
    "mailbox": 2,
    "letter": 3,
    "digital_stamp": 4,
    "small_package": 6
}

def get_headers():
    """Get API headers with encoded key"""
    encoded_key = base64.b64encode(API_KEY.encode()).decode()
    return {
        "Authorization": f"bearer {encoded_key}",
        "User-Agent": "CustomApiCall/2",
        "Content-Type": "application/vnd.shipment+json;charset=utf-8;version=1.1"
    }


@mcp.tool()
def create_shipment(
    person: str,
    street: str,
    number: str,
    postal_code: str,
    city: str,
    country_code: str = "BE",
    email: Optional[str] = None,
    phone: Optional[str] = None,
    label_description: Optional[str] = None,
    weight: Optional[int] = None,
    custom_insurance: Optional[int] = None,
    custom_signature: Optional[bool] = None
) -> dict:
    """
    Create a MyParcel shipment for Pomandi. Uses bpost carrier.

    Country-specific defaults:
    - BE (Belgium): No insurance, no signature, 1000g weight
    - NL/EU: 500 EUR insurance, signature required, 50g weight

    Args:
        person: Recipient full name
        street: Street name
        number: House number
        postal_code: Postal code
        city: City name
        country_code: Country code (BE, NL, DE, etc.). Default: BE
        email: Recipient email (optional)
        phone: Recipient phone (optional)
        label_description: Label text - order number or product (optional)
        weight: Weight in grams (optional, uses country default)
        custom_insurance: Custom insurance in cents (optional, uses country default)
        custom_signature: Force signature requirement (optional, uses country default)

    Returns:
        Shipment creation result with shipment_id on success
    """
    if not API_KEY:
        return {"success": False, "error": "MYPARCEL_API_KEY not configured"}

    # Country-specific defaults
    if country_code == "BE":
        default_insurance = 0
        default_signature = False
        default_weight = 1000
    else:  # NL and other EU countries
        default_insurance = 50000  # 500 EUR
        default_signature = True
        default_weight = 50

    # Use custom values or defaults
    insurance = custom_insurance if custom_insurance is not None else default_insurance
    signature = custom_signature if custom_signature is not None else default_signature
    final_weight = weight if weight is not None else default_weight

    # Recipient data
    recipient = {
        "cc": country_code,
        "person": person,
        "street": street,
        "number": number,
        "postal_code": postal_code,
        "city": city
    }

    if email:
        recipient["email"] = email
    if phone:
        recipient["phone"] = phone

    # Shipment options
    options = {
        "package_type": 1,
        "delivery_type": 2,
        "drop_off_at_postal_point": 1
    }

    if insurance > 0:
        options["insurance"] = {"amount": insurance, "currency": "EUR"}
    if signature:
        options["signature"] = 1
    if label_description:
        options["label_description"] = label_description

    # Shipment data
    shipment = {
        "recipient": recipient,
        "options": options,
        "carrier": 2,  # bpost
        "physical_properties": {"weight": final_weight}
    }

    payload = {
        "data": {
            "shipments": [shipment]
        }
    }

    try:
        response = requests.post(
            f"{BASE_URL}/shipments",
            headers=get_headers(),
            json=payload
        )

        if response.status_code == 200:
            result = {
                "success": True,
                "data": response.json(),
                "status_code": response.status_code
            }
            # Extract shipment ID
            ids = result["data"].get("data", {}).get("ids", [])
            if ids:
                result["shipment_id"] = ids[0]["id"]
            return result
        else:
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def create_be_shipment(
    person: str,
    street: str,
    number: str,
    postal_code: str,
    city: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    label: Optional[str] = None
) -> dict:
    """
    Quick Belgium shipment (no insurance, no signature).

    Args:
        person: Recipient full name
        street: Street name
        number: House number
        postal_code: Postal code
        city: City name
        email: Recipient email (optional)
        phone: Recipient phone (optional)
        label: Label description - order number or product (optional)

    Returns:
        Shipment creation result
    """
    return create_shipment(
        person=person,
        street=street,
        number=number,
        postal_code=postal_code,
        city=city,
        country_code="BE",
        email=email,
        phone=phone,
        label_description=label
    )


@mcp.tool()
def create_nl_shipment(
    person: str,
    street: str,
    number: str,
    postal_code: str,
    city: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    label: Optional[str] = None
) -> dict:
    """
    Quick Netherlands shipment (500 EUR insurance + signature).

    Args:
        person: Recipient full name
        street: Street name
        number: House number
        postal_code: Postal code
        city: City name
        email: Recipient email (optional)
        phone: Recipient phone (optional)
        label: Label description - order number or product (optional)

    Returns:
        Shipment creation result
    """
    return create_shipment(
        person=person,
        street=street,
        number=number,
        postal_code=postal_code,
        city=city,
        country_code="NL",
        email=email,
        phone=phone,
        label_description=label
    )


@mcp.tool()
def create_eu_shipment(
    person: str,
    street: str,
    number: str,
    postal_code: str,
    city: str,
    country_code: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    label: Optional[str] = None
) -> dict:
    """
    Quick EU shipment (500 EUR insurance + signature).

    Args:
        person: Recipient full name
        street: Street name
        number: House number
        postal_code: Postal code
        city: City name
        country_code: Country code (DE, EE, FR, etc.)
        email: Recipient email (optional)
        phone: Recipient phone (optional)
        label: Label description - order number or product (optional)

    Returns:
        Shipment creation result
    """
    return create_shipment(
        person=person,
        street=street,
        number=number,
        postal_code=postal_code,
        city=city,
        country_code=country_code,
        email=email,
        phone=phone,
        label_description=label
    )


@mcp.tool()
def get_shipments(size: int = 10) -> dict:
    """
    Get recent shipments list.

    Args:
        size: Number of shipments to retrieve. Default: 10

    Returns:
        List of recent shipments
    """
    if not API_KEY:
        return {"success": False, "error": "MYPARCEL_API_KEY not configured"}

    try:
        response = requests.get(
            f"{BASE_URL}/shipments",
            headers=get_headers(),
            params={"size": size}
        )

        if response.status_code == 200:
            data = response.json()
            shipments = data.get("data", {}).get("shipments", [])

            # Simplify output
            simplified = []
            for s in shipments:
                simplified.append({
                    "id": s.get("id"),
                    "barcode": s.get("barcode"),
                    "status": s.get("status"),
                    "recipient": {
                        "person": s.get("recipient", {}).get("person"),
                        "city": s.get("recipient", {}).get("city"),
                        "country": s.get("recipient", {}).get("cc")
                    },
                    "created": s.get("created")
                })

            return {
                "success": True,
                "count": len(simplified),
                "shipments": simplified
            }
        else:
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_shipment(shipment_id: int) -> dict:
    """
    Get shipment details by ID.

    Args:
        shipment_id: MyParcel shipment ID

    Returns:
        Shipment details including status and tracking
    """
    if not API_KEY:
        return {"success": False, "error": "MYPARCEL_API_KEY not configured"}

    try:
        response = requests.get(
            f"{BASE_URL}/shipments/{shipment_id}",
            headers=get_headers()
        )

        if response.status_code == 200:
            data = response.json()
            shipments = data.get("data", {}).get("shipments", [])

            if shipments:
                s = shipments[0]
                return {
                    "success": True,
                    "shipment": {
                        "id": s.get("id"),
                        "barcode": s.get("barcode"),
                        "status": s.get("status"),
                        "recipient": s.get("recipient"),
                        "options": s.get("options"),
                        "carrier": s.get("carrier_id"),
                        "created": s.get("created"),
                        "modified": s.get("modified"),
                        "price": s.get("price")
                    }
                }
            else:
                return {"success": False, "error": "Shipment not found"}
        else:
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_shipment_label(shipment_id: int, format: str = "A6") -> dict:
    """
    Get shipment label PDF URL info.

    Note: This returns label info. To download PDF, use the MyParcel dashboard
    or call the label endpoint directly.

    Args:
        shipment_id: MyParcel shipment ID
        format: Label format - A4 or A6. Default: A6

    Returns:
        Label availability info
    """
    if not API_KEY:
        return {"success": False, "error": "MYPARCEL_API_KEY not configured"}

    label_headers = get_headers()
    label_headers["Accept"] = "application/pdf"
    label_headers["Content-Type"] = "application/json"

    try:
        response = requests.get(
            f"{BASE_URL}/shipment_labels/{shipment_id}",
            headers=label_headers,
            params={"format": format}
        )

        if response.status_code == 200:
            return {
                "success": True,
                "message": f"Label available for shipment {shipment_id}",
                "format": format,
                "download_url": f"https://api.myparcel.nl/shipment_labels/{shipment_id}?format={format}",
                "note": "Use MyParcel dashboard to download or print the label"
            }
        else:
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def delete_shipment(shipment_id: int) -> dict:
    """
    Delete a shipment.

    Args:
        shipment_id: MyParcel shipment ID to delete

    Returns:
        Deletion result
    """
    if not API_KEY:
        return {"success": False, "error": "MYPARCEL_API_KEY not configured"}

    try:
        response = requests.delete(
            f"{BASE_URL}/shipments/{shipment_id}",
            headers=get_headers()
        )

        if response.status_code in [200, 204]:
            return {
                "success": True,
                "message": f"Shipment {shipment_id} deleted successfully"
            }
        else:
            return {
                "success": False,
                "error": response.text,
                "status_code": response.status_code
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_shipping_standards() -> dict:
    """
    Get Pomandi shipping standards and rules.

    Returns:
        Shipping standards by country including insurance, signature, and weight defaults
    """
    return {
        "carrier": "bpost (carrier_id: 2)",
        "countries": {
            "BE": {
                "name": "Belgium",
                "insurance": "None",
                "signature": False,
                "default_weight": "1000g",
                "example_price": "6.83 - 8.15 EUR"
            },
            "NL": {
                "name": "Netherlands",
                "insurance": "500 EUR",
                "signature": True,
                "default_weight": "50g",
                "example_price": "10.55 - 11.80 EUR"
            },
            "EU": {
                "name": "Other EU Countries",
                "insurance": "500 EUR",
                "signature": True,
                "default_weight": "50g",
                "example_price": "~39 EUR (varies)"
            }
        },
        "label_formats": {
            "shopify_orders": "#10641 (order number)",
            "manual_shipments": "Product description or order ref"
        },
        "notes": [
            "All shipments use bpost carrier",
            "Track & Trace emails sent from info@pomandi.com",
            "API v1.1 - sender info configured in backoffice"
        ]
    }


if __name__ == "__main__":
    mcp.run()
