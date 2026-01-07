#!/usr/bin/env python3
"""
Agent Creator MCP Server
Creates standardized agents with proper MCP integrations, memory-hub, and agent-outputs.
IMPORTANT: Every agent MUST have its own MCP server - no agent creation without MCP!
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("agent-creator")

# Base paths
AGENTS_PATH = os.getenv("AGENTS_PATH", "/home/claude/.claude/agents")
MCP_SERVERS_PATH = os.getenv("MCP_SERVERS_PATH", "/home/claude/.claude/agents/unified-analytics/mcp-servers")
MCP_CONFIG_PATH = os.getenv("MCP_CONFIG_PATH", "/home/claude/.claude/agents/.mcp.json")

# Agent categories and their templates
AGENT_CATEGORIES = {
    "collector": {
        "description": "Data collection agents that gather data from APIs",
        "required_mcps": ["agent-outputs", "memory-hub"],
        "optional_mcps": ["google-ads", "meta-ads", "shopify", "analytics", "search-console", "merchant-center", "afspraak-db"],
        "model": "sonnet",
        "timeout": 1800,
        "default_tools": [
            {"name": "collect_data", "description": "Collect data from the source"},
            {"name": "get_status", "description": "Get collection status"}
        ]
    },
    "analyzer": {
        "description": "Analysis agents that process and analyze collected data",
        "required_mcps": ["agent-outputs", "memory-hub"],
        "optional_mcps": ["google-ads", "meta-ads", "analytics"],
        "model": "sonnet",
        "timeout": 3600,
        "default_tools": [
            {"name": "analyze", "description": "Run analysis on data"},
            {"name": "get_insights", "description": "Get analysis insights"}
        ]
    },
    "publisher": {
        "description": "Publishing agents that post content to social media",
        "required_mcps": ["agent-outputs", "memory-hub", "social-media-publish"],
        "optional_mcps": ["cloudflare-r2", "saleor"],
        "model": "sonnet",
        "timeout": 1200,
        "default_tools": [
            {"name": "publish", "description": "Publish content"},
            {"name": "schedule_post", "description": "Schedule a post for later"}
        ]
    },
    "generator": {
        "description": "Content generation agents (captions, images, etc.)",
        "required_mcps": ["agent-outputs", "memory-hub"],
        "optional_mcps": ["cloudflare-r2", "saleor"],
        "model": "sonnet",
        "timeout": 1800,
        "default_tools": [
            {"name": "generate", "description": "Generate content"},
            {"name": "get_templates", "description": "Get available templates"}
        ]
    },
    "orchestrator": {
        "description": "Orchestration agents that coordinate other agents",
        "required_mcps": ["agent-outputs", "memory-hub"],
        "optional_mcps": [],
        "model": "opus",
        "timeout": 7200,
        "default_tools": [
            {"name": "run_workflow", "description": "Run a multi-agent workflow"},
            {"name": "get_workflow_status", "description": "Get workflow status"}
        ]
    },
    "utility": {
        "description": "Utility agents for maintenance and system tasks",
        "required_mcps": ["agent-outputs", "memory-hub"],
        "optional_mcps": [],
        "model": "haiku",
        "timeout": 600,
        "default_tools": [
            {"name": "run_task", "description": "Run the utility task"},
            {"name": "get_status", "description": "Get task status"}
        ]
    }
}

# Standard agent.md template
AGENT_MD_TEMPLATE = '''---
name: {name}
description: {description}
model: {model}
---

# {name}

{description}

## Required MCP Servers

This agent MUST use the following MCP tools:

### 1. Agent's Own MCP Server ({mcp_name})
- Use `mcp__{mcp_name}__*` tools for agent-specific functionality
- This MCP provides the core capabilities for this agent

### 2. Memory Hub (Session Management)
- Start session: `mcp__memory-hub__session_start` at the beginning
- End session: `mcp__memory-hub__session_end` when complete
- Log notes: `mcp__memory-hub__session_note` for important findings
- Create memories: `mcp__memory-hub__memory_create` for bugs, decisions, runbooks

### 3. Agent Outputs (Result Storage)
- Save output: `mcp__agent-outputs__save_output` for all results
- Log execution: `mcp__agent-outputs__start_execution` / `complete_execution`

{additional_mcp_docs}

## Task Instructions

{task_instructions}

## Output Format

All outputs MUST be saved using `mcp__agent-outputs__save_output` with:
- `agent_name`: "{name}"
- `output_type`: "data" | "analysis" | "report" | "error"
- `title`: Descriptive title with date
- `content`: Markdown formatted content
- `tags`: ["{name}", "{category}", "YYYY-MM-DD"]

## Error Handling

If any error occurs:
1. Log error to memory-hub: `mcp__memory-hub__session_note`
2. Save error output: `mcp__agent-outputs__save_output` with type="error"
3. End session properly: `mcp__memory-hub__session_end` with error summary

## Session Workflow

```
1. START: mcp__memory-hub__session_start(project="{project}")
2. EXECUTE: Use mcp__{mcp_name}__* tools for main task
3. SAVE: mcp__agent-outputs__save_output(...)
4. END: mcp__memory-hub__session_end(summary="...")
```
'''

# Config.yaml template
CONFIG_YAML_TEMPLATE = '''# Agent Configuration
# Generated: {generated_at}
# Agent: {name}

name: {name}
category: {category}
description: {description}
model: {model}
mcp_server: {mcp_name}
capabilities:
{capabilities_yaml}
# All outputs go to PostgreSQL via agent-outputs MCP
# No local file storage
output_storage: database
timeout: {timeout}
tags:
{tags_yaml}
required_mcps:
{required_mcps_yaml}
learning:
  enabled: true
  share_insights: false
  track_metrics:
    - duration
    - items_processed
    - errors
'''

# MCP Server template
MCP_SERVER_TEMPLATE = '''#!/usr/bin/env python3
"""
{mcp_name} MCP Server
Agent: {agent_name}
Category: {category}
Generated: {generated_at}

{description}

NOTE: All outputs go to PostgreSQL via agent-outputs MCP.
No local file storage - use mcp__agent-outputs__save_output() for all results.
"""
import asyncio
import json
import logging
from datetime import datetime
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("{mcp_name}")

server = Server("{mcp_name}")


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
{tools_list}
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    logger.info(f"Tool called: {{name}} with arguments: {{arguments}}")

{tool_implementations}

    return [TextContent(type="text", text=json.dumps({{"error": f"Unknown tool: {{name}}"}}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
'''


def generate_mcp_name(agent_name: str) -> str:
    """Generate MCP server name from agent name."""
    # Remove common suffixes and create MCP name
    mcp_name = agent_name.replace("-agent", "").replace("-data-collector", "-mcp")
    if not mcp_name.endswith("-mcp"):
        mcp_name = f"{mcp_name}-mcp"
    return mcp_name


def generate_tool_code(tool: dict) -> tuple:
    """Generate tool definition and implementation code."""
    tool_name = tool.get("name", "tool")
    tool_desc = tool.get("description", "Tool description")
    tool_params = tool.get("parameters", {})

    # Tool definition
    tool_def = f'''        Tool(
            name="{tool_name}",
            description="{tool_desc}",
            inputSchema={{
                "type": "object",
                "properties": {json.dumps(tool_params)},
                "required": []
            }}
        ),'''

    # Tool implementation
    tool_impl = f'''    if name == "{tool_name}":
        # TODO: Implement {tool_name}
        result = {{
            "status": "success",
            "tool": "{tool_name}",
            "timestamp": datetime.now().isoformat(),
            "data": {{}}
        }}
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
'''

    return tool_def, tool_impl


def generate_mcp_server(mcp_name: str, agent_name: str, category: str,
                         description: str, tools: list) -> str:
    """Generate MCP server code."""
    cat_info = AGENT_CATEGORIES.get(category, AGENT_CATEGORIES["utility"])

    # Use provided tools or default tools for category
    if not tools:
        tools = cat_info.get("default_tools", [{"name": "run", "description": "Run the agent task"}])

    # Generate tool definitions and implementations
    tool_defs = []
    tool_impls = []

    for tool in tools:
        tool_def, tool_impl = generate_tool_code(tool)
        tool_defs.append(tool_def)
        tool_impls.append(tool_impl)

    tools_list = "\n".join(tool_defs)
    tool_implementations = "\n".join(tool_impls)

    return MCP_SERVER_TEMPLATE.format(
        mcp_name=mcp_name,
        agent_name=agent_name,
        category=category,
        description=description,
        generated_at=datetime.now().isoformat(),
        tools_list=tools_list,
        tool_implementations=tool_implementations
    )


def update_mcp_config(mcp_name: str, mcp_path: str) -> dict:
    """Update .mcp.json with new MCP server."""
    config_path = Path(MCP_CONFIG_PATH)

    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {"mcpServers": {}}

    # Add new MCP server
    config["mcpServers"][mcp_name] = {
        "command": "/home/claude/.mcp-venv/bin/python",
        "args": [mcp_path]
    }

    return config


def generate_agent_md(name: str, category: str, description: str,
                      capabilities: list, task_instructions: str,
                      project: str, mcp_name: str) -> str:
    """Generate agent.md content."""
    cat_info = AGENT_CATEGORIES.get(category, AGENT_CATEGORIES["utility"])

    # Build additional MCP docs based on capabilities
    additional_docs = []
    for cap in capabilities:
        if cap == "google-ads":
            additional_docs.append("""### Google Ads
- Use `mcp__google-ads__*` tools for all Google Ads API calls
- Never make direct API requests""")
        elif cap == "meta-ads":
            additional_docs.append("""### Meta Ads
- Use `mcp__meta-ads__*` tools for all Meta Ads API calls
- Never make direct API requests""")
        elif cap == "shopify":
            additional_docs.append("""### Shopify
- Use `mcp__shopify__*` tools for all Shopify API calls""")
        elif cap == "analytics":
            additional_docs.append("""### Google Analytics
- Use `mcp__analytics__*` tools for GA4 data""")
        elif cap == "cloudflare-r2":
            additional_docs.append("""### Cloudflare R2 (Image Storage)
- Use `mcp__cloudflare-r2__upload` for all image uploads
- Never store images locally""")

    additional_mcp_docs = "\n\n".join(additional_docs) if additional_docs else "No additional MCP servers required."

    return AGENT_MD_TEMPLATE.format(
        name=name,
        description=description,
        model=cat_info["model"],
        mcp_name=mcp_name,
        additional_mcp_docs=additional_mcp_docs,
        task_instructions=task_instructions or "Define your task instructions here.",
        category=category,
        project=project
    )


def generate_config_yaml(name: str, category: str, description: str,
                         capabilities: list, tags: list, mcp_name: str) -> str:
    """Generate config.yaml content."""
    cat_info = AGENT_CATEGORIES.get(category, AGENT_CATEGORIES["utility"])

    caps_yaml = "\n".join([f"  - {cap}" for cap in capabilities]) if capabilities else "  - general"
    tags_yaml = "\n".join([f"  - {tag}" for tag in tags]) if tags else f"  - {category}"
    required_mcps = "\n".join([f"  - {mcp}" for mcp in [mcp_name] + cat_info["required_mcps"]])

    return CONFIG_YAML_TEMPLATE.format(
        generated_at=datetime.now().isoformat(),
        name=name,
        category=category,
        description=description,
        model=cat_info["model"],
        mcp_name=mcp_name,
        capabilities_yaml=caps_yaml,
        timeout=cat_info["timeout"],
        tags_yaml=tags_yaml,
        required_mcps_yaml=required_mcps
    )


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
        Tool(
            name="create_agent",
            description="Create a new standardized agent WITH its MCP server. BOTH are created together - no agent without MCP!",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Agent name (e.g., 'google-ads-collector')"
                    },
                    "category": {
                        "type": "string",
                        "enum": list(AGENT_CATEGORIES.keys()),
                        "description": "Agent category"
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the agent does"
                    },
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of MCP capabilities needed (e.g., ['google-ads', 'analytics'])"
                    },
                    "task_instructions": {
                        "type": "string",
                        "description": "Specific task instructions for the agent"
                    },
                    "project": {
                        "type": "string",
                        "description": "Project name for memory-hub (default: marketing-agents)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional tags for the agent"
                    },
                    "mcp_tools": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "parameters": {"type": "object"}
                            }
                        },
                        "description": "Custom MCP tools for this agent. If not provided, default tools for category are used."
                    },
                    "save_to_disk": {
                        "type": "boolean",
                        "description": "If true, saves all files to disk. If false, just returns content."
                    }
                },
                "required": ["name", "category", "description"]
            }
        ),
        Tool(
            name="list_categories",
            description="List all available agent categories with their descriptions and requirements.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="validate_agent",
            description="Validate an existing agent against standards. Returns list of issues and recommendations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the agent to validate"
                    }
                },
                "required": ["agent_name"]
            }
        ),
        Tool(
            name="list_agents",
            description="List all existing agents with their categories and MCP status.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_mcp_template",
            description="Get a template for creating a new standalone MCP server.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mcp_name": {
                        "type": "string",
                        "description": "Name for the new MCP server"
                    },
                    "tools": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"}
                            }
                        },
                        "description": "List of tools the MCP should provide"
                    }
                },
                "required": ["mcp_name"]
            }
        ),
        Tool(
            name="get_standards",
            description="Get the full agent standards documentation.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""

    if name == "create_agent":
        agent_name = arguments["name"]
        category = arguments["category"]
        description = arguments["description"]
        capabilities = arguments.get("capabilities", [])
        task_instructions = arguments.get("task_instructions", "")
        project = arguments.get("project", "marketing-agents")
        tags = arguments.get("tags", [category])
        mcp_tools = arguments.get("mcp_tools", [])
        save_to_disk = arguments.get("save_to_disk", False)

        # Generate MCP name from agent name
        mcp_name = generate_mcp_name(agent_name)

        # Generate all content
        agent_md = generate_agent_md(agent_name, category, description,
                                     capabilities, task_instructions, project, mcp_name)
        config_yaml = generate_config_yaml(agent_name, category, description,
                                          capabilities, tags, mcp_name)
        mcp_server = generate_mcp_server(mcp_name, agent_name, category,
                                         description, mcp_tools)

        # MCP server path
        mcp_server_path = f"{MCP_SERVERS_PATH}/{mcp_name}/server.py"

        # Get updated MCP config
        updated_mcp_config = update_mcp_config(mcp_name, mcp_server_path)

        result = {
            "agent_name": agent_name,
            "mcp_name": mcp_name,
            "category": category,
            "files": {
                "agent.md": agent_md,
                "config.yaml": config_yaml,
                "mcp_server.py": mcp_server
            },
            "paths": {
                "agent_dir": f"{AGENTS_PATH}/{agent_name}",
                "mcp_dir": f"{MCP_SERVERS_PATH}/{mcp_name}",
                "mcp_server": mcp_server_path
            },
            "mcp_config_entry": {
                mcp_name: updated_mcp_config["mcpServers"][mcp_name]
            },
            "required_mcps": [mcp_name] + AGENT_CATEGORIES[category]["required_mcps"],
            "instructions": [
                f"1. Agent directory: {AGENTS_PATH}/{agent_name}/",
                f"2. MCP server directory: {MCP_SERVERS_PATH}/{mcp_name}/",
                f"3. MCP config updated in: {MCP_CONFIG_PATH}",
                "4. Restart celery-scheduler to pick up new MCP",
                f"5. Test agent with: claude -p 'test' --mcp-config {MCP_CONFIG_PATH}"
            ]
        }

        if save_to_disk:
            # Create agent directory
            agent_dir = Path(AGENTS_PATH) / agent_name
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "agent.md").write_text(agent_md)
            (agent_dir / "config.yaml").write_text(config_yaml)

            # Create MCP server directory
            mcp_dir = Path(MCP_SERVERS_PATH) / mcp_name
            mcp_dir.mkdir(parents=True, exist_ok=True)
            (mcp_dir / "server.py").write_text(mcp_server)

            # Update .mcp.json
            config_path = Path(MCP_CONFIG_PATH)
            config_path.write_text(json.dumps(updated_mcp_config, indent=2))

            result["saved"] = True
            result["message"] = f"Agent '{agent_name}' and MCP server '{mcp_name}' created successfully!"

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]

    elif name == "list_categories":
        result = []
        for cat_name, cat_info in AGENT_CATEGORIES.items():
            result.append({
                "name": cat_name,
                "description": cat_info["description"],
                "model": cat_info["model"],
                "timeout": cat_info["timeout"],
                "required_mcps": cat_info["required_mcps"],
                "optional_mcps": cat_info["optional_mcps"],
                "default_tools": cat_info.get("default_tools", [])
            })

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]

    elif name == "validate_agent":
        agent_name = arguments["agent_name"]
        agent_dir = Path(AGENTS_PATH) / agent_name

        issues = []
        recommendations = []

        # Check if agent exists
        if not agent_dir.exists():
            return [TextContent(
                type="text",
                text=json.dumps({
                    "valid": False,
                    "error": f"Agent '{agent_name}' not found at {agent_dir}"
                }, indent=2)
            )]

        # Check agent.md
        agent_md_path = agent_dir / "agent.md"
        if not agent_md_path.exists():
            issues.append("Missing agent.md file")
        else:
            content = agent_md_path.read_text()

            # Check for required MCP mentions
            if "mcp__memory-hub__session_start" not in content:
                issues.append("Missing memory-hub session_start")
                recommendations.append("Add: mcp__memory-hub__session_start at the beginning")

            if "mcp__memory-hub__session_end" not in content:
                issues.append("Missing memory-hub session_end")
                recommendations.append("Add: mcp__memory-hub__session_end at completion")

            if "mcp__agent-outputs__save_output" not in content:
                issues.append("Missing agent-outputs save_output")
                recommendations.append("Add: mcp__agent-outputs__save_output for results")

        # Check config.yaml
        config_path = agent_dir / "config.yaml"
        mcp_name = None
        if not config_path.exists():
            issues.append("Missing config.yaml file")
        else:
            try:
                import yaml
                config = yaml.safe_load(config_path.read_text())
                mcp_name = config.get("mcp_server")
                if not mcp_name:
                    issues.append("No mcp_server defined in config.yaml")
                    recommendations.append("Add: mcp_server: <mcp-name> to config.yaml")
            except:
                issues.append("Invalid config.yaml format")

        # Check MCP server exists
        if mcp_name:
            mcp_path = Path(MCP_SERVERS_PATH) / mcp_name / "server.py"
            if not mcp_path.exists():
                issues.append(f"MCP server not found: {mcp_path}")
                recommendations.append(f"Create MCP server at: {mcp_path}")

            # Check if MCP is in config
            config_path = Path(MCP_CONFIG_PATH)
            if config_path.exists():
                mcp_config = json.loads(config_path.read_text())
                if mcp_name not in mcp_config.get("mcpServers", {}):
                    issues.append(f"MCP '{mcp_name}' not in .mcp.json")
                    recommendations.append(f"Add '{mcp_name}' to .mcp.json")

        return [TextContent(
            type="text",
            text=json.dumps({
                "agent_name": agent_name,
                "mcp_name": mcp_name,
                "valid": len(issues) == 0,
                "issues": issues,
                "recommendations": recommendations,
                "files_found": {
                    "agent.md": agent_md_path.exists() if agent_md_path else False,
                    "config.yaml": config_path.exists() if config_path else False,
                    "mcp_server": (Path(MCP_SERVERS_PATH) / mcp_name / "server.py").exists() if mcp_name else False
                }
            }, indent=2)
        )]

    elif name == "list_agents":
        agents_dir = Path(AGENTS_PATH)
        mcp_config_path = Path(MCP_CONFIG_PATH)

        # Load MCP config
        mcp_config = {}
        if mcp_config_path.exists():
            mcp_config = json.loads(mcp_config_path.read_text()).get("mcpServers", {})

        agents = []

        if agents_dir.exists():
            for item in agents_dir.iterdir():
                if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('old-'):
                    agent_info = {
                        "name": item.name,
                        "has_agent_md": (item / "agent.md").exists(),
                        "has_config": (item / "config.yaml").exists(),
                        "mcp_name": None,
                        "mcp_exists": False,
                        "mcp_in_config": False
                    }

                    # Try to read category and MCP from config
                    config_path = item / "config.yaml"
                    if config_path.exists():
                        try:
                            import yaml
                            config = yaml.safe_load(config_path.read_text())
                            agent_info["category"] = config.get("category", "unknown")
                            agent_info["mcp_name"] = config.get("mcp_server")

                            if agent_info["mcp_name"]:
                                mcp_path = Path(MCP_SERVERS_PATH) / agent_info["mcp_name"] / "server.py"
                                agent_info["mcp_exists"] = mcp_path.exists()
                                agent_info["mcp_in_config"] = agent_info["mcp_name"] in mcp_config
                        except:
                            agent_info["category"] = "unknown"

                    agents.append(agent_info)

        return [TextContent(
            type="text",
            text=json.dumps({
                "agents_path": str(agents_dir),
                "mcp_servers_path": MCP_SERVERS_PATH,
                "count": len(agents),
                "agents": agents
            }, indent=2)
        )]

    elif name == "get_mcp_template":
        mcp_name = arguments["mcp_name"]
        tools = arguments.get("tools", [{"name": "run", "description": "Run the main task"}])

        template = generate_mcp_server(mcp_name, "standalone", "utility",
                                       f"Standalone MCP server: {mcp_name}", tools)

        return [TextContent(
            type="text",
            text=json.dumps({
                "mcp_name": mcp_name,
                "server_path": f"{MCP_SERVERS_PATH}/{mcp_name}/server.py",
                "template": template,
                "mcp_config_entry": {
                    mcp_name: {
                        "command": "/home/claude/.mcp-venv/bin/python",
                        "args": [f"{MCP_SERVERS_PATH}/{mcp_name}/server.py"]
                    }
                }
            }, indent=2)
        )]

    elif name == "get_standards":
        standards = """
# Agent Standards Documentation

## CRITICAL: Every Agent MUST Have an MCP Server

When creating an agent, an MCP server is ALWAYS created together.
No agent can exist without its own MCP server!

## 1. Required MCP Integrations

ALL agents MUST use these MCP servers:

### Agent's Own MCP Server
- Every agent has its own MCP: `mcp__{agent-mcp}__*`
- Contains agent-specific functionality
- Created automatically with `create_agent`

### Memory Hub
- `mcp__memory-hub__session_start`: Call at agent start
- `mcp__memory-hub__session_end`: Call at agent completion
- `mcp__memory-hub__session_note`: Log important findings
- `mcp__memory-hub__memory_create`: Save bugs, decisions, runbooks

### Agent Outputs
- `mcp__agent-outputs__save_output`: Save ALL results
- `mcp__agent-outputs__start_execution`: Log execution start
- `mcp__agent-outputs__complete_execution`: Log execution end

## 2. Agent Structure

```
/agents/{agent-name}/
  ├── agent.md      # Agent instructions
  └── config.yaml   # Configuration with mcp_server reference

/mcp-servers/{agent-mcp}/
  └── server.py     # MCP server code
```

## 3. Output Types

| Type | When to Use |
|------|-------------|
| data | Raw collected data |
| analysis | Analyzed/processed data |
| report | Human-readable reports |
| error | Error logs |
| summary | Brief summaries |

## 4. API Access Rules

- NEVER make direct API calls
- ALWAYS use MCP tools for external services
- Use agent's own MCP for agent-specific logic

## 5. Session Workflow

```
START:
  mcp__memory-hub__session_start(project="marketing-agents")

EXECUTE:
  - Use mcp__{agent-mcp}__* for main task
  - Use other MCPs as needed

SAVE:
  mcp__agent-outputs__save_output(...)

END:
  mcp__memory-hub__session_end(summary="...")
```
"""
        return [TextContent(type="text", text=standards)]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
