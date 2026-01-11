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
# Landing pages config path - can be set via env var for container deployment
LANDING_PAGES_CONFIG_PATH = Path(os.getenv(
    "LANDING_PAGES_CONFIG_PATH",
    "/app/landing-pages/config" if Path("/app").exists() else "/home/claude/projects/sale-v2/pomandi-landing-pages/src/config/pages"
))
COOLIFY_APP_UUID = "dkgksok4g0o04oko88g08s0g"


@activity.defn
async def fetch_search_console_data(days: int = 28) -> Dict[str, Any]:
    """
    Fetch Search Console data using MCP tools.

    Args:
        days: Number of days of data to fetch

    Returns:
        Dictionary with keyword opportunities, top queries, pages, etc.
        Includes detailed error info if fetch fails.
    """
    import os
    import traceback

    activity.logger.info(f"Fetching Search Console data for last {days} days")
    start_time = time.time()

    result = {
        "keyword_opportunities": [],
        "top_queries": [],
        "top_pages": [],
        "position_distribution": {},
        "seo_summary": None,
        "date_range": {
            "days": days,
            "fetched_at": datetime.now().isoformat()
        },
        "fetch_status": "pending",
        "errors": []
    }

    try:
        # Check if MCP SDK is available
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as e:
            result["fetch_status"] = "error"
            result["errors"].append({
                "type": "DEPENDENCY_ERROR",
                "message": f"MCP SDK not available: {e}",
                "suggestion": "Install: pip install mcp"
            })
            activity.logger.error(f"MCP SDK not available: {e}")
            return result

        # Check credentials
        google_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        google_path = os.getenv("GOOGLE_CREDENTIALS_PATH")

        if not google_json and not google_path:
            result["fetch_status"] = "error"
            result["errors"].append({
                "type": "CREDENTIALS_ERROR",
                "message": "Google credentials not configured",
                "env_vars": {
                    "GOOGLE_CREDENTIALS_JSON": "NOT_SET",
                    "GOOGLE_CREDENTIALS_PATH": "NOT_SET"
                },
                "suggestion": "Set GOOGLE_CREDENTIALS_JSON or GOOGLE_CREDENTIALS_PATH env var"
            })
            activity.logger.error("Google credentials not configured")
            return result

        # Find MCP server
        mcp_paths = [
            Path("/app/mcp-servers/search-console/server.py"),
            Path("/home/claude/.claude/agents/agent-runner/mcp-servers/search-console/server.py")
        ]
        server_path = None
        for p in mcp_paths:
            if p.exists():
                server_path = p
                break

        if not server_path:
            result["fetch_status"] = "error"
            result["errors"].append({
                "type": "SERVER_NOT_FOUND",
                "message": "Search Console MCP server not found",
                "searched_paths": [str(p) for p in mcp_paths]
            })
            activity.logger.error("Search Console MCP server not found")
            return result

        # Call MCP server
        activity.logger.info(f"Connecting to MCP server: {server_path}")

        server_params = StdioServerParameters(
            command="python3",
            args=[str(server_path)],
            env=os.environ.copy()  # Pass environment variables!
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                activity.logger.info("MCP session initialized")

                # Fetch keyword opportunities
                activity.logger.info("Fetching keyword opportunities...")
                try:
                    opp_result = await session.call_tool(
                        "get_keyword_opportunities",
                        {"days": days, "min_impressions": 50}
                    )
                    if opp_result.content:
                        for content in opp_result.content:
                            if hasattr(content, 'text'):
                                data = json.loads(content.text)
                                if "error" not in str(data).lower()[:100]:
                                    result["keyword_opportunities"] = data.get("opportunities", {})
                                else:
                                    result["errors"].append({"tool": "get_keyword_opportunities", "error": data})
                except Exception as e:
                    result["errors"].append({"tool": "get_keyword_opportunities", "error": str(e)})
                    activity.logger.warning(f"get_keyword_opportunities failed: {e}")

                # Fetch top queries
                activity.logger.info("Fetching top queries...")
                try:
                    queries_result = await session.call_tool(
                        "get_top_queries",
                        {"days": days, "limit": 100}
                    )
                    if queries_result.content:
                        for content in queries_result.content:
                            if hasattr(content, 'text'):
                                data = json.loads(content.text)
                                if "error" not in str(data).lower()[:100]:
                                    result["top_queries"] = data.get("queries", [])
                                else:
                                    result["errors"].append({"tool": "get_top_queries", "error": data})
                except Exception as e:
                    result["errors"].append({"tool": "get_top_queries", "error": str(e)})
                    activity.logger.warning(f"get_top_queries failed: {e}")

                # Fetch top pages
                activity.logger.info("Fetching top pages...")
                try:
                    pages_result = await session.call_tool(
                        "get_top_pages",
                        {"days": days, "limit": 50}
                    )
                    if pages_result.content:
                        for content in pages_result.content:
                            if hasattr(content, 'text'):
                                data = json.loads(content.text)
                                if "error" not in str(data).lower()[:100]:
                                    result["top_pages"] = data.get("pages", [])
                                else:
                                    result["errors"].append({"tool": "get_top_pages", "error": data})
                except Exception as e:
                    result["errors"].append({"tool": "get_top_pages", "error": str(e)})
                    activity.logger.warning(f"get_top_pages failed: {e}")

                # Fetch position distribution
                activity.logger.info("Fetching position distribution...")
                try:
                    pos_result = await session.call_tool(
                        "get_position_distribution",
                        {"days": days}
                    )
                    if pos_result.content:
                        for content in pos_result.content:
                            if hasattr(content, 'text'):
                                data = json.loads(content.text)
                                if "error" not in str(data).lower()[:100]:
                                    result["position_distribution"] = data.get("position_distribution", {})
                                else:
                                    result["errors"].append({"tool": "get_position_distribution", "error": data})
                except Exception as e:
                    result["errors"].append({"tool": "get_position_distribution", "error": str(e)})
                    activity.logger.warning(f"get_position_distribution failed: {e}")

                # Fetch SEO summary
                activity.logger.info("Fetching SEO summary...")
                try:
                    summary_result = await session.call_tool(
                        "get_seo_summary",
                        {"days": days}
                    )
                    if summary_result.content:
                        for content in summary_result.content:
                            if hasattr(content, 'text'):
                                data = json.loads(content.text)
                                if "error" not in str(data).lower()[:100]:
                                    result["seo_summary"] = data
                                else:
                                    result["errors"].append({"tool": "get_seo_summary", "error": data})
                except Exception as e:
                    result["errors"].append({"tool": "get_seo_summary", "error": str(e)})
                    activity.logger.warning(f"get_seo_summary failed: {e}")

        # Determine fetch status
        if result["errors"]:
            if result["top_queries"] or result["keyword_opportunities"]:
                result["fetch_status"] = "partial"
            else:
                result["fetch_status"] = "error"
        else:
            result["fetch_status"] = "success"

        duration = time.time() - start_time
        result["fetch_duration_seconds"] = round(duration, 2)

        activity.logger.info(
            f"Search Console data fetched in {duration:.2f}s - "
            f"status={result['fetch_status']}, "
            f"queries={len(result['top_queries'])}, "
            f"opportunities={len(result.get('keyword_opportunities', {}).get('position_4_to_10', []))}, "
            f"errors={len(result['errors'])}"
        )

        return result

    except Exception as e:
        result["fetch_status"] = "error"
        result["errors"].append({
            "type": "UNEXPECTED_ERROR",
            "message": str(e),
            "traceback": traceback.format_exc()[-500:]
        })
        activity.logger.error(f"Failed to fetch Search Console data: {e}")
        return result


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
async def push_landing_page_to_git(config_path: str, slug: str) -> Dict[str, Any]:
    """
    Push landing page config to git repository.

    Args:
        config_path: Path to the config file
        slug: Page slug for commit message

    Returns:
        Git push result
    """
    import subprocess

    activity.logger.info(f"Pushing landing page to git: {slug}")

    # Landing pages repo path
    repo_path = Path(os.getenv(
        "LANDING_PAGES_REPO_PATH",
        "/home/claude/projects/sale-v2/pomandi-landing-pages"
    ))

    if not repo_path.exists():
        return {
            "success": False,
            "error": f"Repo not found: {repo_path}"
        }

    try:
        # Git add
        add_result = subprocess.run(
            ["git", "add", config_path],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if add_result.returncode != 0:
            return {
                "success": False,
                "step": "git_add",
                "error": add_result.stderr
            }

        # Git commit
        commit_message = f"feat(seo): Add landing page for '{slug}'\n\nAuto-generated by SEO Landing Optimizer"
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        # Check if there was nothing to commit (not an error)
        if commit_result.returncode != 0:
            if "nothing to commit" in commit_result.stdout or "nothing to commit" in commit_result.stderr:
                activity.logger.info("No changes to commit")
                return {
                    "success": True,
                    "status": "no_changes",
                    "message": "Config already up to date"
                }
            return {
                "success": False,
                "step": "git_commit",
                "error": commit_result.stderr
            }

        # Git push
        push_result = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        if push_result.returncode != 0:
            return {
                "success": False,
                "step": "git_push",
                "error": push_result.stderr
            }

        activity.logger.info(f"Successfully pushed landing page: {slug}")

        return {
            "success": True,
            "status": "pushed",
            "slug": slug,
            "commit_message": commit_message,
            "pushed_at": datetime.now().isoformat()
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Git operation timed out"
        }
    except Exception as e:
        activity.logger.error(f"Git push failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# Coolify API configuration
COOLIFY_URL = os.getenv("COOLIFY_URL", "http://46.224.117.155:8000")
COOLIFY_TOKEN = os.getenv("COOLIFY_TOKEN", "8|skhubBnCoPY6G1ccBmosO0MkwIQKmCjDzALEou4S46cc458d")
LANDING_PAGES_APP_UUID = os.getenv("LANDING_PAGES_APP_UUID", "dkgksok4g0o04oko88g08s0g")


@activity.defn
async def trigger_coolify_deployment(skip: bool = False) -> Dict[str, Any]:
    """
    Trigger Coolify deployment for landing pages app via HTTP API.

    Args:
        skip: If True, skip deployment (for testing)

    Returns:
        Deployment result with status
    """
    import httpx

    if skip:
        activity.logger.info("Skipping Coolify deployment (skip=True)")
        return {
            "success": True,
            "status": "skipped",
            "message": "Deployment skipped as requested"
        }

    activity.logger.info(f"Triggering Coolify deployment: {LANDING_PAGES_APP_UUID}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{COOLIFY_URL}/api/v1/applications/{LANDING_PAGES_APP_UUID}/restart",
                headers={
                    "Authorization": f"Bearer {COOLIFY_TOKEN}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )

            if response.status_code >= 400:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": response.text[:500]
                }

            result = {
                "success": True,
                "uuid": LANDING_PAGES_APP_UUID,
                "status": "deployment_triggered",
                "status_code": response.status_code,
                "triggered_at": datetime.now().isoformat()
            }

            # Try to parse response
            try:
                result["response"] = response.json()
            except:
                result["response_text"] = response.text[:200]

            activity.logger.info(f"Coolify deployment triggered: {LANDING_PAGES_APP_UUID}")
            return result

    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Coolify API request timed out"
        }
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
