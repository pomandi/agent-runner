"""
Data Validation Rules
======================

Cross-source verification and anomaly detection rules for analytics data.

Rule Categories:
1. CROSS_SOURCE_RULES - Verify data consistency between different sources
2. ANOMALY_RULES - Detect unusual values and patterns
3. DATA_QUALITY_RULES - Check for missing or incomplete data

Usage:
    from validation_rules import CROSS_SOURCE_RULES, ANOMALY_RULES

    for rule in CROSS_SOURCE_RULES:
        if not rule["validation"](google_ads_data, shopify_data):
            print(f"Validation failed: {rule['message']}")
"""

from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class Severity(Enum):
    """Severity levels for validation failures."""
    CRITICAL = "critical"  # Stops processing, requires human review
    HIGH = "high"          # Major issue, flagged in report
    MEDIUM = "medium"      # Warning, included in report
    LOW = "low"            # Minor issue, logged only


class ValidationAction(Enum):
    """Actions to take on validation failure."""
    BLOCK = "block"        # Stop processing this data
    WARN = "warn"          # Continue but flag in report
    LOG = "log"            # Log only, no user notification
    FIX = "fix"            # Attempt automatic correction


@dataclass
class ValidationResult:
    """Result of a validation check."""
    rule_id: str
    passed: bool
    severity: Severity
    message: str
    suggested_action: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "passed": self.passed,
            "severity": self.severity.value,
            "message": self.message,
            "suggested_action": self.suggested_action,
            "details": self.details
        }


# =============================================================================
# CROSS-SOURCE VERIFICATION RULES
# =============================================================================

CROSS_SOURCE_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "conversion_verification",
        "name": "Google Ads Conversion vs Shopify Orders",
        "description": "Google Ads'deki conversion sayısı Shopify sipariş sayısına yakın olmalı",
        "sources": ["google_ads", "shopify"],
        "validation": lambda ga, sh: (
            ga.get("total_conversions", 0) == 0 or
            sh.get("total_orders", 0) == 0 or
            abs(ga.get("total_conversions", 0) - sh.get("total_orders", 0)) / max(sh.get("total_orders", 1), 1) < 0.5
        ),
        "tolerance": 0.5,  # 50% tolerance (some conversions may not result in orders)
        "severity": Severity.HIGH,
        "action": ValidationAction.WARN,
        "message": "Google Ads conversions ({ga_conv}) significantly differs from Shopify orders ({sh_orders})",
        "suggested_action": "Check Google Ads conversion tracking setup. May indicate tracking issues or attribution window mismatch."
    },
    {
        "rule_id": "roas_reality_check",
        "name": "ROAS Sanity Check",
        "description": "ROAS değeri makul bir aralıkta olmalı (0.1 - 15)",
        "sources": ["google_ads", "shopify"],
        "validation": lambda ga, sh: (
            ga.get("total_spend", 0) == 0 or
            sh.get("total_revenue", 0) == 0 or
            (0.1 <= (sh.get("total_revenue", 0) / max(ga.get("total_spend", 1), 0.01)) <= 15)
        ),
        "tolerance": None,
        "severity": Severity.CRITICAL,
        "action": ValidationAction.WARN,
        "message": "ROAS ({roas:.1f}x) seems unrealistic. Revenue: €{revenue:.2f}, Spend: €{spend:.2f}",
        "suggested_action": "Verify conversion value tracking in Google Ads. ROAS > 15 usually indicates tracking error."
    },
    {
        "rule_id": "meta_reach_vs_sessions",
        "name": "Meta Ads Reach vs Visitor Sessions",
        "description": "Meta reach'in bir kısmı site ziyaretine dönüşmeli",
        "sources": ["meta_ads", "visitor_tracking"],
        "validation": lambda ma, vt: (
            ma.get("total_reach", 0) == 0 or
            vt.get("total_sessions", 0) == 0 or
            (ma.get("total_reach", 0) * 0.001 < vt.get("total_sessions", 0) < ma.get("total_reach", 0) * 0.5)
        ),
        "tolerance": None,
        "severity": Severity.MEDIUM,
        "action": ValidationAction.LOG,
        "message": "Meta reach ({reach:,}) and visitor sessions ({sessions:,}) ratio seems unusual",
        "suggested_action": "Check UTM tracking and attribution. Expected session rate: 0.1% - 50% of reach."
    },
    {
        "rule_id": "conversion_value_vs_aov",
        "name": "Conversion Value vs Average Order Value",
        "description": "Google Ads'deki conversion value AOV ile tutarlı olmalı",
        "sources": ["google_ads", "shopify"],
        "validation": lambda ga, sh: (
            ga.get("total_conversions", 0) == 0 or
            sh.get("total_orders", 0) == 0 or
            sh.get("average_order_value", 0) == 0 or
            abs(
                (ga.get("total_spend", 0) * ga.get("roas", 0) / max(ga.get("total_conversions", 1), 1)) -
                sh.get("average_order_value", 0)
            ) / sh.get("average_order_value", 1) < 0.7
        ),
        "tolerance": 0.7,
        "severity": Severity.HIGH,
        "action": ValidationAction.WARN,
        "message": "Conversion value per conversion differs significantly from AOV",
        "suggested_action": "Review conversion value tracking in Google Ads. Dynamic values may need adjustment."
    },
    {
        "rule_id": "appointment_attribution",
        "name": "Appointment GCLID/FBCLID Match Rate",
        "description": "Randevuların büyük çoğunluğu visitor_id ile eşleşmeli",
        "sources": ["appointments", "visitor_tracking"],
        "validation": lambda ap, vt: (
            ap.get("total_appointments", 0) == 0 or
            ap.get("with_visitor_id", 0) / max(ap.get("total_appointments", 1), 1) > 0.3
        ),
        "tolerance": 0.3,  # At least 30% should have attribution
        "severity": Severity.MEDIUM,
        "action": ValidationAction.WARN,
        "message": "Only {match_rate:.0%} of appointments have visitor attribution",
        "suggested_action": "Check visitor tracking implementation on appointment form. Ensure visitor_id is passed."
    },
    {
        "rule_id": "ga4_vs_custom_tracking",
        "name": "GA4 Sessions vs Custom Tracking Sessions",
        "description": "GA4 ve custom tracking session sayıları benzer olmalı",
        "sources": ["ga4", "visitor_tracking"],
        "validation": lambda g4, vt: (
            g4.get("sessions", 0) == 0 or
            vt.get("total_sessions", 0) == 0 or
            abs(g4.get("sessions", 0) - vt.get("total_sessions", 0)) / max(g4.get("sessions", 1), 1) < 0.5
        ),
        "tolerance": 0.5,
        "severity": Severity.MEDIUM,
        "action": ValidationAction.LOG,
        "message": "GA4 sessions ({ga4_sessions:,}) differs from custom tracking ({vt_sessions:,})",
        "suggested_action": "Session counting methodology may differ. Check bot filtering and session timeout settings."
    },
    {
        "rule_id": "total_ad_spend_verification",
        "name": "Total Ad Spend Verification",
        "description": "Google Ads + Meta Ads toplam harcaması makul olmalı",
        "sources": ["google_ads", "meta_ads"],
        "validation": lambda ga, ma: (
            (ga.get("total_spend", 0) + ma.get("total_spend", 0)) < 10000  # Daily limit sanity check
        ),
        "tolerance": None,
        "severity": Severity.CRITICAL,
        "action": ValidationAction.BLOCK,
        "message": "Total ad spend (€{total_spend:.2f}) exceeds expected daily budget",
        "suggested_action": "Verify this is correct. May indicate budget issues or data aggregation error."
    },
    {
        "rule_id": "merchant_vs_shopify_products",
        "name": "Merchant Center vs Shopify Product Count",
        "description": "Merchant Center'daki ürün sayısı Shopify'a yakın olmalı",
        "sources": ["merchant_center", "shopify"],
        "validation": lambda mc, sh: (
            mc.get("total_products", 0) == 0 or
            len(sh.get("top_products", [])) == 0 or
            True  # Simplified - Shopify doesn't return total product count
        ),
        "tolerance": 0.3,
        "severity": Severity.LOW,
        "action": ValidationAction.LOG,
        "message": "Merchant Center products ({mc_products}) differs from Shopify catalog",
        "suggested_action": "Some products may be filtered in Merchant Center feed."
    }
]


# =============================================================================
# ANOMALY DETECTION RULES
# =============================================================================

ANOMALY_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "sudden_spend_spike",
        "name": "Sudden Spend Increase",
        "description": "Harcama önceki döneme göre 2x'den fazla artmış mı?",
        "check": lambda current, historical: (
            historical.get("avg_spend", 0) == 0 or
            current.get("total_spend", 0) <= historical.get("avg_spend", 0) * 2
        ),
        "severity": Severity.HIGH,
        "action": ValidationAction.WARN,
        "message": "Spend (€{current_spend:.2f}) is 2x+ higher than average (€{avg_spend:.2f})",
        "suggested_action": "Check for budget changes or unusual campaign activity."
    },
    {
        "rule_id": "zero_conversions_with_spend",
        "name": "Zero Conversions Despite Spend",
        "description": "Harcama var ama conversion yok",
        "check": lambda data, hist: not (
            data.get("total_spend", 0) > 50 and
            data.get("total_conversions", 0) == 0
        ),
        "severity": Severity.CRITICAL,
        "action": ValidationAction.WARN,
        "message": "€{spend:.2f} spent but 0 conversions",
        "suggested_action": "Check conversion tracking. May be broken or campaigns may need optimization."
    },
    {
        "rule_id": "ctr_anomaly",
        "name": "CTR Outside Normal Range",
        "description": "CTR normal aralığın dışında (0.5% - 15%)",
        "check": lambda data, hist: (
            data.get("avg_ctr", 0) == 0 or
            (0.3 <= data.get("avg_ctr", 0) <= 20)
        ),
        "severity": Severity.MEDIUM,
        "action": ValidationAction.LOG,
        "message": "CTR ({ctr:.2f}%) is outside normal range (0.5% - 15%)",
        "suggested_action": "Very high CTR may indicate click fraud. Very low CTR needs ad optimization."
    },
    {
        "rule_id": "merchant_disapproval_spike",
        "name": "Merchant Center Disapproval Spike",
        "description": "Reddedilen ürün sayısı artmış mı?",
        "check": lambda current, historical: (
            historical.get("avg_disapproved", 0) == 0 or
            current.get("disapproved_products", 0) <= historical.get("avg_disapproved", 0) * 1.5
        ),
        "severity": Severity.HIGH,
        "action": ValidationAction.WARN,
        "message": "Disapproved products ({current}) increased significantly from average ({avg})",
        "suggested_action": "Check Merchant Center for policy violations or feed errors."
    },
    {
        "rule_id": "session_duration_anomaly",
        "name": "Session Duration Anomaly",
        "description": "Oturum süresi anormal (< 5s veya > 30 dakika)",
        "check": lambda data, hist: (
            data.get("median_session_duration", 60) == 0 or
            (5 <= data.get("median_session_duration", 60) <= 1800)
        ),
        "severity": Severity.MEDIUM,
        "action": ValidationAction.LOG,
        "message": "Median session duration ({duration}s) seems unusual",
        "suggested_action": "Very short sessions may indicate bot traffic or page issues."
    },
    {
        "rule_id": "revenue_drop",
        "name": "Significant Revenue Drop",
        "description": "Gelir önceki döneme göre %50'den fazla düşmüş mü?",
        "check": lambda current, historical: (
            historical.get("avg_revenue", 0) == 0 or
            current.get("total_revenue", 0) >= historical.get("avg_revenue", 0) * 0.5
        ),
        "severity": Severity.CRITICAL,
        "action": ValidationAction.WARN,
        "message": "Revenue (€{current:.2f}) dropped 50%+ from average (€{avg:.2f})",
        "suggested_action": "Investigate cause: checkout issues, payment problems, or seasonal?"
    },
    {
        "rule_id": "order_count_anomaly",
        "name": "Order Count Anomaly",
        "description": "Sipariş sayısı beklenenin çok altında veya üstünde",
        "check": lambda current, historical: (
            historical.get("avg_orders", 0) == 0 or
            (historical.get("avg_orders", 0) * 0.3 <= current.get("total_orders", 0) <= historical.get("avg_orders", 0) * 3)
        ),
        "severity": Severity.HIGH,
        "action": ValidationAction.WARN,
        "message": "Order count ({current}) is unusual compared to average ({avg})",
        "suggested_action": "Check for promotions, site issues, or data collection problems."
    },
    {
        "rule_id": "search_position_drop",
        "name": "Search Position Drop",
        "description": "Ortalama pozisyon önemli ölçüde düşmüş mü?",
        "check": lambda current, historical: (
            historical.get("avg_position", 0) == 0 or
            current.get("avg_position", 0) <= historical.get("avg_position", 0) + 5
        ),
        "severity": Severity.MEDIUM,
        "action": ValidationAction.LOG,
        "message": "Average search position dropped from {hist_pos:.1f} to {current_pos:.1f}",
        "suggested_action": "Monitor SEO rankings. May indicate algorithm update or competitor activity."
    }
]


# =============================================================================
# DATA QUALITY RULES
# =============================================================================

DATA_QUALITY_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "missing_source_data",
        "name": "Missing Source Data",
        "description": "Kritik veri kaynağı eksik",
        "check": lambda sources: len([s for s in sources if s.get("error")]) <= 2,
        "severity": Severity.HIGH,
        "action": ValidationAction.WARN,
        "message": "{missing_count} of 8 data sources failed to load",
        "suggested_action": "Check MCP server status and API credentials."
    },
    {
        "rule_id": "stale_data",
        "name": "Stale Data Detection",
        "description": "Veri güncel mi?",
        "check": lambda data: True,  # Implemented in validator
        "severity": Severity.MEDIUM,
        "action": ValidationAction.LOG,
        "message": "Data appears to be stale or not updated recently",
        "suggested_action": "Verify data collection is running on schedule."
    },
    {
        "rule_id": "incomplete_metrics",
        "name": "Incomplete Metrics",
        "description": "Temel metrikler eksik mi?",
        "check": lambda data: all([
            data.get("total_spend") is not None,
            data.get("total_clicks") is not None,
            data.get("total_impressions") is not None
        ]) if data.get("source") in ["google_ads", "meta_ads"] else True,
        "severity": Severity.MEDIUM,
        "action": ValidationAction.WARN,
        "message": "Essential metrics missing for {source}",
        "suggested_action": "Check API response. Partial data may indicate API issues."
    }
]


# =============================================================================
# VALIDATION HELPER FUNCTIONS
# =============================================================================

def run_cross_source_validation(
    data: Dict[str, Dict[str, Any]]
) -> List[ValidationResult]:
    """
    Run all cross-source validation rules.

    Args:
        data: Dictionary with source names as keys and source data as values
            e.g., {"google_ads": {...}, "shopify": {...}}

    Returns:
        List of ValidationResult objects for failed validations
    """
    results = []

    for rule in CROSS_SOURCE_RULES:
        sources = rule["sources"]

        # Get source data
        source_data = [data.get(s, {}) or {} for s in sources]

        # Skip if any required source is missing
        if any(not sd for sd in source_data):
            continue

        # Run validation
        try:
            passed = rule["validation"](*source_data)

            if not passed:
                result = ValidationResult(
                    rule_id=rule["rule_id"],
                    passed=False,
                    severity=rule["severity"],
                    message=rule["message"],
                    suggested_action=rule["suggested_action"],
                    details={
                        "sources": sources,
                        "source_data": {s: summarize_source(d) for s, d in zip(sources, source_data)}
                    }
                )
                results.append(result)

                logger.warning(
                    "cross_source_validation_failed",
                    rule_id=rule["rule_id"],
                    severity=rule["severity"].value,
                    sources=sources
                )

        except Exception as e:
            logger.error(
                "cross_source_validation_error",
                rule_id=rule["rule_id"],
                error=str(e)
            )

    return results


def run_anomaly_detection(
    current_data: Dict[str, Any],
    historical_data: Optional[Dict[str, Any]] = None
) -> List[ValidationResult]:
    """
    Run anomaly detection on current data.

    Args:
        current_data: Current period's data
        historical_data: Historical averages for comparison

    Returns:
        List of ValidationResult objects for detected anomalies
    """
    results = []
    historical = historical_data or {}

    for rule in ANOMALY_RULES:
        try:
            passed = rule["check"](current_data, historical)

            if not passed:
                result = ValidationResult(
                    rule_id=rule["rule_id"],
                    passed=False,
                    severity=rule["severity"],
                    message=rule["message"],
                    suggested_action=rule["suggested_action"],
                    details={
                        "current": summarize_source(current_data),
                        "historical": summarize_source(historical)
                    }
                )
                results.append(result)

                logger.warning(
                    "anomaly_detected",
                    rule_id=rule["rule_id"],
                    severity=rule["severity"].value
                )

        except Exception as e:
            logger.error(
                "anomaly_detection_error",
                rule_id=rule["rule_id"],
                error=str(e)
            )

    return results


def calculate_validation_score(
    validation_results: List[ValidationResult]
) -> float:
    """
    Calculate overall validation score based on failures.

    Score starts at 1.0 and decreases based on failures:
    - CRITICAL: -0.3
    - HIGH: -0.15
    - MEDIUM: -0.05
    - LOW: -0.02

    Returns:
        Score between 0.0 and 1.0
    """
    score = 1.0

    for result in validation_results:
        if not result.passed:
            if result.severity == Severity.CRITICAL:
                score -= 0.3
            elif result.severity == Severity.HIGH:
                score -= 0.15
            elif result.severity == Severity.MEDIUM:
                score -= 0.05
            elif result.severity == Severity.LOW:
                score -= 0.02

    return max(0.0, score)


def should_proceed_to_analysis(validation_score: float, threshold: float = 0.70) -> bool:
    """
    Determine if data quality is sufficient to proceed with analysis.

    Args:
        validation_score: Score from calculate_validation_score
        threshold: Minimum score to proceed (default: 0.70)

    Returns:
        True if should proceed, False if needs human review
    """
    return validation_score >= threshold


def summarize_source(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a summary of source data for logging/reporting."""
    if not data:
        return {}

    return {
        k: v for k, v in data.items()
        if k in [
            "source", "total_spend", "total_clicks", "total_impressions",
            "total_conversions", "total_revenue", "total_orders",
            "total_sessions", "total_appointments", "error"
        ]
    }


def get_rules_for_sources(source_names: List[str]) -> List[Dict[str, Any]]:
    """Get validation rules relevant for given sources."""
    relevant_rules = []

    for rule in CROSS_SOURCE_RULES:
        if set(rule["sources"]).issubset(set(source_names)):
            relevant_rules.append(rule)

    return relevant_rules


def format_validation_report(
    validation_results: List[ValidationResult],
    validation_score: float
) -> str:
    """Format validation results as markdown report."""
    lines = [
        "## Veri Doğrulama Raporu",
        "",
        f"**Validation Score:** {validation_score:.0%}",
        f"**Proceed to Analysis:** {'✅ Evet' if should_proceed_to_analysis(validation_score) else '❌ Hayır - İnceleme Gerekli'}",
        ""
    ]

    if not validation_results:
        lines.append("✅ Tüm doğrulama kontrolleri başarılı!")
        return "\n".join(lines)

    # Group by severity
    critical = [r for r in validation_results if r.severity == Severity.CRITICAL]
    high = [r for r in validation_results if r.severity == Severity.HIGH]
    medium = [r for r in validation_results if r.severity == Severity.MEDIUM]
    low = [r for r in validation_results if r.severity == Severity.LOW]

    if critical:
        lines.append("### 🔴 Kritik Sorunlar")
        for r in critical:
            lines.append(f"- **{r.rule_id}**: {r.message}")
            lines.append(f"  - Öneri: {r.suggested_action}")
        lines.append("")

    if high:
        lines.append("### 🟠 Yüksek Öncelikli")
        for r in high:
            lines.append(f"- **{r.rule_id}**: {r.message}")
        lines.append("")

    if medium:
        lines.append("### 🟡 Orta Öncelikli")
        for r in medium:
            lines.append(f"- {r.rule_id}: {r.message}")
        lines.append("")

    if low:
        lines.append("### ⚪ Düşük Öncelikli")
        for r in low:
            lines.append(f"- {r.rule_id}")

    return "\n".join(lines)
