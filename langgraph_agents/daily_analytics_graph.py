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

Workflow (v3 - Real-time Per-Source Messaging):
1. For each of 8 sources:
   - Fetch data from source
   - Run full LLM analysis (Claude)
   - Generate Turkish sub-report with diagnostics
   - IMMEDIATELY send to Telegram (8 messages)
2. Create final summary report (9th message)
3. Send final summary to Telegram

Total: 9 Telegram messages per run
- 8 detailed source reports (sent as each source is analyzed)
- 1 executive summary (sent at the end)

Schedule: Daily 08:00 UTC (10:00 Amsterdam)
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from langgraph.graph import StateGraph, END
from pathlib import Path
import structlog
import time
import os
import asyncio
import asyncpg
import httpx
import json
import hashlib

# Output directory for saving analytics data
AGENT_OUTPUTS_DIR = Path(__file__).parent.parent / "agent_outputs" / "daily_analytics"

from .base_graph import BaseAgentGraph
from .state_schemas import DailyAnalyticsState, init_daily_analytics_state
from .error_handling import (
    fetch_with_smart_retry,
    ErrorAggregator,
    circuit_registry,
    diagnose_error
)

# Import monitoring metrics
try:
    from monitoring.metrics import record_agent_execution
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

# Import Claude Agent SDK (for analysis nodes)
try:
    from claude_agent_sdk import query, ClaudeAgentOptions
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

# Import MCP Python SDK (for direct MCP server calls)
_mcp_import_error = None
try:
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.stdio import stdio_client
    MCP_SDK_AVAILABLE = True
except ImportError as e:
    MCP_SDK_AVAILABLE = False
    _mcp_import_error = str(e)

logger = structlog.get_logger(__name__)

# Log MCP SDK availability at startup
logger.info("mcp_sdk_status", available=MCP_SDK_AVAILABLE, error=_mcp_import_error)


class DailyAnalyticsGraph(BaseAgentGraph):
    """
    Daily analytics report generator with real-time per-source Telegram messaging.

    Flow (v3 - Real-time Per-Source Messaging):
        START
          |
          v
        fetch_google_ads --> analyze_google_ads (LLM) --> 📨 Telegram (1/8)
          |
          v
        fetch_meta_ads --> analyze_meta_ads (LLM) --> 📨 Telegram (2/8)
          |
          v
        fetch_visitor_tracking --> analyze_visitor_tracking (LLM) --> 📨 Telegram (3/8)
          |
          v
        fetch_ga4 --> analyze_ga4 (LLM) --> 📨 Telegram (4/8)
          |
          v
        fetch_search_console --> analyze_search_console (LLM) --> 📨 Telegram (5/8)
          |
          v
        fetch_merchant --> analyze_merchant (LLM) --> 📨 Telegram (6/8)
          |
          v
        fetch_shopify --> analyze_shopify (LLM) --> 📨 Telegram (7/8)
          |
          v
        fetch_appointments --> analyze_appointments (LLM) --> 📨 Telegram (8/8)
          |
          v
        merge_reports (create executive summary)
          |
          v
        send_telegram --> 📨 Telegram (9/9 - Final Summary)
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

    Each source gets full LLM analysis that:
        1. Checks data status (success/error)
        2. Diagnoses issues if data is 0 or missing
        3. Summarizes key metrics
        4. Provides recommendations
        5. IMMEDIATELY sends to Telegram (no waiting for all sources)

    Total Telegram Messages: 9
        - 8 detailed source reports (real-time as each source is analyzed)
        - 1 executive summary with key metrics (at the end)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.regenerate_count = 0
        self.max_regenerate = 2
        self._mcp_dir = Path(__file__).parent.parent / "mcp-servers"
        # Error tracking for resilient data collection
        self.error_aggregator = ErrorAggregator()
        # Reset circuit breakers on new instance (optional - remove if you want persistence)
        # circuit_registry.reset()

    def _get_server_path(self, server_name: str) -> Optional[Path]:
        """Get the path to an MCP server script."""
        server_path = self._mcp_dir / server_name / "server.py"
        if server_path.exists():
            return server_path
        logger.warning(f"MCP server not found: {server_name} at {server_path}")
        return None

    async def _call_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call an MCP server tool directly using MCP Python SDK.

        This uses stdio_client to spawn the MCP server as a subprocess
        and communicate via stdin/stdout using the MCP protocol.

        Args:
            server_name: Name of the MCP server (e.g., 'google-ads')
            tool_name: Name of the tool to call (e.g., 'get_campaigns')
            arguments: Arguments to pass to the tool

        Returns:
            Dict with tool result or error
        """
        if not MCP_SDK_AVAILABLE:
            logger.error("MCP SDK not available")
            return {"error": "MCP SDK not available"}

        server_path = self._get_server_path(server_name)
        if not server_path:
            return {"error": f"MCP server '{server_name}' not found"}

        try:
            # Create server parameters
            server_params = StdioServerParameters(
                command="python3",
                args=[str(server_path)],
                env=dict(os.environ)  # Pass all env vars (API keys, etc.)
            )

            logger.info(f"Calling MCP tool: {server_name}/{tool_name}", arguments=arguments)

            # Connect to MCP server and call tool
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize the session
                    await session.initialize()

                    # Call the tool
                    result = await session.call_tool(tool_name, arguments)

                    # Parse the result
                    if result.content:
                        for content in result.content:
                            if hasattr(content, 'text'):
                                text = content.text
                                # Check if response is an error message (MCP servers return "Error: ...")
                                if text.startswith("Error:"):
                                    error_msg = text[6:].strip()  # Remove "Error:" prefix
                                    logger.error("mcp_tool_returned_error", server=server_name, tool=tool_name, error=error_msg)
                                    return {"error": error_msg, "raw_response": text}
                                try:
                                    return json.loads(text)
                                except json.JSONDecodeError:
                                    # Check if it looks like an error even without prefix
                                    if "credentials" in text.lower() or "not found" in text.lower() or "failed" in text.lower():
                                        logger.warning("mcp_possible_error_in_response", server=server_name, tool=tool_name, text=text[:200])
                                        return {"error": text, "raw_response": text}
                                    return {"raw_response": text}

                    return {"error": "No content in response"}

        except Exception as e:
            error_msg = f"MCP tool call failed: {server_name}/{tool_name}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    async def _call_mcp_tools_batch(
        self,
        server_name: str,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Call multiple tools on the same MCP server in a single session.

        This is more efficient than calling _call_mcp_tool multiple times
        because it reuses the same server connection.

        Args:
            server_name: Name of the MCP server
            tools: List of dicts with 'name' and 'arguments' keys

        Returns:
            List of results for each tool call
        """
        logger.info("mcp_batch_call_start", server=server_name, tools=[t.get("name") for t in tools], mcp_sdk_available=MCP_SDK_AVAILABLE)

        if not MCP_SDK_AVAILABLE:
            logger.warning("mcp_sdk_not_available", error=_mcp_import_error)
            return [{"error": f"MCP SDK not available: {_mcp_import_error}"} for _ in tools]

        server_path = self._get_server_path(server_name)
        if not server_path:
            logger.warning("mcp_server_not_found", server=server_name, mcp_dir=str(self._mcp_dir))
            return [{"error": f"MCP server '{server_name}' not found at {self._mcp_dir}"} for _ in tools]

        logger.info("mcp_server_found", server=server_name, path=str(server_path))
        results = []

        try:
            server_params = StdioServerParameters(
                command="python3",
                args=[str(server_path)],
                env=dict(os.environ)
            )

            logger.info("mcp_connecting", server=server_name)
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    logger.info("mcp_session_initialized", server=server_name)

                    for tool in tools:
                        tool_name = tool.get("name")
                        arguments = tool.get("arguments", {})

                        try:
                            logger.debug("mcp_tool_calling", server=server_name, tool=tool_name)
                            result = await session.call_tool(tool_name, arguments)
                            if result.content:
                                for content in result.content:
                                    if hasattr(content, 'text'):
                                        text = content.text
                                        # Check if response is an error message (MCP servers return "Error: ...")
                                        if text.startswith("Error:"):
                                            error_msg = text[6:].strip()
                                            logger.error("mcp_tool_returned_error", server=server_name, tool=tool_name, error=error_msg)
                                            results.append({"error": error_msg, "raw_response": text})
                                            break
                                        try:
                                            parsed = json.loads(text)
                                            results.append(parsed)
                                            logger.debug("mcp_tool_success", server=server_name, tool=tool_name)
                                        except json.JSONDecodeError as e:
                                            # Check if it looks like an error even without prefix
                                            if "credentials" in text.lower() or "not found" in text.lower() or "failed" in text.lower():
                                                logger.warning("mcp_possible_error_in_response", server=server_name, tool=tool_name, text=text[:200])
                                                results.append({"error": text, "raw_response": text})
                                            else:
                                                # DIAGNOSTIC: Log JSON parse failure details
                                                logger.warning("mcp_json_parse_failed",
                                                    server=server_name,
                                                    tool=tool_name,
                                                    error=str(e),
                                                    text_preview=text[:200] if text else "EMPTY"
                                                )
                                                results.append({"raw_response": text[:500]})
                                        break
                                else:
                                    results.append({"error": "No text content"})
                            else:
                                results.append({"error": "No content"})
                        except Exception as e:
                            logger.error("mcp_tool_error", server=server_name, tool=tool_name, error=str(e))
                            results.append({"error": str(e)})

        except Exception as e:
            logger.error("mcp_batch_call_failed", server=server_name, error=str(e))
            results = [{"error": str(e)} for _ in tools]

        logger.info("mcp_batch_call_complete", server=server_name, results_count=len(results))
        return results

    def build_graph(self) -> StateGraph:
        """Build daily analytics graph with per-source LLM analysis.

        New Flow (v2):
            fetch_google_ads -> analyze_google_ads ->
            fetch_meta_ads -> analyze_meta_ads ->
            fetch_visitor_tracking -> analyze_visitor_tracking ->
            fetch_ga4 -> analyze_ga4 ->
            fetch_search_console -> analyze_search_console ->
            fetch_merchant -> analyze_merchant ->
            fetch_shopify -> analyze_shopify ->
            fetch_appointments -> analyze_appointments ->
            merge_reports -> send_telegram -> END

        Each data source gets its own full LLM analysis with Turkish sub-report.
        """
        graph = StateGraph(DailyAnalyticsState)

        # Data collection + analysis nodes (16 total: 8 fetch + 8 analyze)
        graph.add_node("fetch_google_ads", self.fetch_google_ads_node)
        graph.add_node("analyze_google_ads", self.analyze_google_ads_node)
        graph.add_node("fetch_meta_ads", self.fetch_meta_ads_node)
        graph.add_node("analyze_meta_ads", self.analyze_meta_ads_node)
        graph.add_node("fetch_visitor_tracking", self.fetch_visitor_tracking_node)
        graph.add_node("analyze_visitor_tracking", self.analyze_visitor_tracking_node)
        graph.add_node("fetch_ga4", self.fetch_ga4_node)
        graph.add_node("analyze_ga4", self.analyze_ga4_node)
        graph.add_node("fetch_search_console", self.fetch_search_console_node)
        graph.add_node("analyze_search_console", self.analyze_search_console_node)
        graph.add_node("fetch_merchant", self.fetch_merchant_node)
        graph.add_node("analyze_merchant", self.analyze_merchant_node)
        graph.add_node("fetch_shopify", self.fetch_shopify_node)
        graph.add_node("analyze_shopify", self.analyze_shopify_node)
        graph.add_node("fetch_appointments", self.fetch_appointments_node)
        graph.add_node("analyze_appointments", self.analyze_appointments_node)

        # Final nodes
        graph.add_node("merge_reports", self.merge_reports_node)
        graph.add_node("save_data", self.save_data_node)  # NEW: Data persistence
        graph.add_node("send_telegram", self.send_telegram_node)

        # Entry point
        graph.set_entry_point("fetch_google_ads")

        # Sequential edges: fetch -> analyze -> next fetch
        graph.add_edge("fetch_google_ads", "analyze_google_ads")
        graph.add_edge("analyze_google_ads", "fetch_meta_ads")
        graph.add_edge("fetch_meta_ads", "analyze_meta_ads")
        graph.add_edge("analyze_meta_ads", "fetch_visitor_tracking")
        graph.add_edge("fetch_visitor_tracking", "analyze_visitor_tracking")
        graph.add_edge("analyze_visitor_tracking", "fetch_ga4")
        graph.add_edge("fetch_ga4", "analyze_ga4")
        graph.add_edge("analyze_ga4", "fetch_search_console")
        graph.add_edge("fetch_search_console", "analyze_search_console")
        graph.add_edge("analyze_search_console", "fetch_merchant")
        graph.add_edge("fetch_merchant", "analyze_merchant")
        graph.add_edge("analyze_merchant", "fetch_shopify")
        graph.add_edge("fetch_shopify", "analyze_shopify")
        graph.add_edge("analyze_shopify", "fetch_appointments")
        graph.add_edge("fetch_appointments", "analyze_appointments")

        # After all analysis, merge reports, save data, then send
        graph.add_edge("analyze_appointments", "merge_reports")
        graph.add_edge("merge_reports", "save_data")  # NEW: Save before sending
        graph.add_edge("save_data", "send_telegram")
        graph.add_edge("send_telegram", END)

        return graph

    # =========================================================================
    # DATA COLLECTION NODES (8 sources)
    # =========================================================================

    async def fetch_google_ads_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Google Ads campaign data with smart error handling."""
        source_name = "google_ads"
        days = state["days"]
        brand = state["brand"]

        logger.info("Fetching Google Ads data", days=days, brand=brand)

        # Date range for keywords
        end_date_str = datetime.now().strftime("%Y-%m-%d")
        start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        tools = [
            {"name": "get_account_summary", "arguments": {"days": days}},
            {"name": "get_campaigns", "arguments": {"days": days}},
            {"name": "get_keywords", "arguments": {"start_date": start_date_str, "end_date": end_date_str, "limit": 20}},
        ]

        # Smart fetch with error diagnosis and auto-fix attempts
        fetch_result = await fetch_with_smart_retry(
            source_name=source_name,
            fetch_func=lambda: self._call_mcp_tools_batch("google-ads", tools),
            context={"mcp_dir": str(self._mcp_dir)},
            max_retries=3,
            circuit_threshold=5,
            circuit_cooldown=120.0
        )

        if not fetch_result["success"]:
            # Log detailed diagnosis
            diagnosis = fetch_result.get("diagnosis", {})
            logger.error(
                "google_ads_fetch_failed",
                error=fetch_result.get("error"),
                category=diagnosis.get("category"),
                cause=diagnosis.get("probable_cause"),
                fix=diagnosis.get("suggested_fix"),
                attempts=fetch_result.get("attempts"),
                fixes_tried=fetch_result.get("fixes_applied", [])
            )

            state["google_ads_data"] = {
                "source": source_name,
                "error": fetch_result.get("error"),
                "diagnosis": diagnosis
            }
            state["errors"].append(fetch_result.get("error", "Unknown error"))
            self.error_aggregator.add_error(
                source_name,
                fetch_result.get("error", "Unknown"),
                attempts=fetch_result.get("attempts", 1),
                fixes_tried=fetch_result.get("fixes_applied", [])
            )
            state = self.add_step(state, "fetch_google_ads")
            return state

        # Success - process results
        results = fetch_result["data"]
        account_summary = results[0] if len(results) > 0 else {}
        campaigns = results[1] if len(results) > 1 else {}
        keywords = results[2] if len(results) > 2 else {}

        totals = account_summary.get("account_totals", account_summary.get("totals", {}))
        data = {
            "source": source_name,
            "period_days": days,
            "account_summary": account_summary,
            "campaigns": campaigns.get("campaigns", []),
            "total_spend": totals.get("cost", 0),
            "total_clicks": totals.get("clicks", 0),
            "total_impressions": totals.get("impressions", 0),
            "total_conversions": totals.get("conversions", 0),
            "avg_cpc": totals.get("cpc", 0),
            "avg_ctr": totals.get("ctr", 0),
            "top_keywords": keywords.get("keywords", [])[:20],
            "error": None,
            "fetch_attempts": fetch_result.get("attempts", 1),
            "fixes_applied": fetch_result.get("fixes_applied", [])
        }

        self.error_aggregator.add_success(source_name)
        state["google_ads_data"] = data
        state = self.add_step(state, "fetch_google_ads")

        logger.info(
            "google_ads_fetched",
            days=days,
            brand=brand,
            attempts=fetch_result.get("attempts"),
            wait_time=fetch_result.get("total_wait_time", 0)
        )

        return state

    async def fetch_meta_ads_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Meta Ads (Facebook/Instagram) data with smart error handling and token refresh."""
        source_name = "meta_ads"
        days = state["days"]
        brand = state["brand"]

        logger.info("Fetching Meta Ads data", days=days, brand=brand)

        tools = [
            {"name": "get_campaigns", "arguments": {"days": days}},
            {"name": "get_adsets", "arguments": {"days": days}},
            {"name": "get_ads", "arguments": {"days": days}},
        ]

        # Smart fetch with auto token refresh for auth errors
        fetch_result = await fetch_with_smart_retry(
            source_name=source_name,
            fetch_func=lambda: self._call_mcp_tools_batch("meta-ads", tools),
            context={"mcp_dir": str(self._mcp_dir)},
            max_retries=3,
            circuit_threshold=5,
            circuit_cooldown=120.0
        )

        if not fetch_result["success"]:
            diagnosis = fetch_result.get("diagnosis", {})
            logger.error(
                "meta_ads_fetch_failed",
                error=fetch_result.get("error"),
                category=diagnosis.get("category"),
                cause=diagnosis.get("probable_cause"),
                fix=diagnosis.get("suggested_fix"),
                attempts=fetch_result.get("attempts"),
                fixes_tried=fetch_result.get("fixes_applied", [])
            )

            state["meta_ads_data"] = {
                "source": source_name,
                "error": fetch_result.get("error"),
                "diagnosis": diagnosis
            }
            state["errors"].append(fetch_result.get("error", "Unknown error"))
            self.error_aggregator.add_error(
                source_name,
                fetch_result.get("error", "Unknown"),
                attempts=fetch_result.get("attempts", 1),
                fixes_tried=fetch_result.get("fixes_applied", [])
            )
            state = self.add_step(state, "fetch_meta_ads")
            return state

        # Success - process results
        results = fetch_result["data"]
        campaigns = results[0] if len(results) > 0 else {}
        adsets = results[1] if len(results) > 1 else {}
        ads = results[2] if len(results) > 2 else {}

        # Use summary if available, otherwise calculate from campaigns
        summary = campaigns.get("summary", {})
        if summary:
            total_spend = summary.get("total_spend", 0)
            total_clicks = summary.get("total_clicks", 0)
            total_impressions = summary.get("total_impressions", 0)
        else:
            total_spend = sum(float((c.get("insights") or {}).get("spend", 0) or 0) for c in campaigns.get("campaigns", []))
            total_clicks = sum(int((c.get("insights") or {}).get("clicks", 0) or 0) for c in campaigns.get("campaigns", []))
            total_impressions = sum(int((c.get("insights") or {}).get("impressions", 0) or 0) for c in campaigns.get("campaigns", []))

        total_reach = sum(int((c.get("insights") or {}).get("reach", 0) or 0) for c in campaigns.get("campaigns", []))

        data = {
            "source": source_name,
            "period_days": days,
            "campaigns": campaigns.get("campaigns", []),
            "adsets": adsets.get("adsets", []),
            "ads": ads.get("ads", []),
            "total_campaigns": campaigns.get("total_campaigns", len(campaigns.get("campaigns", []))),
            "total_spend": total_spend,
            "total_reach": total_reach,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_conversions": summary.get("conversions", 0),
            "avg_cpm": summary.get("cpm", 0),
            "avg_ctr": summary.get("avg_ctr", 0),
            "error": None,
            "fetch_attempts": fetch_result.get("attempts", 1),
            "fixes_applied": fetch_result.get("fixes_applied", [])
        }

        self.error_aggregator.add_success(source_name)
        state["meta_ads_data"] = data
        state = self.add_step(state, "fetch_meta_ads")

        logger.info(
            "meta_ads_fetched",
            days=days,
            brand=brand,
            total_campaigns=data.get("total_campaigns"),
            total_spend=data.get("total_spend"),
            attempts=fetch_result.get("attempts"),
            wait_time=fetch_result.get("total_wait_time", 0)
        )

        return state

    async def fetch_visitor_tracking_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """
        Fetch custom visitor tracking data via MCP server.

        Uses visitor-tracking MCP server which:
        - Connects to PostgreSQL visitor tracking database
        - Excludes bot traffic (is_bot = false)
        - Returns sessions, visitors, UTM/GCLID/FBCLID attribution, landing pages, traffic sources
        """
        source_name = "visitor_tracking"
        days = state["days"]

        logger.info("Fetching visitor tracking data via MCP", days=days)

        # Use MCP server for data collection
        fetch_result = await fetch_with_smart_retry(
            source_name=source_name,
            fetch_func=lambda: self._call_mcp_tool(
                "visitor-tracking",
                "get_visitor_summary",
                {"days": days}
            ),
            context={"mcp_dir": str(self._mcp_dir)},
            max_retries=3,
            circuit_threshold=5,
            circuit_cooldown=120.0
        )

        if not fetch_result["success"]:
            diagnosis = fetch_result.get("diagnosis", {})
            logger.error(
                "visitor_tracking_fetch_failed",
                error=fetch_result.get("error"),
                category=diagnosis.get("category"),
                cause=diagnosis.get("probable_cause"),
                attempts=fetch_result.get("attempts")
            )

            state["visitor_tracking_data"] = {
                "source": source_name,
                "error": fetch_result.get("error"),
                "diagnosis": diagnosis
            }
            state["errors"].append(fetch_result.get("error", "Unknown error"))
            self.error_aggregator.add_error(
                source_name,
                fetch_result.get("error", "Unknown"),
                attempts=fetch_result.get("attempts", 1),
                fixes_tried=fetch_result.get("fixes_applied", [])
            )
            state = self.add_step(state, "fetch_visitor_tracking")
            return state

        # Success - MCP returns complete summary
        result = fetch_result["data"]

        # Check for error in MCP response
        if result.get("error"):
            error_msg = result.get("error")
            state["visitor_tracking_data"] = {
                "source": source_name,
                "error": error_msg,
                "diagnosis": {"category": "mcp_error", "probable_cause": error_msg}
            }
            state["errors"].append(error_msg)
            self.error_aggregator.add_error(source_name, error_msg)
            state = self.add_step(state, "fetch_visitor_tracking")
            return state

        data = {
            "source": source_name,
            "period_days": days,
            "total_sessions": result.get("total_sessions", 0),
            "unique_visitors": result.get("unique_visitors", 0),
            "utm_sessions": result.get("utm_sessions", 0),
            "gclid_sessions": result.get("gclid_sessions", 0),
            "fbclid_sessions": result.get("fbclid_sessions", 0),
            "median_session_duration": result.get("median_session_duration", 0),
            "conversions": result.get("conversions", []),
            "top_landing_pages": result.get("top_landing_pages", []),
            "traffic_sources": result.get("traffic_sources", []),
            "error": None,
            "fetch_attempts": fetch_result.get("attempts", 1)
        }

        self.error_aggregator.add_success(source_name)
        state["visitor_tracking_data"] = data
        state = self.add_step(state, "fetch_visitor_tracking")

        logger.info(
            "visitor_tracking_fetched",
            days=days,
            sessions=data.get("total_sessions", 0),
            visitors=data.get("unique_visitors", 0),
            attempts=fetch_result.get("attempts")
        )

        return state

    async def fetch_ga4_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Google Analytics 4 data with smart error handling."""
        source_name = "ga4"
        days = state["days"]

        logger.info("Fetching GA4 data", days=days)

        fetch_result = await fetch_with_smart_retry(
            source_name=source_name,
            fetch_func=lambda: self._call_mcp_tool("analytics", "get_traffic_overview", {"days": days}),
            context={"mcp_dir": str(self._mcp_dir)},
            max_retries=3,
            circuit_threshold=5,
            circuit_cooldown=120.0
        )

        if not fetch_result["success"]:
            diagnosis = fetch_result.get("diagnosis", {})
            logger.error("ga4_fetch_failed", error=fetch_result.get("error"), category=diagnosis.get("category"))

            state["ga4_data"] = {"source": source_name, "error": fetch_result.get("error"), "diagnosis": diagnosis}
            state["errors"].append(fetch_result.get("error", "Unknown error"))
            self.error_aggregator.add_error(source_name, fetch_result.get("error", "Unknown"), attempts=fetch_result.get("attempts", 1))
            state = self.add_step(state, "fetch_ga4")
            return state

        result = fetch_result["data"]
        # MCP server returns data in "summary" dict, not at top level
        summary = result.get("summary", {})
        data = {
            "source": source_name,
            "period_days": days,
            "total_users": summary.get("activeUsers", 0),  # GA4 uses "activeUsers"
            "new_users": summary.get("newUsers", 0),
            "sessions": summary.get("sessions", 0),
            "page_views": summary.get("pageviews", 0),
            "avg_session_duration": summary.get("avgSessionDuration", 0),
            "bounce_rate": summary.get("avgBounceRate", 0),
            "top_pages": result.get("rows", [])[:10],  # Use rows as top pages data
            "traffic_sources": result.get("traffic_sources", []),
            "error": None,
            "fetch_attempts": fetch_result.get("attempts", 1)
        }

        self.error_aggregator.add_success(source_name)
        state["ga4_data"] = data
        state = self.add_step(state, "fetch_ga4")
        logger.info("ga4_fetched", days=days, attempts=fetch_result.get("attempts"))

        return state

    async def fetch_search_console_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Search Console SEO data with smart error handling."""
        source_name = "search_console"
        days = state["days"]

        logger.info("Fetching Search Console data", days=days)

        fetch_result = await fetch_with_smart_retry(
            source_name=source_name,
            fetch_func=lambda: self._call_mcp_tool("search-console", "get_search_analytics", {"days": days}),
            context={"mcp_dir": str(self._mcp_dir)},
            max_retries=3,
            circuit_threshold=5,
            circuit_cooldown=120.0
        )

        if not fetch_result["success"]:
            diagnosis = fetch_result.get("diagnosis", {})
            logger.error("search_console_fetch_failed", error=fetch_result.get("error"), category=diagnosis.get("category"))

            state["search_console_data"] = {"source": source_name, "error": fetch_result.get("error"), "diagnosis": diagnosis}
            state["errors"].append(fetch_result.get("error", "Unknown error"))
            self.error_aggregator.add_error(source_name, fetch_result.get("error", "Unknown"), attempts=fetch_result.get("attempts", 1))
            state = self.add_step(state, "fetch_search_console")
            return state

        result = fetch_result["data"]
        # MCP server returns data in "summary" dict, not at top level
        summary = result.get("summary", {})
        data = {
            "source": source_name,
            "period_days": days,
            "total_clicks": summary.get("total_clicks", 0),
            "total_impressions": summary.get("total_impressions", 0),
            "avg_ctr": summary.get("average_ctr", 0),  # Note: "average_ctr" not "avg_ctr"
            "avg_position": summary.get("average_position", 0),
            "top_queries": result.get("queries", result.get("rows", []))[:20],
            "top_pages": result.get("pages", [])[:20],
            "error": None,
            "fetch_attempts": fetch_result.get("attempts", 1)
        }

        self.error_aggregator.add_success(source_name)
        state["search_console_data"] = data
        state = self.add_step(state, "fetch_search_console")
        logger.info("search_console_fetched", days=days, attempts=fetch_result.get("attempts"))

        return state

    async def fetch_merchant_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Google Merchant Center data with smart error handling."""
        source_name = "merchant_center"
        days = state["days"]

        logger.info("Fetching Merchant Center data", days=days)

        tools = [{"name": "get_shopping_summary", "arguments": {"days": days}}]

        fetch_result = await fetch_with_smart_retry(
            source_name=source_name,
            fetch_func=lambda: self._call_mcp_tools_batch("merchant-center", tools),
            context={"mcp_dir": str(self._mcp_dir)},
            max_retries=3,
            circuit_threshold=5,
            circuit_cooldown=120.0
        )

        if not fetch_result["success"]:
            diagnosis = fetch_result.get("diagnosis", {})
            logger.error("merchant_fetch_failed", error=fetch_result.get("error"), category=diagnosis.get("category"))

            state["merchant_data"] = {"source": source_name, "error": fetch_result.get("error"), "diagnosis": diagnosis}
            state["errors"].append(fetch_result.get("error", "Unknown error"))
            self.error_aggregator.add_error(source_name, fetch_result.get("error", "Unknown"), attempts=fetch_result.get("attempts", 1))
            state = self.add_step(state, "fetch_merchant")
            return state

        results = fetch_result["data"]
        summary = results[0] if len(results) > 0 else {}

        # NEW format: feed_summary has accurate product counts
        feed_summary = summary.get("feed_summary", {})
        perf = summary.get("performance_summary", {})
        health = summary.get("health_summary", {})

        data = {
            "source": source_name,
            "period_days": days,
            "merchant_id": summary.get("merchant_id", "unknown"),
            # Feed summary - ACCURATE product counts (pagination fixed)
            "total_products": feed_summary.get("total_products_in_feed", 0),
            "products_checked": feed_summary.get("products_checked", 0),
            "approved_products": feed_summary.get("approved", 0),
            "limited_products": feed_summary.get("limited", 0),
            "disapproved_products": feed_summary.get("disapproved", 0),
            "pending_products": feed_summary.get("pending", 0),
            # Health metrics
            "health_score": health.get("health_score", 0),
            "critical_issues": health.get("critical_issues", 0),
            "total_issues": health.get("total_issues", 0),
            # Performance (only products with impressions/clicks)
            "products_with_impressions": perf.get("products_with_impressions", 0),
            "total_clicks": perf.get("total_clicks", 0),
            "total_impressions": perf.get("total_impressions", 0),
            "average_ctr": perf.get("average_ctr", 0),
            # Issues
            "top_issues": summary.get("top_issues", []),
            "error": None,
            "fetch_attempts": fetch_result.get("attempts", 1)
        }

        self.error_aggregator.add_success(source_name)
        state["merchant_data"] = data
        state = self.add_step(state, "fetch_merchant")
        logger.info("merchant_fetched", days=days, attempts=fetch_result.get("attempts"))

        return state

    async def fetch_shopify_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch Shopify orders and revenue data with smart error handling."""
        source_name = "shopify"
        days = state["days"]
        brand = state["brand"]

        logger.info("Fetching Shopify data", days=days, brand=brand)

        tools = [
            {"name": "get_orders", "arguments": {"days": days}},
            {"name": "get_products", "arguments": {"limit": 20}},
        ]

        fetch_result = await fetch_with_smart_retry(
            source_name=source_name,
            fetch_func=lambda: self._call_mcp_tools_batch("shopify", tools),
            context={"mcp_dir": str(self._mcp_dir)},
            max_retries=3,
            circuit_threshold=5,
            circuit_cooldown=120.0
        )

        if not fetch_result["success"]:
            diagnosis = fetch_result.get("diagnosis", {})
            logger.error("shopify_fetch_failed", error=fetch_result.get("error"), category=diagnosis.get("category"))

            state["shopify_data"] = {"source": source_name, "error": fetch_result.get("error"), "diagnosis": diagnosis}
            state["errors"].append(fetch_result.get("error", "Unknown error"))
            self.error_aggregator.add_error(source_name, fetch_result.get("error", "Unknown"), attempts=fetch_result.get("attempts", 1))
            state = self.add_step(state, "fetch_shopify")
            return state

        results = fetch_result["data"]
        orders = results[0] if len(results) > 0 else {}
        products = results[1] if len(results) > 1 else {}

        order_list = orders.get("orders", [])
        total_revenue = sum(float(o.get("total_price", 0)) for o in order_list)
        avg_order_value = total_revenue / len(order_list) if order_list else 0

        data = {
            "source": source_name,
            "period_days": days,
            "total_orders": len(order_list),
            "total_revenue": total_revenue,
            "average_order_value": avg_order_value,
            "new_customers": orders.get("new_customers", 0),
            "returning_customers": orders.get("returning_customers", 0),
            "top_products": products.get("products", [])[:20],
            "abandoned_carts": orders.get("abandoned_checkouts", 0),
            "error": None,
            "fetch_attempts": fetch_result.get("attempts", 1)
        }

        self.error_aggregator.add_success(source_name)
        state["shopify_data"] = data
        state = self.add_step(state, "fetch_shopify")
        logger.info("shopify_fetched", days=days, brand=brand, attempts=fetch_result.get("attempts"))

        return state

    async def fetch_appointments_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Fetch appointment data from Afspraak-DB with smart error handling."""
        source_name = "appointments"
        days = state["days"]
        brand = state["brand"]

        logger.info("Fetching Appointments data", days=days, brand=brand)

        tools = [
            {"name": "get_appointments", "arguments": {"days": days}},
            {"name": "get_appointment_stats", "arguments": {"days": days}},
        ]

        fetch_result = await fetch_with_smart_retry(
            source_name=source_name,
            fetch_func=lambda: self._call_mcp_tools_batch("afspraak-db", tools),
            context={"mcp_dir": str(self._mcp_dir)},
            max_retries=3,
            circuit_threshold=5,
            circuit_cooldown=120.0
        )

        if not fetch_result["success"]:
            diagnosis = fetch_result.get("diagnosis", {})
            logger.error("appointments_fetch_failed", error=fetch_result.get("error"), category=diagnosis.get("category"))

            state["appointments_data"] = {"source": source_name, "error": fetch_result.get("error"), "diagnosis": diagnosis}
            state["errors"].append(fetch_result.get("error", "Unknown error"))
            self.error_aggregator.add_error(source_name, fetch_result.get("error", "Unknown"), attempts=fetch_result.get("attempts", 1))
            state = self.add_step(state, "fetch_appointments")
            return state

        results = fetch_result["data"]
        appointments = results[0] if len(results) > 0 else {}
        stats = results[1] if len(results) > 1 else {}

        data = {
            "source": "afspraak_db",
            "period_days": days,
            "total_appointments": stats.get("total_appointments", 0),
            "gclid_attributed": stats.get("with_gclid", 0),
            "fbclid_attributed": stats.get("with_fbclid", 0),
            "with_visitor_id": stats.get("with_visitor_id", 0),
            "by_source": stats.get("by_source", []),
            "appointments": appointments.get("appointments", []),
            "error": None,
            "fetch_attempts": fetch_result.get("attempts", 1)
        }

        self.error_aggregator.add_success(source_name)
        state["appointments_data"] = data
        state = self.add_step(state, "fetch_appointments")
        logger.info("appointments_fetched", days=days, brand=brand, attempts=fetch_result.get("attempts"))

        return state

    # =========================================================================
    # PER-SOURCE ANALYSIS NODES (8 LLM calls)
    # =========================================================================

    async def _send_source_telegram(
        self,
        source_name: str,
        icon: str,
        report: str,
        source_index: int = 0
    ) -> bool:
        """
        Send individual source analysis to Telegram immediately.

        Args:
            source_name: Display name (e.g., "Google Ads")
            icon: Emoji icon for the source
            report: LLM analysis markdown report
            source_index: Source number (1-8)

        Returns:
            True if sent successfully
        """
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN_ANALYTICS")
            chat_id = os.getenv("TELEGRAM_CHAT_ID_ANALYTICS")

            if not bot_token or not chat_id:
                logger.warning("telegram_config_missing_for_source", source=source_name)
                return False

            # Format message with source header
            message = f"{icon} **{source_name}** ({source_index}/8)\n\n{report}"

            # Truncate if too long (Telegram limit is 4096)
            if len(message) > 4000:
                message = message[:3950] + "\n\n... (kırpıldı)"

            async with httpx.AsyncClient() as client:
                # Try with Markdown first
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": "Markdown"
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    logger.info("source_telegram_sent", source=source_name, index=source_index)
                    return True
                elif response.status_code == 400:
                    # Markdown parsing failed, retry without parse_mode (plain text)
                    logger.warning("telegram_markdown_failed_retrying_plain", source=source_name)
                    response = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": message
                        },
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        logger.info("source_telegram_sent_plain", source=source_name, index=source_index)
                        return True
                    else:
                        logger.error("source_telegram_failed", source=source_name, status=response.status_code)
                        return False
                else:
                    logger.error("source_telegram_failed", source=source_name, status=response.status_code)
                    return False

        except Exception as e:
            logger.error("source_telegram_error", source=source_name, error=str(e))
            return False

    async def _run_source_analysis(
        self,
        source_name: str,
        data: Dict[str, Any],
        expert_role: str,
        analysis_focus: str
    ) -> str:
        """
        Run full LLM analysis for a data source.

        Args:
            source_name: Name of the source (e.g., "Google Ads")
            data: Data dictionary from fetch node
            expert_role: Expert role for Claude (e.g., "Google Ads uzmanı")
            analysis_focus: Specific focus areas for this source

        Returns:
            Turkish markdown sub-report
        """
        # Check if there's an error in the data
        has_error = data.get("error") is not None
        is_empty = not data or (not has_error and all(
            v in [0, None, [], {}]
            for k, v in data.items()
            if k not in ["source", "error", "period_days"]
        ))

        prompt = f"""Sen bir {expert_role}sin. Aşağıdaki {source_name} verisini detaylı analiz et.

VERİ:
{json.dumps(data, indent=2, default=str, ensure_ascii=False)}

ANALİZ GEREKSİNİMLERİ:

## 1. VERİ DURUMU
- Veri başarıyla geldi mi?
- Error var mı? Varsa ne?
- Kritik metrikler sıfır veya boş mu?

## 2. EĞER VERİ SORUNLUYSA
Olası nedenler:
- API credentials eksik/hatalı mı?
- Token expired mı?
- Account/kampanya aktif değil mi?
- Date range sorunu mu?
- MCP server çalışıyor mu?

## 3. VERİ ÖZETİ (veri varsa)
{analysis_focus}

## 4. ÖNERİLER
- Acil aksiyon gerekiyor mu?
- İyileştirme önerileri

KURALLAR:
- TÜRKÇE yaz
- KISA ve ÖZ ol (max 15 satır)
- Markdown formatında yaz
- Emoji kullan (✅ ⚠️ ❌ 📊 💡)
- Sorun varsa YÜKSEK ÖNCELİK olarak belirt"""

        if not CLAUDE_SDK_AVAILABLE:
            return f"⚠️ LLM analizi yapılamadı (Claude SDK yok)\n\nVeri: {json.dumps(data, indent=2, default=str)[:500]}"

        try:
            response = ""
            async for msg in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    max_turns=1,
                    permission_mode="bypassPermissions"
                )
            ):
                if hasattr(msg, 'content'):
                    for block in msg.content:
                        if hasattr(block, 'text'):
                            response += block.text

            return response if response else f"⚠️ LLM yanıt vermedi\n\nVeri: {json.dumps(data, indent=2, default=str)[:300]}"

        except Exception as e:
            logger.error(f"source_analysis_error", source=source_name, error=str(e))
            return f"❌ LLM analizi başarısız: {str(e)}\n\nVeri: {json.dumps(data, indent=2, default=str)[:300]}"

    async def analyze_google_ads_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze Google Ads data with full LLM analysis and send to Telegram."""
        try:
            data = state.get("google_ads_data", {}) or {}

            report = await self._run_source_analysis(
                source_name="Google Ads",
                data=data,
                expert_role="Google Ads uzmanı",
                analysis_focus="""- Toplam harcama: €X
- Toplam tıklama ve CTR
- CPC trendi
- En iyi kampanya performansı
- Conversion sayısı ve maliyeti
- Keyword kalitesi"""
            )

            if "source_reports" not in state:
                state["source_reports"] = {}
            state["source_reports"]["google_ads"] = report
            state = self.add_step(state, "analyze_google_ads")

            # Send to Telegram immediately
            await self._send_source_telegram("Google Ads", "📈", report, 1)

            logger.info("google_ads_analyzed", report_length=len(report))

        except Exception as e:
            logger.error("analyze_google_ads_error", error=str(e))
            state["source_reports"]["google_ads"] = f"❌ Analiz hatası: {str(e)}"

        return state

    async def analyze_meta_ads_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze Meta Ads data with full LLM analysis and send to Telegram."""
        try:
            data = state.get("meta_ads_data", {}) or {}

            report = await self._run_source_analysis(
                source_name="Meta Ads (Facebook/Instagram)",
                data=data,
                expert_role="Meta Ads uzmanı",
                analysis_focus="""- Toplam harcama: €X
- Reach ve impressions
- CTR ve CPM
- En iyi kampanya
- Audience performansı
- Creative insights"""
            )

            if "source_reports" not in state:
                state["source_reports"] = {}
            state["source_reports"]["meta_ads"] = report
            state = self.add_step(state, "analyze_meta_ads")

            # Send to Telegram immediately
            await self._send_source_telegram("Meta Ads", "📘", report, 2)

            logger.info("meta_ads_analyzed", report_length=len(report))

        except Exception as e:
            logger.error("analyze_meta_ads_error", error=str(e))
            state["source_reports"]["meta_ads"] = f"❌ Analiz hatası: {str(e)}"

        return state

    async def analyze_visitor_tracking_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze Visitor Tracking data with full LLM analysis and send to Telegram."""
        try:
            data = state.get("visitor_tracking_data", {}) or {}

            report = await self._run_source_analysis(
                source_name="Visitor Tracking (Custom DB)",
                data=data,
                expert_role="Web analytics uzmanı",
                analysis_focus="""- Toplam session ve unique visitor
- GCLID/FBCLID attribution oranı
- Median session süresi (ORTALAMA DEĞİL!)
- Top landing page'ler
- Traffic source dağılımı
- Conversion tracking durumu"""
            )

            if "source_reports" not in state:
                state["source_reports"] = {}
            state["source_reports"]["visitor_tracking"] = report
            state = self.add_step(state, "analyze_visitor_tracking")

            # Send to Telegram immediately
            await self._send_source_telegram("Visitor Tracking", "🌐", report, 3)

            logger.info("visitor_tracking_analyzed", report_length=len(report))

        except Exception as e:
            logger.error("analyze_visitor_tracking_error", error=str(e))
            state["source_reports"]["visitor_tracking"] = f"❌ Analiz hatası: {str(e)}"

        return state

    async def analyze_ga4_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze GA4 data with full LLM analysis and send to Telegram."""
        try:
            data = state.get("ga4_data", {}) or {}

            report = await self._run_source_analysis(
                source_name="Google Analytics 4",
                data=data,
                expert_role="GA4 analytics uzmanı",
                analysis_focus="""- Users ve sessions
- New vs returning users
- Bounce rate
- Avg session duration
- Top pages
- Traffic sources karşılaştırması"""
            )

            if "source_reports" not in state:
                state["source_reports"] = {}
            state["source_reports"]["ga4"] = report
            state = self.add_step(state, "analyze_ga4")

            # Send to Telegram immediately
            await self._send_source_telegram("Google Analytics 4", "📊", report, 4)

            logger.info("ga4_analyzed", report_length=len(report))

        except Exception as e:
            logger.error("analyze_ga4_error", error=str(e))
            state["source_reports"]["ga4"] = f"❌ Analiz hatası: {str(e)}"

        return state

    async def analyze_search_console_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze Search Console data with full LLM analysis and send to Telegram."""
        try:
            data = state.get("search_console_data", {}) or {}

            report = await self._run_source_analysis(
                source_name="Google Search Console",
                data=data,
                expert_role="SEO uzmanı",
                analysis_focus="""- Organic clicks ve impressions
- Ortalama CTR
- Ortalama pozisyon
- Top performing queries
- Top pages
- Pozisyon değişimleri"""
            )

            if "source_reports" not in state:
                state["source_reports"] = {}
            state["source_reports"]["search_console"] = report
            state = self.add_step(state, "analyze_search_console")

            # Send to Telegram immediately
            await self._send_source_telegram("Search Console", "🔍", report, 5)

            logger.info("search_console_analyzed", report_length=len(report))

        except Exception as e:
            logger.error("analyze_search_console_error", error=str(e))
            state["source_reports"]["search_console"] = f"❌ Analiz hatası: {str(e)}"

        return state

    async def analyze_merchant_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze Merchant Center data with full LLM analysis and send to Telegram."""
        try:
            data = state.get("merchant_data", {}) or {}

            report = await self._run_source_analysis(
                source_name="Google Merchant Center",
                data=data,
                expert_role="E-commerce ve feed uzmanı",
                analysis_focus="""- Toplam ürün sayısı
- Approved vs disapproved ürünler
- Health score
- Top performing products
- Feed issues ve warnings
- Click/impression performansı"""
            )

            if "source_reports" not in state:
                state["source_reports"] = {}
            state["source_reports"]["merchant_center"] = report
            state = self.add_step(state, "analyze_merchant")

            # Send to Telegram immediately
            await self._send_source_telegram("Merchant Center", "🛒", report, 6)

            logger.info("merchant_analyzed", report_length=len(report))

        except Exception as e:
            logger.error("analyze_merchant_error", error=str(e))
            state["source_reports"]["merchant_center"] = f"❌ Analiz hatası: {str(e)}"

        return state

    async def analyze_shopify_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze Shopify data with full LLM analysis and send to Telegram."""
        try:
            data = state.get("shopify_data", {}) or {}

            # IMPORTANT: Truncate Shopify data to prevent "Argument list too long" error
            # Only send summary metrics, not full order/product lists
            truncated_data = {
                "source": data.get("source", "shopify"),
                "period_days": data.get("period_days", 7),
                "total_orders": data.get("total_orders", 0),
                "total_revenue": data.get("total_revenue", 0),
                "average_order_value": data.get("average_order_value", 0),
                "new_customers": data.get("new_customers", 0),
                "returning_customers": data.get("returning_customers", 0),
                "abandoned_carts": data.get("abandoned_carts", 0),
                # Only include top 5 products (truncated)
                "top_products": [
                    {"title": p.get("title", ""), "variants_count": len(p.get("variants", []))}
                    for p in (data.get("top_products", []) or [])[:5]
                ],
                "error": data.get("error")
            }

            report = await self._run_source_analysis(
                source_name="Shopify",
                data=truncated_data,
                expert_role="E-commerce ve satış uzmanı",
                analysis_focus="""- Toplam sipariş sayısı
- Toplam gelir (€)
- Average Order Value (AOV)
- New vs returning customers
- Top selling products
- Abandoned cart oranı"""
            )

            if "source_reports" not in state:
                state["source_reports"] = {}
            state["source_reports"]["shopify"] = report
            state = self.add_step(state, "analyze_shopify")

            # Send to Telegram immediately
            await self._send_source_telegram("Shopify", "💰", report, 7)

            logger.info("shopify_analyzed", report_length=len(report))

        except Exception as e:
            logger.error("analyze_shopify_error", error=str(e))
            state["source_reports"]["shopify"] = f"❌ Analiz hatası: {str(e)}"

        return state

    async def analyze_appointments_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """Analyze Appointments data with full LLM analysis and send to Telegram."""
        try:
            data = state.get("appointments_data", {}) or {}

            report = await self._run_source_analysis(
                source_name="Randevu Sistemi (Afspraak-DB)",
                data=data,
                expert_role="CRM ve randevu uzmanı",
                analysis_focus="""- Toplam randevu sayısı
- GCLID ile gelen randevular (Google Ads attribution)
- FBCLID ile gelen randevular (Meta attribution)
- Visitor ID eşleşme oranı
- Source bazlı dağılım
- Conversion funnel analizi"""
            )

            if "source_reports" not in state:
                state["source_reports"] = {}
            state["source_reports"]["appointments"] = report
            state = self.add_step(state, "analyze_appointments")

            # Send to Telegram immediately
            await self._send_source_telegram("Randevular", "📅", report, 8)

            logger.info("appointments_analyzed", report_length=len(report))

        except Exception as e:
            logger.error("analyze_appointments_error", error=str(e))
            state["source_reports"]["appointments"] = f"❌ Analiz hatası: {str(e)}"

        return state

    async def merge_reports_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """
        Create final summary report (9th message).

        Since each source report was already sent individually,
        this creates a concise executive summary with key metrics.

        Also includes error diagnostics if there were failures.
        """
        try:
            days = state["days"]
            brand = state["brand"]
            today = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Get error summary from aggregator
            error_summary = self.error_aggregator.get_summary()

            # If there are errors, send diagnostic message first
            if error_summary["failed"] > 0:
                diagnostic_msg = self.error_aggregator.format_for_telegram()
                await self._send_source_telegram(
                    "DIAGNOSTIC",
                    "🔧",
                    diagnostic_msg,
                    source_index=0  # Before final summary
                )
                logger.warning(
                    "diagnostic_sent",
                    failed_sources=error_summary["failed"],
                    successful_sources=error_summary["successful"]
                )

            # Extract key metrics for summary
            ga = state.get("google_ads_data", {}) or {}
            ma = state.get("meta_ads_data", {}) or {}
            vt = state.get("visitor_tracking_data", {}) or {}
            sh = state.get("shopify_data", {}) or {}
            mc = state.get("merchant_data", {}) or {}
            ap = state.get("appointments_data", {}) or {}

            # Calculate totals
            total_ad_spend = float(ga.get("total_spend", 0) or 0) + float(ma.get("total_spend", 0) or 0)
            total_revenue = float(sh.get("total_revenue", 0) or 0)
            total_orders = int(sh.get("total_orders", 0) or 0)
            total_sessions = int(vt.get("total_sessions", 0) or 0)
            total_appointments = int(ap.get("total_appointments", 0) or 0)
            roas = total_revenue / total_ad_spend if total_ad_spend > 0 else 0

            # Use error aggregator for accurate counts
            success_count = error_summary["successful"]
            error_count = error_summary["failed"]

            # Get circuit breaker status
            circuit_status = circuit_registry.get_all_status()
            open_circuits = [name for name, status in circuit_status.items() if status.get("state") == "open"]

            # Build concise final summary
            final_report = f"""🎯 **FİNAL ÖZET** (9/9)

📅 **{today}** | {brand.title()} | Son {days} gün

━━━━━━━━━━━━━━━━━━━━━━

💰 **HARCAMA & GELİR**
• Toplam Reklam: €{total_ad_spend:,.2f}
• Toplam Gelir: €{total_revenue:,.2f}
• ROAS: {roas:.1f}x

📊 **PERFORMANS**
• Sipariş: {total_orders}
• Session: {total_sessions:,}
• Randevu: {total_appointments}

📈 **GOOGLE ADS**
• Harcama: €{ga.get('total_spend', 0):,.2f}
• Tıklama: {ga.get('total_clicks', 0):,}
• CTR: {ga.get('avg_ctr', 0):.2f}%

📘 **META ADS**
• Harcama: €{ma.get('total_spend', 0):,.2f}
• Reach: {ma.get('total_reach', 0):,}

🛒 **MERCHANT CENTER**
• Toplam Ürün: {mc.get('total_products', 0):,}
• Onaylı: {mc.get('approved_products', 0):,}
• Reddedilen: {mc.get('disapproved_products', 0):,}
• Health: {mc.get('health_score', 0):.1f}%

━━━━━━━━━━━━━━━━━━━━━━

✅ Başarılı: {success_count}/8 kaynak
❌ Hatalı: {error_count}/8 kaynak
{"🔴 Devre Dışı: " + ", ".join(open_circuits) if open_circuits else ""}

🤖 *Detaylı analizler yukarıdaki mesajlarda.*
{f"⚠️ *{error_count} kaynak hatalı - diagnostic mesajı gönderildi*" if error_count > 0 else ""}
"""

            state["report_markdown"] = final_report
            state = self.add_step(state, "merge_reports")

            logger.info("final_summary_created", sources_success=success_count, sources_error=error_count)

        except Exception as e:
            error_msg = f"Final summary failed: {str(e)}"
            state["errors"].append(error_msg)
            state["report_markdown"] = f"❌ Özet oluşturulamadı: {str(e)}"
            logger.error("merge_reports_error", error=str(e))

        return state

    async def save_data_node(self, state: DailyAnalyticsState) -> DailyAnalyticsState:
        """
        Save collected data and analysis to persistent storage.

        This node saves:
        1. Raw data from all 8 sources
        2. LLM analysis reports
        3. Final summary
        4. Metadata (timestamps, quality scores, etc.)

        Storage:
        - JSON file: agent_outputs/daily_analytics/YYYY-MM-DD_{brand}.json
        - Memory-Hub: analytics_data card (if available)
        - Data hash for duplicate detection

        Flow: merge_reports -> save_data -> send_telegram
        """
        try:
            brand = state["brand"]
            days = state["days"]
            today = datetime.now().strftime("%Y-%m-%d")
            timestamp = datetime.now().isoformat()

            # Compile all data into a comprehensive structure
            data_to_save = {
                "metadata": {
                    "brand": brand,
                    "period_days": days,
                    "collection_date": today,
                    "collection_timestamp": timestamp,
                    "graph_version": "v3",
                    "steps_completed": state.get("steps_completed", [])
                },
                "raw_data": {
                    "google_ads": state.get("google_ads_data", {}),
                    "meta_ads": state.get("meta_ads_data", {}),
                    "visitor_tracking": state.get("visitor_tracking_data", {}),
                    "ga4": state.get("ga4_data", {}),
                    "search_console": state.get("search_console_data", {}),
                    "merchant_center": state.get("merchant_data", {}),
                    "shopify": state.get("shopify_data", {}),
                    "appointments": state.get("appointments_data", {})
                },
                "analysis_reports": state.get("source_reports", {}),
                "final_summary": state.get("report_markdown", ""),
                "quality": {
                    "sources_success": sum(
                        1 for k, v in state.items()
                        if k.endswith("_data") and isinstance(v, dict) and not v.get("error")
                    ),
                    "sources_error": sum(
                        1 for k, v in state.items()
                        if k.endswith("_data") and isinstance(v, dict) and v.get("error")
                    ),
                    "errors": state.get("errors", [])
                },
                "aggregated_metrics": self._calculate_aggregated_metrics(state)
            }

            # Generate data hash for duplicate detection
            hash_input = f"{brand}:{today}:{days}"
            data_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
            data_to_save["metadata"]["data_hash"] = data_hash

            # === 1. Save to JSON file ===
            AGENT_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            json_filename = f"{today}_{brand}.json"
            json_path = AGENT_OUTPUTS_DIR / json_filename

            # Check if file already exists (duplicate detection)
            if json_path.exists():
                logger.warning(
                    "save_data_existing_file",
                    path=str(json_path),
                    action="overwriting"
                )
                # Keep backup of previous data
                backup_path = AGENT_OUTPUTS_DIR / f"{today}_{brand}_backup_{timestamp.replace(':', '-')}.json"
                json_path.rename(backup_path)

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False, default=str)

            logger.info(
                "data_saved_to_json",
                path=str(json_path),
                size_bytes=json_path.stat().st_size
            )

            # === 2. Save to Memory-Hub (if available) ===
            memory_hub_saved = await self._save_to_memory_hub(data_to_save)

            # Update state with save status
            state["data_saved"] = True
            state["data_save_path"] = str(json_path)
            state["data_hash"] = data_hash
            state["memory_hub_saved"] = memory_hub_saved
            state = self.add_step(state, "save_data")

            logger.info(
                "save_data_complete",
                json_path=str(json_path),
                memory_hub=memory_hub_saved,
                data_hash=data_hash
            )

        except Exception as e:
            error_msg = f"Data save failed: {str(e)}"
            state["errors"].append(error_msg)
            state["data_saved"] = False
            logger.error("save_data_error", error=str(e))

        return state

    def _calculate_aggregated_metrics(self, state: DailyAnalyticsState) -> Dict[str, Any]:
        """Calculate aggregated metrics from all sources."""
        try:
            ga = state.get("google_ads_data", {}) or {}
            ma = state.get("meta_ads_data", {}) or {}
            vt = state.get("visitor_tracking_data", {}) or {}
            sh = state.get("shopify_data", {}) or {}
            mc = state.get("merchant_data", {}) or {}
            ap = state.get("appointments_data", {}) or {}

            total_ad_spend = float(ga.get("total_spend", 0) or 0) + float(ma.get("total_spend", 0) or 0)
            total_revenue = float(sh.get("total_revenue", 0) or 0)
            total_orders = int(sh.get("total_orders", 0) or 0)
            total_sessions = int(vt.get("total_sessions", 0) or 0)
            total_appointments = int(ap.get("total_appointments", 0) or 0)

            roas = total_revenue / total_ad_spend if total_ad_spend > 0 else 0
            cpa = total_ad_spend / total_orders if total_orders > 0 else 0

            return {
                "total_ad_spend": total_ad_spend,
                "total_revenue": total_revenue,
                "total_orders": total_orders,
                "total_sessions": total_sessions,
                "total_appointments": total_appointments,
                "roas": round(roas, 2),
                "cpa": round(cpa, 2),
                "aov": round(total_revenue / total_orders, 2) if total_orders > 0 else 0,
                "google_ads": {
                    "spend": float(ga.get("total_spend", 0) or 0),
                    "clicks": int(ga.get("total_clicks", 0) or 0),
                    "conversions": float(ga.get("total_conversions", 0) or 0),
                    "ctr": float(ga.get("avg_ctr", 0) or 0)
                },
                "meta_ads": {
                    "spend": float(ma.get("total_spend", 0) or 0),
                    "reach": int(ma.get("total_reach", 0) or 0),
                    "clicks": int(ma.get("total_clicks", 0) or 0)
                },
                "merchant_center": {
                    "total_products": int(mc.get("total_products", 0) or 0),
                    "approved": int(mc.get("approved_products", 0) or 0),
                    "disapproved": int(mc.get("disapproved_products", 0) or 0),
                    "health_score": float(mc.get("health_score", 0) or 0)
                }
            }
        except Exception as e:
            logger.error("calculate_aggregated_metrics_error", error=str(e))
            return {}

    async def _save_to_memory_hub(self, data: Dict[str, Any]) -> bool:
        """
        Save analytics data to Memory-Hub via MCP.

        Creates a memory_card with type 'analytics_data' for later retrieval
        and cross-reference with other data sources.

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Try to call Memory-Hub MCP server
            result = await self._call_mcp_tool(
                "memory-hub",
                "memory_create",
                {
                    "type": "analytics_data",
                    "title": f"Daily Analytics - {data['metadata']['brand']} - {data['metadata']['collection_date']}",
                    "content": json.dumps({
                        "summary": data.get("final_summary", "")[:2000],  # Truncate for memory card
                        "aggregated_metrics": data.get("aggregated_metrics", {}),
                        "quality": data.get("quality", {})
                    }, ensure_ascii=False),
                    "project": data["metadata"]["brand"],
                    "tags": [
                        "analytics",
                        "daily-report",
                        data["metadata"]["brand"],
                        data["metadata"]["collection_date"]
                    ],
                    "data_source": "daily_analytics_graph",
                    "data_date": data["metadata"]["collection_date"],
                    "data_hash": data["metadata"]["data_hash"]
                }
            )

            if result.get("error"):
                logger.warning("memory_hub_save_failed", error=result.get("error"))
                return False

            logger.info("memory_hub_saved", card_id=result.get("id"))
            return True

        except Exception as e:
            logger.warning("memory_hub_save_error", error=str(e))
            return False

    # =========================================================================
    # PROCESSING NODES (Legacy - keeping for backward compatibility)
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
                    options=ClaudeAgentOptions(
                        max_turns=1,
                        permission_mode="bypassPermissions"
                    )
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
                    options=ClaudeAgentOptions(
                        max_turns=1,
                        permission_mode="bypassPermissions"
                    )
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
                spend = ga.get('total_spend', 0)
                clicks = ga.get('total_clicks', 0)
                conversions = ga.get('total_conversions', 0)
                report += f"| Google Ads Harcama | €{spend:,.2f} |\n"
                report += f"| Google Ads Tik | {clicks:,} |\n"
                report += f"| Google Ads CTR | {ga.get('avg_ctr', 0):.2f}% |\n"
                report += f"| Google Ads Conversion | {conversions:,.1f} |\n"

            # Meta Ads
            ma = sources.get("meta_ads", {})
            if ma and not ma.get("error"):
                report += f"| Meta Ads Harcama | €{ma.get('total_spend', 0):,.2f} |\n"
                report += f"| Meta Ads Erisim | {ma.get('total_reach', 0):,} |\n"
                report += f"| Meta Ads Tik | {ma.get('total_clicks', 0):,} |\n"

            # Visitor Tracking
            vt = sources.get("visitor_tracking", {})
            if vt and not vt.get("error"):
                report += f"| Site Oturumu | {vt.get('total_sessions', 0):,} |\n"
                report += f"| Benzersiz Ziyaretci | {vt.get('unique_visitors', 0):,} |\n"
                report += f"| GCLID Oturum | {vt.get('gclid_sessions', 0):,} |\n"

            # Shopify
            sh = sources.get("shopify", {})
            if sh and not sh.get("error"):
                orders = sh.get('total_orders', 0)
                revenue = sh.get('total_revenue', 0)
                aov = revenue / orders if orders > 0 else 0
                report += f"| Siparis | {orders:,} |\n"
                report += f"| Gelir | €{revenue:,.2f} |\n"
                report += f"| AOV | €{aov:,.2f} |\n"

            # Merchant Center
            mc = sources.get("merchant_center", {})
            if mc and not mc.get("error"):
                report += f"| Toplam Urun | {mc.get('total_products', 0):,} |\n"
                report += f"| Onayli Urun | {mc.get('approved_products', 0):,} |\n"
                report += f"| Reddedilen | {mc.get('disapproved_products', 0):,} |\n"
                report += f"| Merchant Health | {mc.get('health_score', 0):.1f}% |\n"

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

            # Get Telegram config (separate from email bot)
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN_ANALYTICS")
            chat_id = os.getenv("TELEGRAM_CHAT_ID_ANALYTICS")

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
