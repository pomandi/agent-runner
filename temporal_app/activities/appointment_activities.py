"""
Appointment Collection Activities - Database operations for appointment data.
"""
from temporalio import activity
import asyncpg
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import Counter

# Database configuration
DB_HOST = os.getenv("AFSPRAAK_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("AFSPRAAK_DB_PORT", "5432"))
DB_USER = os.getenv("AFSPRAAK_DB_USER", "postgres")
DB_PASSWORD = os.getenv("AFSPRAAK_DB_PASSWORD", "9h3qp2d99jlkKl")
DB_NAME = os.getenv("AFSPRAAK_DB_NAME", "afspraak_db")

# Agent outputs database (for saving reports)
OUTPUT_DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
OUTPUT_DB_PORT = int(os.getenv("DB_PORT", "5433"))
OUTPUT_DB_USER = os.getenv("DB_USER", "postgres")
OUTPUT_DB_PASSWORD = os.getenv("DB_PASSWORD", "dXn0xUUpebj1ooW9nI0gJMQJMrJloLaVexQkDm8XvWN6CYNwd3JMXiVUuBcgqr4m")
OUTPUT_DB_NAME = os.getenv("DB_NAME", "postgres")


@activity.defn
async def collect_appointments(days: int) -> Dict[str, Any]:
    """
    Collect appointments from afspraak database.

    Args:
        days: Number of days to look back

    Returns:
        Dictionary with total count and appointment list
    """
    activity.logger.info(f"📊 Connecting to afspraak database to collect last {days} days...")

    conn = None
    try:
        # Connect to afspraak database
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )

        activity.logger.info("✅ Database connection established")

        # Query appointments from last N days
        query = """
            SELECT
                id,
                first_name,
                last_name,
                email,
                phone,
                appointment_date,
                appointment_time,
                service,
                status,
                source,
                notes,
                gclid,
                fbclid,
                utm_source,
                utm_medium,
                utm_campaign,
                visitor_id,
                session_id,
                created_at,
                updated_at
            FROM appointments
            WHERE created_at >= NOW() - INTERVAL '%s days'
            ORDER BY created_at DESC
        """ % days

        rows = await conn.fetch(query)

        activity.logger.info(f"✅ Found {len(rows)} appointments")

        # Convert to list of dicts
        appointments = []
        for row in rows:
            appointments.append({
                "id": row["id"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "email": row["email"],
                "phone": row["phone"],
                "appointment_date": row["appointment_date"].isoformat() if row["appointment_date"] else None,
                "appointment_time": str(row["appointment_time"]) if row["appointment_time"] else None,
                "service": row["service"],
                "status": row["status"],
                "source": row["source"],
                "notes": row["notes"],
                "gclid": row["gclid"],
                "fbclid": row["fbclid"],
                "utm_source": row["utm_source"],
                "utm_medium": row["utm_medium"],
                "utm_campaign": row["utm_campaign"],
                "visitor_id": row["visitor_id"],
                "session_id": row["session_id"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            })

        return {
            "total": len(appointments),
            "appointments": appointments,
            "query_date": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        activity.logger.error(f"❌ Database error: {e}")
        raise
    finally:
        if conn:
            await conn.close()
            activity.logger.info("🔌 Database connection closed")


@activity.defn
async def analyze_appointments(appointments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze appointment data to extract insights.

    Args:
        appointments: List of appointment dictionaries

    Returns:
        Analysis results with statistics
    """
    activity.logger.info(f"🔍 Analyzing {len(appointments)} appointments...")

    if not appointments:
        return {
            "total_appointments": 0,
            "total_conversions": 0,
            "sources": {},
            "top_source": None,
            "utm_campaigns": {},
            "google_ads_conversions": 0,
            "meta_ads_conversions": 0,
            "organic_conversions": 0,
        }

    # Count sources
    sources = Counter(apt.get("source") for apt in appointments if apt.get("source"))

    # Count UTM campaigns
    utm_campaigns = Counter(apt.get("utm_campaign") for apt in appointments if apt.get("utm_campaign"))

    # Count conversions by type
    google_ads = sum(1 for apt in appointments if apt.get("gclid"))
    meta_ads = sum(1 for apt in appointments if apt.get("fbclid"))

    # Count status
    confirmed = sum(1 for apt in appointments if apt.get("status") == "confirmed")
    pending = sum(1 for apt in appointments if apt.get("status") == "pending")
    cancelled = sum(1 for apt in appointments if apt.get("status") == "cancelled")

    analysis = {
        "total_appointments": len(appointments),
        "total_conversions": confirmed,
        "pending": pending,
        "cancelled": cancelled,
        "sources": dict(sources.most_common()),
        "top_source": sources.most_common(1)[0][0] if sources else None,
        "utm_campaigns": dict(utm_campaigns.most_common(10)),
        "google_ads_conversions": google_ads,
        "meta_ads_conversions": meta_ads,
        "organic_conversions": len(appointments) - google_ads - meta_ads,
        "conversion_rate": f"{(confirmed / len(appointments) * 100):.1f}%" if appointments else "0%",
    }

    activity.logger.info(f"✅ Analysis complete: {confirmed} conversions from {len(appointments)} appointments")

    return analysis


@activity.defn
async def save_appointment_report(
    days: int,
    total: int,
    appointments: List[Dict[str, Any]],
    analysis: Dict[str, Any]
) -> int:
    """
    Save appointment collection report to agent_outputs database.

    Args:
        days: Number of days collected
        total: Total appointments
        appointments: Full appointment list
        analysis: Analysis results

    Returns:
        Report ID from database
    """
    activity.logger.info("💾 Saving appointment report to agent_outputs...")

    conn = None
    try:
        # Connect to agent_outputs database
        conn = await asyncpg.connect(
            host=OUTPUT_DB_HOST,
            port=OUTPUT_DB_PORT,
            user=OUTPUT_DB_USER,
            password=OUTPUT_DB_PASSWORD,
            database=OUTPUT_DB_NAME,
        )

        # Build report content
        content = f"""# Appointment Collection Report

## Summary
- **Period:** Last {days} days
- **Total Appointments:** {total}
- **Confirmed:** {analysis['total_conversions']}
- **Pending:** {analysis['pending']}
- **Cancelled:** {analysis['cancelled']}
- **Conversion Rate:** {analysis['conversion_rate']}

## Traffic Sources
- **Google Ads:** {analysis['google_ads_conversions']} appointments
- **Meta Ads:** {analysis['meta_ads_conversions']} appointments
- **Organic/Other:** {analysis['organic_conversions']} appointments

## Top Sources
{chr(10).join(f"- {source}: {count}" for source, count in list(analysis['sources'].items())[:5])}

## Top Campaigns
{chr(10).join(f"- {campaign}: {count}" for campaign, count in list(analysis['utm_campaigns'].items())[:5])}

## Data
Total {total} appointments collected and analyzed.
"""

        # Insert to database
        query = """
            INSERT INTO agent_outputs
            (agent_name, output_type, content, title, tags, metadata)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """

        report_id = await conn.fetchval(
            query,
            "appointment-collector",
            "report",
            content,
            f"Appointment Report - Last {days} Days",
            ["appointments", "analytics", f"last-{days}-days"],
            json.dumps({
                "days": days,
                "total_appointments": total,
                "conversions": analysis['total_conversions'],
                "google_ads": analysis['google_ads_conversions'],
                "meta_ads": analysis['meta_ads_conversions'],
            })
        )

        activity.logger.info(f"✅ Report saved with ID: {report_id}")

        return report_id

    except Exception as e:
        activity.logger.error(f"❌ Failed to save report: {e}")
        raise
    finally:
        if conn:
            await conn.close()
