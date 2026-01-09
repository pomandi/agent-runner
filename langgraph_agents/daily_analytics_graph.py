"""
Daily Analytics Report Graph
=============================

LangGraph implementation for daily analytics report generation.

Collects data from 8 sources:
1. Google Ads - Kampanya, keyword, conversion
2. Meta Ads - FB/IG kampanya, hedefleme
3. Custom Visitor Tracking - Sessions, events, conversions (PostgreSQL)
4. GA4 - Trafik, kullanici
5. Search Console - SEO, keyword pozisyon
6. Merchant Center - Urun performansi
7. Shopify - Siparis, gelir, musteri
8. Afspraak-DB - Randevu, GCLID/FBCLID attribution

Workflow:
1. Parallel data collection (8 sources)
2. Merge and validate data
3. Claude analysis (Turkish)
4. Generate insights & recommendations
5. Quality check (regenerate if low)
6. Format report (Markdown)
7. Send to Telegram

Schedule: Daily 08:00 UTC (10:00 Amsterdam)
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from langgraph.graph import StateGraph, END
import structlog
import time
import os
import asyncio
import asyncpg
import httpx

from .base_graph import BaseAgentGraph
from .state_schemas import DailyAnalyticsState, init_daily_analytics_state

# Import monitoring metrics
try:
    from monitoring.metrics import record_agent_execution
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

# Import Claude Agent SDK
try:
    from claude_agent_sdk import query, ClaudeAgentOptions
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

logger = structlog.get_logger(__name__)


class DailyAnalyticsGraph(BaseAgentGraph):
    """
    Daily analytics report generator with multi-source data collection.

    Flow:
        START
          |
        +--+--+--+--+--+--+--+--+  (Parallel)
        |  |  |  |  |  |  |  |
        v  v  v  v  v  v  v  v
       GA MA VT G4 SC MC SH AP
        |  |  |  |  |  |  |  |
        +--+--+--+--+--+--+--+--+
                  |
                  v
            merge_data
                  |
                  v
            analyze_funnel (Claude)
                  |
                  v
            generate_insights (Claude)
                  |
                  v
            quality_check
                  |
          +-------+-------+
          |               |
          v               v
        format       regenerate
        report          |
          |             |
          +---------+---+
                    |
                    v
            send_telegram
                    |
                    v
                  END

    Legend:
        GA = Google Ads
        MA = Meta Ads
        VT = Visitor Tracking (Custom DB)
        G4 = GA4
        SC = Search Console
        MC = Merchant Center
        SH = Shopify
        AP = Appointments (Afspraak-DB)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.regenerate_count = 0
        self.max_regenerate = 2

    def build_graph(self) -> StateGraph:
        """Build daily analytics graph."""
        graph = StateGraph(DailyAnalyticsState)

        # Add data collection nodes
        graph.add_node("fetch_google_ads", self.fetch_google_ads_node)
        graph.add_node("fetch_meta_ads", self.fetch_meta_ads_node)
        graph.add_node("fetch_visitor_tracking", self.fetch_visitor_tracking_node)
        graph.add_node("fetch_ga4", self.fetch_ga4_node)
        graph.add_node("fetch_search_console", self.fetch_search_console_node)
        graph.add_node("fetch_merchant", self.fetch_merchant_node)
        graph.add_node("fetch_shopify", self.fetch_shopify_node)
        graph.add_node("fetch_appointments", self.fetch_appointments_node)

        # Add processing nodes
        graph.add_node("merge_data", self.merge_data_node)
        graph.add_node("analyze_funnel", self.analyze_funnel_node)
        graph.add_node("generate_insights", self.generate_insights_node)
        graph.add_node("quality_check", self.quality_check_node)
        graph.add_node("format_report", self.format_report_node)
        graph.add_node("send_telegram", self.send_telegram_node)

        # Entry point - start with all data collectors in parallel
        # For LangGraph, we'll run them sequentially but could use asyncio.gather
        graph.set_entry_point("fetch_google_ads")

        # Sequential edges for data collection
        graph.add_edge("fetch_google_ads", "fetch_meta_ads")
        graph.add_edge("fetch_meta_ads", "fetch_visitor_tracking")
        graph.add_edge("fetch_visitor_tracking", "fetch_ga4")
        graph.add_edge("fetch_ga4", "fetch_search_console")
        graph.add_edge("fetch_search_console", "fetch_merchant")
        graph.add_edge("fetch_merchant", "fetch_shopify")
        graph.add_edge("fetch_shopify", "fetch_appointments")

        # After all data collected
        graph.add_edge("fetch_appointments", "merge_data")
        graph.add_edge("merge_data", "analyze_funnel")
        graph.add_edge("analyze_funnel", "generate_insights")
        graph.add_edge("generate_insights", "quality_check")

        # Conditional routing based on quality
        graph.add_conditional_edges(
            "quality_check",
            self.quality_router,
            {
                "format": "format_report",
                "regenerate": "analyze_funnel"  # Loop back
            }
        )

        graph.add_edge("format_report", "send_telegram")
        graph.add_edge("send_telegram", END)

        return graph

    # =========================================================================
    # DATA COLLECTION NODES (8 sources)
    # =========================================================================

    async def fetch_google_ads_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Google Ads campaign data via MCP."""
        try:
            days = state["days"]
            brand = state["brand"]

            # TODO: Use google-ads MCP server
            # For now, return mock data structure
            data = {
                "source": "google_ads",
                "period_days": days,
                "campaigns": [],
                "total_spend": 0.0,
                "total_clicks": 0,
                "total_conversions": 0,
                "top_keywords": [],
                "error": None
            }

            # Try to call MCP if available
            # mcp__google-ads__get_campaigns({"days": days, "brand": brand})

            state["google_ads_data"] = data
            state = self.add_step(state, "fetch_google_ads")

            logger.info("google_ads_fetched", days=days, brand=brand)

        except Exception as e:
            error_msg = f"Google Ads fetch failed: {str(e)}"
            state["google_ads_data"] = {"error": error_msg}
            state["errors"].append(error_msg)
            logger.error("google_ads_fetch_error", error=str(e))

        return state

    async def fetch_meta_ads_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Meta Ads (Facebook/Instagram) data via MCP."""
        try:
            days = state["days"]
            brand = state["brand"]

            data = {
                "source": "meta_ads",
                "period_days": days,
                "campaigns": [],
                "total_spend": 0.0,
                "total_reach": 0,
                "total_clicks": 0,
                "total_conversions": 0,
                "top_audiences": [],
                "error": None
            }

            # TODO: Use meta-ads MCP server

            state["meta_ads_data"] = data
            state = self.add_step(state, "fetch_meta_ads")

            logger.info("meta_ads_fetched", days=days, brand=brand)

        except Exception as e:
            error_msg = f"Meta Ads fetch failed: {str(e)}"
            state["meta_ads_data"] = {"error": error_msg}
            state["errors"].append(error_msg)
            logger.error("meta_ads_fetch_error", error=str(e))

        return state

    async def fetch_visitor_tracking_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """
        Fetch custom visitor tracking data from PostgreSQL.

        This is the BEST data source - our own tracking system!

        Tables:
        - visitors: Ziyaretci profilleri
        - sessions: UTM, GCLID, landing page, referrer
        - page_views: Sayfa goruntuleme + sure
        - events: Custom event tracking
        - conversions: Goal tamamlama
        - google_ads_clicks: GCLID ile reklam eslestirme
        - hourly_summaries: Onceden hesaplanmis saatlik ozet

        CRITICAL: Use MEDIAN for time metrics, not AVERAGE!
        """
        try:
            days = state["days"]
            brand = state["brand"]

            # Get DB connection from environment
            db_url = os.getenv("VISITOR_TRACKING_DATABASE_URL")

            if db_url:
                conn = await asyncpg.connect(db_url)

                try:
                    # Date range
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=days)

                    # Query sessions with UTM data
                    sessions_query = """
                        SELECT
                            COUNT(*) as total_sessions,
                            COUNT(DISTINCT visitor_id) as unique_visitors,
                            COUNT(CASE WHEN utm_source IS NOT NULL THEN 1 END) as utm_sessions,
                            COUNT(CASE WHEN gclid IS NOT NULL THEN 1 END) as gclid_sessions,
                            COUNT(CASE WHEN fbclid IS NOT NULL THEN 1 END) as fbclid_sessions,
                            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds) as median_session_duration
                        FROM sessions
                        WHERE created_at >= $1 AND created_at < $2
                    """
                    session_stats = await conn.fetchrow(sessions_query, start_date, end_date)

                    # Query conversions
                    conversions_query = """
                        SELECT
                            COUNT(*) as total_conversions,
                            goal_type,
                            COUNT(*) as count
                        FROM conversions
                        WHERE created_at >= $1 AND created_at < $2
                        GROUP BY goal_type
                    """
                    conversions = await conn.fetch(conversions_query, start_date, end_date)

                    # Query top landing pages
                    landing_pages_query = """
                        SELECT
                            landing_page,
                            COUNT(*) as sessions,
                            COUNT(DISTINCT visitor_id) as unique_visitors
                        FROM sessions
                        WHERE created_at >= $1 AND created_at < $2
                        GROUP BY landing_page
                        ORDER BY sessions DESC
                        LIMIT 10
                    """
                    top_landing_pages = await conn.fetch(landing_pages_query, start_date, end_date)

                    # Query traffic sources
                    traffic_sources_query = """
                        SELECT
                            COALESCE(utm_source, 'direct') as source,
                            COALESCE(utm_medium, 'none') as medium,
                            COUNT(*) as sessions
                        FROM sessions
                        WHERE created_at >= $1 AND created_at < $2
                        GROUP BY utm_source, utm_medium
                        ORDER BY sessions DESC
                        LIMIT 10
                    """
                    traffic_sources = await conn.fetch(traffic_sources_query, start_date, end_date)

                    data = {
                        "source": "visitor_tracking",
                        "period_days": days,
                        "total_sessions": session_stats["total_sessions"] if session_stats else 0,
                        "unique_visitors": session_stats["unique_visitors"] if session_stats else 0,
                        "utm_sessions": session_stats["utm_sessions"] if session_stats else 0,
                        "gclid_sessions": session_stats["gclid_sessions"] if session_stats else 0,
                        "fbclid_sessions": session_stats["fbclid_sessions"] if session_stats else 0,
                        "median_session_duration": float(session_stats["median_session_duration"]) if session_stats and session_stats["median_session_duration"] else 0,
                        "conversions": [dict(c) for c in conversions],
                        "top_landing_pages": [dict(p) for p in top_landing_pages],
                        "traffic_sources": [dict(s) for s in traffic_sources],
                        "error": None
                    }

                finally:
                    await conn.close()
            else:
                data = {
                    "source": "visitor_tracking",
                    "error": "Database URL not configured"
                }

            state["visitor_tracking_data"] = data
            state = self.add_step(state, "fetch_visitor_tracking")

            logger.info("visitor_tracking_fetched", days=days, sessions=data.get("total_sessions", 0))

        except Exception as e:
            error_msg = f"Visitor Tracking fetch failed: {str(e)}"
            state["visitor_tracking_data"] = {"error": error_msg}
            state["errors"].append(error_msg)
            logger.error("visitor_tracking_fetch_error", error=str(e))

        return state

    async def fetch_ga4_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Google Analytics 4 data via MCP."""
        try:
            days = state["days"]

            data = {
                "source": "ga4",
                "period_days": days,
                "total_users": 0,
                "new_users": 0,
                "sessions": 0,
                "page_views": 0,
                "avg_session_duration": 0,
                "bounce_rate": 0,
                "top_pages": [],
                "error": None
            }

            # TODO: Use analytics MCP server

            state["ga4_data"] = data
            state = self.add_step(state, "fetch_ga4")

            logger.info("ga4_fetched", days=days)

        except Exception as e:
            error_msg = f"GA4 fetch failed: {str(e)}"
            state["ga4_data"] = {"error": error_msg}
            state["errors"].append(error_msg)
            logger.error("ga4_fetch_error", error=str(e))

        return state

    async def fetch_search_console_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Search Console SEO data via MCP."""
        try:
            days = state["days"]

            data = {
                "source": "search_console",
                "period_days": days,
                "total_clicks": 0,
                "total_impressions": 0,
                "avg_ctr": 0,
                "avg_position": 0,
                "top_queries": [],
                "top_pages": [],
                "position_changes": [],
                "error": None
            }

            # TODO: Use search-console MCP server

            state["search_console_data"] = data
            state = self.add_step(state, "fetch_search_console")

            logger.info("search_console_fetched", days=days)

        except Exception as e:
            error_msg = f"Search Console fetch failed: {str(e)}"
            state["search_console_data"] = {"error": error_msg}
            state["errors"].append(error_msg)
            logger.error("search_console_fetch_error", error=str(e))

        return state

    async def fetch_merchant_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Google Merchant Center data via MCP."""
        try:
            days = state["days"]

            data = {
                "source": "merchant_center",
                "period_days": days,
                "total_products": 0,
                "approved_products": 0,
                "disapproved_products": 0,
                "total_clicks": 0,
                "total_impressions": 0,
                "top_products": [],
                "issues": [],
                "error": None
            }

            # TODO: Use merchant-center MCP server

            state["merchant_data"] = data
            state = self.add_step(state, "fetch_merchant")

            logger.info("merchant_fetched", days=days)

        except Exception as e:
            error_msg = f"Merchant Center fetch failed: {str(e)}"
            state["merchant_data"] = {"error": error_msg}
            state["errors"].append(error_msg)
            logger.error("merchant_fetch_error", error=str(e))

        return state

    async def fetch_shopify_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Shopify orders and revenue data via MCP."""
        try:
            days = state["days"]
            brand = state["brand"]

            data = {
                "source": "shopify",
                "period_days": days,
                "total_orders": 0,
                "total_revenue": 0.0,
                "average_order_value": 0.0,
                "new_customers": 0,
                "returning_customers": 0,
                "top_products": [],
                "abandoned_carts": 0,
                "error": None
            }

            # TODO: Use shopify MCP server

            state["shopify_data"] = data
            state = self.add_step(state, "fetch_shopify")

            logger.info("shopify_fetched", days=days, brand=brand)

        except Exception as e:
            error_msg = f"Shopify fetch failed: {str(e)}"
            state["shopify_data"] = {"error": error_msg}
            state["errors"].append(error_msg)
            logger.error("shopify_fetch_error", error=str(e))

        return state

    async def fetch_appointments_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch appointment data from Afspraak-DB via MCP."""
        try:
            days = state["days"]
            brand = state["brand"]

            data = {
                "source": "afspraak_db",
                "period_days": days,
                "total_appointments": 0,
                "confirmed_appointments": 0,
                "cancelled_appointments": 0,
                "no_shows": 0,
                "gclid_attributed": 0,
                "fbclid_attributed": 0,
                "conversion_rate": 0.0,
                "by_service": [],
                "error": None
            }

            # TODO: Use afspraak-db MCP server

            state["appointments_data"] = data
            state = self.add_step(state, "fetch_appointments")

            logger.info("appointments_fetched", days=days, brand=brand)

        except Exception as e:
            error_msg = f"Appointments fetch failed: {str(e)}"
            state["appointments_data"] = {"error": error_msg}
            state["errors"].append(error_msg)
            logger.error("appointments_fetch_error", error=str(e))

        return state

    # =========================================================================
    # PROCESSING NODES
    # =========================================================================

    async def merge_data_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Merge all collected data into unified structure."""
        try:
            merged = {
                "collection_timestamp": datetime.now().isoformat(),
                "period_days": state["days"],
                "brand": state["brand"],
                "sources": {
                    "google_ads": state.get("google_ads_data", {}),
                    "meta_ads": state.get("meta_ads_data", {}),
                    "visitor_tracking": state.get("visitor_tracking_data", {}),
                    "ga4": state.get("ga4_data", {}),
                    "search_console": state.get("search_console_data", {}),
                    "merchant_center": state.get("merchant_data", {}),
                    "shopify": state.get("shopify_data", {}),
                    "appointments": state.get("appointments_data", {})
                },
                "data_quality": {
                    "sources_with_data": 0,
                    "sources_with_errors": 0,
                    "missing_sources": []
                }
            }

            # Count data quality
            for source_name, source_data in merged["sources"].items():
                if source_data:
                    if source_data.get("error"):
                        merged["data_quality"]["sources_with_errors"] += 1
                    else:
                        merged["data_quality"]["sources_with_data"] += 1
                else:
                    merged["data_quality"]["missing_sources"].append(source_name)

            state["merged_data"] = merged
            state = self.add_step(state, "merge_data")

            logger.info(
                "data_merged",
                sources_with_data=merged["data_quality"]["sources_with_data"],
                sources_with_errors=merged["data_quality"]["sources_with_errors"]
            )

        except Exception as e:
            error_msg = f"Data merge failed: {str(e)}"
            state["errors"].append(error_msg)
            logger.error("merge_data_error", error=str(e))

        return state

    async def analyze_funnel_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze Ads -> Appointments -> Sales funnel using Claude."""
        try:
            merged_data = state.get("merged_data", {})

            # Build prompt for Claude analysis (Turkish)
            prompt = f"""Sen bir dijital pazarlama analistisin. Asagidaki verileri analiz et ve TURKCE olarak funnel analizi yap.

VERILER:
{self._format_data_for_prompt(merged_data)}

ANALIZ GEREKSINIMLERI:
1. Reklam Performansi (Google Ads + Meta Ads)
   - Toplam harcama ve ROAS
   - En iyi ve en kotu performans gosteren kampanyalar
   - CPC ve CTR trendleri

2. Trafik Analizi (Visitor Tracking + GA4)
   - Toplam ziyaretci ve oturum sayisi
   - Trafik kaynaklari dagilimi
   - GCLID/FBCLID attribution orani

3. Donusum Hunisi
   - Reklam tiki -> Site ziyareti
   - Site ziyareti -> Randevu
   - Randevu -> Satis
   - Her adimda kayip orani

4. SEO Durumu (Search Console)
   - Organik trafik trendi
   - Onemli keyword pozisyon degisiklikleri
   - Teknik sorunlar

Yaniti MARKDOWN formatinda ver. Kisa ve oz ol, sadece onemli bulgulari raporla."""

            if CLAUDE_SDK_AVAILABLE:
                response = ""
                async for msg in query(
                    prompt=prompt,
                    options=ClaudeAgentOptions(max_turns=1)
                ):
                    if hasattr(msg, 'content'):
                        for block in msg.content:
                            if hasattr(block, 'text'):
                                response += block.text

                state["funnel_analysis"] = response
            else:
                # Fallback without Claude SDK
                state["funnel_analysis"] = "Claude SDK not available - funnel analysis skipped"

            state = self.add_step(state, "analyze_funnel")

            logger.info("funnel_analyzed", analysis_length=len(state.get("funnel_analysis", "")))

        except Exception as e:
            error_msg = f"Funnel analysis failed: {str(e)}"
            state["errors"].append(error_msg)
            state["funnel_analysis"] = f"Analysis error: {str(e)}"
            logger.error("analyze_funnel_error", error=str(e))

        return state

    async def generate_insights_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Generate actionable insights and recommendations using Claude."""
        try:
            merged_data = state.get("merged_data", {})
            funnel_analysis = state.get("funnel_analysis", "")

            prompt = f"""Onceki funnel analizine dayanarak, TURKCE olarak somut insights ve oneriler uret.

FUNNEL ANALIZI:
{funnel_analysis}

HAM VERILER:
{self._format_data_for_prompt(merged_data)}

CIKTI FORMATI:

## ONE CIKAN BULGULAR
- Her bulgu tek cumlede, emoji ile baslayarak (ornek: "🔥 Google Ads 'costume op maat' keywordu %8.2 CTR ile lider")
- En fazla 5 bulgu

## DIKKAT EDILMESI GEREKENLER
- Sorunlar ve riskler
- En fazla 3 madde

## ONERILER
- Somut aksiyon onerileri
- Her oneriye oncelik seviyesi ekle (YUKSEK/ORTA/DUSUK)
- En fazla 5 oneri

Kisa ve oz yaz. Gereksiz detay verme."""

            if CLAUDE_SDK_AVAILABLE:
                response = ""
                async for msg in query(
                    prompt=prompt,
                    options=ClaudeAgentOptions(max_turns=1)
                ):
                    if hasattr(msg, 'content'):
                        for block in msg.content:
                            if hasattr(block, 'text'):
                                response += block.text

                # Parse insights and recommendations from response
                state["insights"] = self._parse_insights(response)
                state["recommendations"] = self._parse_recommendations(response)
            else:
                state["insights"] = ["Claude SDK not available"]
                state["recommendations"] = ["Enable Claude SDK for recommendations"]

            state = self.add_step(state, "generate_insights")

            logger.info(
                "insights_generated",
                insight_count=len(state["insights"]),
                recommendation_count=len(state["recommendations"])
            )

        except Exception as e:
            error_msg = f"Insights generation failed: {str(e)}"
            state["errors"].append(error_msg)
            logger.error("generate_insights_error", error=str(e))

        return state

    async def quality_check_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Check report quality and decide if regeneration needed."""
        try:
            funnel_analysis = state.get("funnel_analysis", "")
            insights = state.get("insights", [])
            recommendations = state.get("recommendations", [])
            errors = state.get("errors", [])

            score = 1.0

            # Check 1: Analysis length
            if len(funnel_analysis) < 200:
                score -= 0.3

            # Check 2: Has insights
            if len(insights) < 2:
                score -= 0.2

            # Check 3: Has recommendations
            if len(recommendations) < 2:
                score -= 0.2

            # Check 4: Data errors
            error_penalty = min(len(errors) * 0.1, 0.3)
            score -= error_penalty

            # Check 5: Data sources
            merged_data = state.get("merged_data", {})
            sources_with_data = merged_data.get("data_quality", {}).get("sources_with_data", 0)
            if sources_with_data < 4:
                score -= 0.2

            state["quality_score"] = max(0.0, score)
            state = self.add_step(state, "quality_check")

            logger.info(
                "quality_checked",
                score=state["quality_score"],
                regenerate_count=self.regenerate_count
            )

        except Exception as e:
            error_msg = f"Quality check failed: {str(e)}"
            state["errors"].append(error_msg)
            state["quality_score"] = 0.5  # Default to mid score
            logger.error("quality_check_error", error=str(e))

        return state

    def quality_router(self, state: DailyAnalyticsState) -> str:
        """Route based on quality score."""
        quality_score = state.get("quality_score", 0.0)

        # If quality too low and haven't regenerated too many times
        if quality_score < 0.7 and self.regenerate_count < self.max_regenerate:
            self.regenerate_count += 1
            logger.info("regenerating_analysis", attempt=self.regenerate_count)
            return "regenerate"

        return "format"

    async def format_report_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Format final report in Markdown."""
        try:
            brand = state["brand"]
            days = state["days"]
            funnel_analysis = state.get("funnel_analysis", "")
            insights = state.get("insights", [])
            recommendations = state.get("recommendations", [])
            merged_data = state.get("merged_data", {})

            # Build report
            today = datetime.now().strftime("%Y-%m-%d")
            report = f"""# 📊 Gunluk Analytics Raporu - {today}

**Marka:** {brand.title()}
**Donem:** Son {days} gun
**Olusturulma:** {datetime.now().strftime("%H:%M")}

---

## 🎯 Ozet Metrikler

| Metrik | Deger |
|--------|-------|
"""
            # Add summary metrics from merged data
            sources = merged_data.get("sources", {})

            # Google Ads
            ga = sources.get("google_ads", {})
            if ga and not ga.get("error"):
                report += f"| Google Ads Harcama | €{ga.get('total_spend', 0):,.2f} |\n"
                report += f"| Google Ads Tik | {ga.get('total_clicks', 0):,} |\n"

            # Meta Ads
            ma = sources.get("meta_ads", {})
            if ma and not ma.get("error"):
                report += f"| Meta Ads Harcama | €{ma.get('total_spend', 0):,.2f} |\n"
                report += f"| Meta Ads Erisim | {ma.get('total_reach', 0):,} |\n"

            # Visitor Tracking
            vt = sources.get("visitor_tracking", {})
            if vt and not vt.get("error"):
                report += f"| Site Oturumu | {vt.get('total_sessions', 0):,} |\n"
                report += f"| Benzersiz Ziyaretci | {vt.get('unique_visitors', 0):,} |\n"

            # Shopify
            sh = sources.get("shopify", {})
            if sh and not sh.get("error"):
                report += f"| Siparis | {sh.get('total_orders', 0):,} |\n"
                report += f"| Gelir | €{sh.get('total_revenue', 0):,.2f} |\n"

            # Appointments
            ap = sources.get("appointments", {})
            if ap and not ap.get("error"):
                report += f"| Randevu | {ap.get('total_appointments', 0):,} |\n"

            report += f"""
---

## 📈 Funnel Analizi

{funnel_analysis}

---

## 🔥 One Cikan Bulgular

"""
            for insight in insights[:5]:
                report += f"- {insight}\n"

            report += f"""
---

## 💡 Oneriler

"""
            for rec in recommendations[:5]:
                report += f"- {rec}\n"

            # Data quality note
            dq = merged_data.get("data_quality", {})
            report += f"""
---

## 📋 Veri Kalitesi

- Basarili kaynaklar: {dq.get('sources_with_data', 0)}/8
- Hatali kaynaklar: {dq.get('sources_with_errors', 0)}
- Rapor kalite skoru: {state.get('quality_score', 0):.0%}

---

🤖 *Bu rapor otomatik olarak olusturulmustur.*
"""

            state["report_markdown"] = report
            state = self.add_step(state, "format_report")

            logger.info("report_formatted", length=len(report))

        except Exception as e:
            error_msg = f"Report formatting failed: {str(e)}"
            state["errors"].append(error_msg)
            state["report_markdown"] = f"Rapor olusturulamadi: {str(e)}"
            logger.error("format_report_error", error=str(e))

        return state

    async def send_telegram_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Send report to Telegram."""
        try:
            report = state.get("report_markdown", "")

            if not report:
                state["telegram_sent"] = False
                state["errors"].append("No report to send")
                return state

            # Get Telegram config
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")

            if bot_token and chat_id:
                async with httpx.AsyncClient() as client:
                    # Telegram has 4096 char limit, split if needed
                    max_length = 4000

                    if len(report) > max_length:
                        # Send in parts
                        parts = [report[i:i+max_length] for i in range(0, len(report), max_length)]
                        for i, part in enumerate(parts):
                            response = await client.post(
                                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                json={
                                    "chat_id": chat_id,
                                    "text": f"📊 Rapor ({i+1}/{len(parts)})\n\n{part}",
                                    "parse_mode": "Markdown"
                                }
                            )
                            if response.status_code == 200:
                                result = response.json()
                                if i == 0:
                                    state["telegram_message_id"] = str(result.get("result", {}).get("message_id"))
                    else:
                        response = await client.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": report,
                                "parse_mode": "Markdown"
                            }
                        )
                        if response.status_code == 200:
                            result = response.json()
                            state["telegram_message_id"] = str(result.get("result", {}).get("message_id"))

                state["telegram_sent"] = True
                logger.info("telegram_sent", message_id=state.get("telegram_message_id"))
            else:
                state["telegram_sent"] = False
                state["errors"].append("Telegram config missing")
                logger.warning("telegram_config_missing")

            state = self.add_step(state, "send_telegram")

        except Exception as e:
            error_msg = f"Telegram send failed: {str(e)}"
            state["errors"].append(error_msg)
            state["telegram_sent"] = False
            logger.error("send_telegram_error", error=str(e))

        return state

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _format_data_for_prompt(self, merged_data: Dict[str, Any]) -> str:
        """Format merged data for Claude prompt."""
        if not merged_data:
            return "Veri yok"

        parts = []
        sources = merged_data.get("sources", {})

        for source_name, source_data in sources.items():
            if source_data and not source_data.get("error"):
                parts.append(f"\n### {source_name.upper()}")
                # Add key metrics
                for key, value in source_data.items():
                    if key not in ["source", "error"] and not isinstance(value, list):
                        parts.append(f"- {key}: {value}")

        return "\n".join(parts) if parts else "Yeterli veri toplanamadi"

    def _parse_insights(self, response: str) -> List[str]:
        """Parse insights from Claude response."""
        insights = []
        in_insights_section = False

        for line in response.split("\n"):
            if "BULGU" in line.upper() or "INSIGHT" in line.upper():
                in_insights_section = True
                continue
            if "DIKKAT" in line.upper() or "ONERILER" in line.upper():
                in_insights_section = False
            if in_insights_section and line.strip().startswith("-"):
                insights.append(line.strip()[1:].strip())

        return insights[:5]

    def _parse_recommendations(self, response: str) -> List[str]:
        """Parse recommendations from Claude response."""
        recommendations = []
        in_rec_section = False

        for line in response.split("\n"):
            if "ONERI" in line.upper() or "RECOMMENDATION" in line.upper():
                in_rec_section = True
                continue
            if in_rec_section and line.strip().startswith("-"):
                recommendations.append(line.strip()[1:].strip())

        return recommendations[:5]

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def generate_report(
        self,
        days: int = 7,
        brand: str = "pomandi"
    ) -> Dict[str, Any]:
        """
        Generate daily analytics report.

        Args:
            days: Number of days to analyze (default: 7)
            brand: Brand name ("pomandi" or "costume")

        Returns:
            Report result with markdown, insights, and delivery status
        """
        start_time = time.time()
        status = "success"

        try:
            # Reset regenerate counter
            self.regenerate_count = 0

            # Initialize state
            initial_state = init_daily_analytics_state(days, brand)

            # Run graph
            final_state = await self.run(**initial_state)

            # Build result
            result = {
                "success": True,
                "brand": brand,
                "period_days": days,
                "report_markdown": final_state.get("report_markdown", ""),
                "insights": final_state.get("insights", []),
                "recommendations": final_state.get("recommendations", []),
                "quality_score": final_state.get("quality_score", 0.0),
                "telegram_sent": final_state.get("telegram_sent", False),
                "telegram_message_id": final_state.get("telegram_message_id"),
                "errors": final_state.get("errors", []),
                "steps_completed": final_state.get("steps_completed", []),
                "regenerate_attempts": self.regenerate_count
            }

            # Record metrics
            if METRICS_AVAILABLE:
                duration = time.time() - start_time
                record_agent_execution(
                    agent_name="daily_analytics",
                    duration_seconds=duration,
                    status=status,
                    confidence=result["quality_score"]
                )

            logger.info(
                "daily_analytics_complete",
                brand=brand,
                days=days,
                quality_score=result["quality_score"],
                telegram_sent=result["telegram_sent"]
            )

            return result

        except Exception as e:
            status = "failure"
            duration = time.time() - start_time

            if METRICS_AVAILABLE:
                record_agent_execution(
                    agent_name="daily_analytics",
                    duration_seconds=duration,
                    status=status
                )

            logger.error("daily_analytics_failed", error=str(e))
            raise
