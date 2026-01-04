#!/usr/bin/env python3
"""
Claude Agent SDK Runner - Pure Python Implementation

Agents are defined in agents.py as Python dataclasses.
No markdown files, no CLI remnants.

Usage:
    python sdk_runner.py <agent_name> [task]
    python sdk_runner.py feed-publisher "Publish post to Pomandi"
    python sdk_runner.py --full invoice-finder "Find invoice"
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import anyio
from dotenv import load_dotenv
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    create_sdk_mcp_server,
)

# Import agent definitions
from agents import get_agent, list_agents, AGENTS

# Import monitoring client (optional - Langfuse integration)
try:
    from monitoring import LangfuseClient
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    LangfuseClient = None

# Setup logging with valid level mapping
_log_level_map = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
    'VERBOSE': logging.DEBUG,  # Map verbose to DEBUG
}
_raw_level = os.getenv('LOG_LEVEL', 'INFO').upper()
_log_level = _log_level_map.get(_raw_level, logging.INFO)

logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('sdk_runner')

# Load environment
load_dotenv()


def load_custom_tools():
    """Load custom tools from tools/ directory."""
    try:
        from tools.example_tools import ALL_TOOLS
        return ALL_TOOLS
    except ImportError:
        return []


def load_mcp_servers(agent_tools: list) -> dict:
    """
    Load MCP servers based on agent tool requirements.

    Args:
        agent_tools: List of tool patterns (e.g., ["mcp__feed-publisher-mcp__*"])

    Returns:
        Dict of MCP server configurations for ClaudeAgentOptions
    """
    mcp_servers = {}
    mcp_dir = Path(__file__).parent / "mcp-servers"

    if not mcp_dir.exists():
        logger.warning(f"MCP servers directory not found: {mcp_dir}")
        return mcp_servers

    # Extract unique MCP server names from tool patterns
    server_names = set()
    for tool_pattern in agent_tools:
        if tool_pattern.startswith("mcp__") and "__" in tool_pattern:
            # Extract server name from "mcp__server-name__tool" or "mcp__server-name__*"
            parts = tool_pattern.split("__")
            if len(parts) >= 2:
                server_names.add(parts[1])

    # Load each required server
    for server_name in server_names:
        server_path = mcp_dir / server_name / "server.py"
        if server_path.exists():
            mcp_servers[server_name] = {
                "command": "python3",
                "args": [str(server_path)],
                "env": dict(os.environ),  # Pass all env vars (tokens, etc.)
                "stderr": "inherit"  # Show MCP server errors
            }
            logger.info(f"Loaded MCP server: {server_name} at {server_path}")
        else:
            logger.warning(f"MCP server not found: {server_name} at {server_path}")

    return mcp_servers


def load_hooks(hook_type: str = 'safety'):
    """Load hooks configuration."""
    try:
        from hooks import SAFETY_HOOKS, LOGGING_HOOKS
        if hook_type == 'safety':
            return SAFETY_HOOKS
        elif hook_type == 'logging':
            return LOGGING_HOOKS
        return {}
    except ImportError:
        return {}


async def run_agent(
    agent_name: str,
    task: str,
    use_tools: bool = False,
    use_hooks: bool = False
) -> dict:
    """
    Run an agent with the given task.

    Args:
        agent_name: Agent name (must exist in agents.py)
        task: The task/prompt for the agent
        use_tools: Enable custom Python tools
        use_hooks: Enable safety hooks
    """
    start_time = datetime.now()

    # Get agent config from Python definitions
    agent = get_agent(agent_name)
    if not agent:
        return {
            'success': False,
            'error': f"Agent not found: {agent_name}",
            'available': list_agents()
        }

    logger.info(f"Starting agent: {agent.name}")
    logger.info(f"Description: {agent.description}")

    # Initialize monitoring client (if available and configured)
    monitor: Optional['LangfuseClient'] = None
    if MONITORING_AVAILABLE and os.getenv('LANGFUSE_PUBLIC_KEY'):
        monitor = LangfuseClient()
        await monitor.start_trace(agent.name, task)

    # Build options
    options_kwargs = {
        'system_prompt': agent.system_prompt,
        'permission_mode': 'acceptAll',  # Accept all tool calls automatically
        'max_turns': agent.max_turns,
        'stderr': lambda msg: None,  # Suppress "Using bundled Claude Code CLI" logs
    }

    # Load MCP servers based on agent tool requirements
    logger.info(f"Agent tools: {agent.tools}")
    mcp_servers = load_mcp_servers(agent.tools)
    if mcp_servers:
        logger.info(f"Loaded {len(mcp_servers)} MCP servers: {list(mcp_servers.keys())}")
        options_kwargs['mcp_servers'] = mcp_servers
    else:
        logger.warning("No MCP servers loaded for this agent")

    # Add custom tools if enabled
    if use_tools:
        custom_tools = load_custom_tools()
        if custom_tools:
            logger.info(f"Loading {len(custom_tools)} custom tools")
            tools_server = create_sdk_mcp_server(
                name="custom-tools",
                version="1.0.0",
                tools=custom_tools
            )
            # Merge with existing mcp_servers
            if 'mcp_servers' not in options_kwargs:
                options_kwargs['mcp_servers'] = {}
            options_kwargs['mcp_servers']['custom'] = tools_server

    # Add hooks if enabled
    if use_hooks:
        hooks = load_hooks('safety')
        if hooks:
            logger.info("Safety hooks enabled")
            options_kwargs['hooks'] = hooks

    options = ClaudeAgentOptions(**options_kwargs)

    results = {
        'agent': agent.name,
        'task': task,
        'start_time': start_time.isoformat(),
        'tool_calls': [],
        'success': False,
    }

    try:
        if use_tools or use_hooks:
            # Full SDK mode with ClaudeSDKClient
            async with ClaudeSDKClient(options=options) as client:
                async for message in client.process_query(task):
                    await _process_message(message, results, monitor)
        else:
            # Simple mode with query()
            async for message in query(prompt=task, options=options):
                await _process_message(message, results, monitor)

        print()  # Newline after streaming
        results['success'] = True

    except Exception as e:
        logger.error(f"Agent failed: {e}", exc_info=True)
        results['error'] = str(e)
        # Add more error details
        if hasattr(e, '__cause__'):
            results['error'] += f" | Cause: {e.__cause__}"

    results['duration_seconds'] = (datetime.now() - start_time).total_seconds()

    # Complete monitoring
    if monitor:
        status = 'completed' if results.get('success') else 'failed'
        await monitor.complete_trace(
            status=status,
            cost_usd=results.get('cost_usd'),
            error_message=results.get('error')
        )
        await monitor.close()

    return results


async def _process_message(message, results, monitor=None):
    """Process a message from the SDK."""
    if hasattr(message, 'content'):
        for block in message.content:
            if hasattr(block, 'text'):
                print(block.text, end='', flush=True)
            elif hasattr(block, 'name'):
                logger.info(f"Tool: {block.name}")
                results['tool_calls'].append(block.name)

                # Report tool call to monitoring
                if monitor:
                    span_id = await monitor.add_span(block.name, {})
                    # Note: We don't have output yet, span will be auto-completed

    if hasattr(message, 'result'):
        results['final_result'] = message.result
        results['success'] = not getattr(message, 'is_error', False)
        if hasattr(message, 'total_cost_usd'):
            results['cost_usd'] = message.total_cost_usd


async def run_test():
    """Test SDK connection."""
    print("=" * 60)
    print("Claude Agent SDK - Test")
    print("=" * 60)
    print()

    # Test 1: SDK connection
    print("1. SDK Connection...")
    options = ClaudeAgentOptions(
        system_prompt="Be brief.",
        permission_mode='acceptEdits',
        max_turns=1,
    )

    try:
        async for message in query(prompt="Say 'OK'", options=options):
            if hasattr(message, 'content'):
                for block in message.content:
                    if hasattr(block, 'text'):
                        print(f"   Response: {block.text}")
            if hasattr(message, 'result'):
                print("   PASSED")
                break
    except Exception as e:
        print(f"   FAILED: {e}")
        return False

    # Test 2: Agents loaded
    print("\n2. Agents...")
    agents = list_agents()
    print(f"   Found {len(agents)} agents: {', '.join(agents)}")
    print("   PASSED")

    # Test 3: Custom tools
    print("\n3. Custom Tools...")
    tools = load_custom_tools()
    if tools:
        print(f"   Found {len(tools)} tools")
        print("   PASSED")
    else:
        print("   None (optional)")

    # Test 4: Hooks
    print("\n4. Hooks...")
    hooks = load_hooks('safety')
    if hooks:
        print(f"   PreToolUse: {len(hooks.get('PreToolUse', []))}")
        print(f"   PostToolUse: {len(hooks.get('PostToolUse', []))}")
        print("   PASSED")
    else:
        print("   None (optional)")

    print("\n" + "=" * 60)
    print("All tests passed!")
    return True


def print_usage():
    """Print usage information."""
    print("""
Claude Agent SDK Runner
=======================

Usage:
    python sdk_runner.py <agent> [task]           Run agent
    python sdk_runner.py --full <agent> [task]    With tools + hooks
    python sdk_runner.py list                     List agents
    python sdk_runner.py info <agent>             Show agent details
    python sdk_runner.py test                     Test SDK

Agents:""")

    for name, agent in AGENTS.items():
        print(f"    {name:20} {agent.description[:50]}...")

    print("""
Examples:
    python sdk_runner.py feed-publisher "Publish post to Pomandi"
    python sdk_runner.py invoice-finder "Find invoice for SNCB 22.70"
    python sdk_runner.py --full invoice-extractor "Extract pending invoices"

Environment:
    CLAUDE_CODE_OAUTH_TOKEN  - OAuth token (1 year valid)
    LOG_LEVEL               - DEBUG, INFO, WARNING, ERROR
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1

    args = sys.argv[1:]
    use_full = False

    # Parse flags
    while args and args[0].startswith('--'):
        flag = args.pop(0)
        if flag == '--full':
            use_full = True
        elif flag in ['--help', '-h']:
            print_usage()
            return 0

    if not args:
        print_usage()
        return 1

    command = args[0]

    if command == 'list':
        print("Available agents:")
        for name, agent in AGENTS.items():
            print(f"  {name}: {agent.description}")
        return 0

    if command == 'info' and len(args) > 1:
        agent = get_agent(args[1])
        if agent:
            print(f"Agent: {agent.name}")
            print(f"Description: {agent.description}")
            print(f"Max turns: {agent.max_turns}")
            print(f"Tools: {', '.join(agent.tools)}")
            print(f"\nSystem Prompt:\n{agent.system_prompt[:500]}...")
        else:
            print(f"Agent not found: {args[1]}")
        return 0

    if command == 'test':
        success = anyio.run(run_test)
        return 0 if success else 1

    # Run agent
    agent_name = args[0]
    task = " ".join(args[1:]) if len(args) > 1 else "Run the default task"

    async def _run():
        return await run_agent(agent_name, task, use_tools=use_full, use_hooks=use_full)

    results = anyio.run(_run)

    # Summary
    print("\n" + "=" * 60)
    print(f"Agent: {results.get('agent')}")
    print(f"Success: {results.get('success')}")
    print(f"Duration: {results.get('duration_seconds', 0):.1f}s")
    print(f"Tools used: {len(results.get('tool_calls', []))}")
    if results.get('cost_usd'):
        print(f"Cost: ${results['cost_usd']:.4f}")
    if results.get('error'):
        print(f"Error: {results['error']}")

    return 0 if results.get('success') else 1


if __name__ == "__main__":
    exit(main())
