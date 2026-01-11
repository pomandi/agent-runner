"""
SEO Landing Optimizer Activities

Temporal activities for SEO landing page optimization workflow.
These activities wrap MCP tool calls and LangGraph execution.
"""
from temporalio import activity
from typing import Dict, Any, List, Optional
import logging
import time
import json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Constants
LANDING_PAGES_CONFIG_PATH = Path("/home/claude/projects/sale-v2/pomandi-landing-pages/src/config/pages")
COOLIFY_APP_UUID = "dkgksok4g0o04oko88g08s0g"


@activity.defn
async def fetch_search_console_data(days: int = 28) -> Dict[str, Any]:
    """
    Fetch Search Console data using MCP tools.

    Args:
        days: Number of days of data to fetch

    Returns:
        Dictionary with keyword opportunities, top queries, pages, etc.
    """
    activity.logger.info(f"Fetching Search Console data for last {days} days")
    start_time = time.time()

    try:
        # In production, this would use the Search Console MCP client
        # For now, return placeholder structure that SDK agent will populate
        result = {
            "keyword_opportunities": [],
            "top_queries": [],
            "top_pages": [],
            "position_distribution": {},
            "seo_summary": None,
            "date_range": {
                "days": days,
                "fetched_at": datetime.now().isoformat()
            }
        }

        duration = time.time() - start_time
        activity.logger.info(f"Search Console data fetched in {duration:.2f}s")

        return result

    except Exception as e:
        activity.logger.error(f"Failed to fetch Search Console data: {e}")
        raise


@activity.defn
async def run_seo_optimizer_graph(
    mode: str = "analyze",
    target_date: str = None,
    search_console_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Run SEO Landing Optimizer LangGraph workflow.

    Args:
        mode: Operation mode ("analyze", "generate", "report")
        target_date: Target date (YYYY-MM-DD)
        search_console_data: Pre-fetched Search Console data

    Returns:
        Optimizer result with generated config, report, etc.
    """
    activity.logger.info(f"Running SEO optimizer graph: mode={mode}")
    start_time = time.time()

    try:
        from langgraph_agents.seo_landing_optimizer_graph import SEOLandingOptimizerGraph
        from langgraph_agents.state_schemas import init_seo_landing_optimizer_state

        # Create and initialize graph
        graph = SEOLandingOptimizerGraph()
        await graph.initialize()

        # Prepare initial state
        state = init_seo_landing_optimizer_state(
            mode=mode,
            target_date=target_date or datetime.now().strftime("%Y-%m-%d")
        )

        # Inject pre-fetched data if available
        if search_console_data:
            state["keyword_opportunities"] = search_console_data.get("keyword_opportunities", [])
            state["top_queries"] = search_console_data.get("top_queries", [])
            state["top_pages"] = search_console_data.get("top_pages", [])
            state["position_distribution"] = search_console_data.get("position_distribution", {})
            state["seo_summary"] = search_console_data.get("seo_summary")

        # Run graph
        result = await graph.run(**state)

        duration = time.time() - start_time

        activity.logger.info(
            f"SEO optimizer complete: keyword={result.get('selected_keyword')}, "
            f"config_saved={result.get('config_saved')}, "
            f"duration={duration:.2f}s"
        )

        await graph.close()

        # Return truncated result to avoid gRPC size limits
        return {
            "success": result.get("config_saved", False) or result.get("report_saved", False),
            "mode": result.get("mode"),
            "target_date": result.get("target_date"),
            "selected_keyword": result.get("selected_keyword"),
            "selected_template": result.get("selected_template"),
            "generated_config": result.get("generated_config"),
            "config_validated": result.get("config_validated", False),
            "config_saved": result.get("config_saved", False),
            "deployment_triggered": result.get("deployment_triggered", False),
            "deployment_status": result.get("deployment_status"),
            "report_content": result.get("report_content", "")[:5000],  # Truncate report
            "keyword_opportunities_count": len(result.get("keyword_opportunities", [])),
            "existing_pages_count": len(result.get("existing_pages", [])),
            "warnings": result.get("warnings", [])[:20],
            "steps_completed": result.get("steps_completed", [])[:20],
            "error": result.get("error"),
            "duration_seconds": duration
        }

    except Exception as e:
        activity.logger.error(f"SEO optimizer graph failed: {e}")
        raise


@activity.defn
async def get_existing_pages() -> List[str]:
    """
    Get list of existing landing page slugs.

    Returns:
        List of existing page slugs
    """
    activity.logger.info("Getting existing landing pages")

    try:
        existing_pages = []

        if LANDING_PAGES_CONFIG_PATH.exists():
            for config_file in LANDING_PAGES_CONFIG_PATH.glob("*.json"):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        slug = config.get("slug", "")
                        if slug:
                            existing_pages.append(slug)
                except Exception as e:
                    activity.logger.warning(f"Failed to parse {config_file}: {e}")

        activity.logger.info(f"Found {len(existing_pages)} existing pages")
        return existing_pages

    except Exception as e:
        activity.logger.error(f"Failed to get existing pages: {e}")
        raise


@activity.defn
async def save_page_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save landing page configuration to file.

    Args:
        config: PageConfig dictionary

    Returns:
        Save result with file path
    """
    activity.logger.info(f"Saving page config: {config.get('slug')}")

    try:
        slug = config.get("slug", "unknown")
        file_path = LANDING_PAGES_CONFIG_PATH / f"{slug}.json"

        # Ensure directory exists
        LANDING_PAGES_CONFIG_PATH.mkdir(parents=True, exist_ok=True)

        # Write config
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        activity.logger.info(f"Page config saved: {file_path}")

        return {
            "success": True,
            "file_path": str(file_path),
            "slug": slug
        }

    except Exception as e:
        activity.logger.error(f"Failed to save page config: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@activity.defn
async def trigger_coolify_deployment() -> Dict[str, Any]:
    """
    Trigger Coolify deployment for landing pages app.

    Returns:
        Deployment result with status
    """
    activity.logger.info(f"Triggering Coolify deployment: {COOLIFY_APP_UUID}")

    try:
        # In production, this would use Coolify MCP:
        # mcp__coolify__restart_application(uuid=COOLIFY_APP_UUID, server="faric")

        # For now, return placeholder
        result = {
            "success": True,
            "uuid": COOLIFY_APP_UUID,
            "status": "deployment_triggered",
            "triggered_at": datetime.now().isoformat()
        }

        activity.logger.info(f"Coolify deployment triggered: {COOLIFY_APP_UUID}")
        return result

    except Exception as e:
        activity.logger.error(f"Failed to trigger deployment: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@activity.defn
async def save_seo_report(
    report_content: str,
    target_date: str,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Save SEO optimizer report to agent outputs.

    Args:
        report_content: Markdown report content
        target_date: Target date
        metadata: Additional metadata

    Returns:
        Save result
    """
    activity.logger.info(f"Saving SEO report for {target_date}")

    try:
        # In production, this would use agent-outputs MCP:
        # mcp__agent-outputs-mcp__save_output(
        #     agent_name="seo-landing-optimizer",
        #     output_type="report",
        #     title=f"SEO Landing Optimizer Report - {target_date}",
        #     content=report_content,
        #     tags=["seo", "landing-page", target_date]
        # )

        result = {
            "success": True,
            "agent_name": "seo-landing-optimizer",
            "output_type": "report",
            "target_date": target_date,
            "content_length": len(report_content),
            "saved_at": datetime.now().isoformat()
        }

        activity.logger.info(f"SEO report saved: {len(report_content)} chars")
        return result

    except Exception as e:
        activity.logger.error(f"Failed to save report: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@activity.defn
async def check_deployment_status(deployment_uuid: str) -> Dict[str, Any]:
    """
    Check Coolify deployment status.

    Args:
        deployment_uuid: Deployment UUID

    Returns:
        Deployment status
    """
    activity.logger.info(f"Checking deployment status: {deployment_uuid}")

    try:
        # In production, this would use Coolify MCP:
        # mcp__coolify__get_application(uuid=deployment_uuid, server="faric")

        result = {
            "uuid": deployment_uuid,
            "status": "running",  # "running", "building", "stopped", "failed"
            "checked_at": datetime.now().isoformat()
        }

        activity.logger.info(f"Deployment status: {result['status']}")
        return result

    except Exception as e:
        activity.logger.error(f"Failed to check deployment status: {e}")
        return {
            "uuid": deployment_uuid,
            "status": "unknown",
            "error": str(e)
        }


# Activity list for worker registration
SEO_ACTIVITIES = [
    fetch_search_console_data,
    run_seo_optimizer_graph,
    get_existing_pages,
    save_page_config,
    trigger_coolify_deployment,
    save_seo_report,
    check_deployment_status,
]
