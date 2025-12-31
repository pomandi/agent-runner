"""
SDK Executor - Claude Agent SDK based execution.

Replaces all subprocess.run CLI calls with native SDK usage.
Uses credentials file authentication (Claude Max subscription).

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                    Your Python Code                      │
    │  executor = SDKExecutor()                               │
    │  result = await executor.run_prompt(prompt, tools)      │
    └────────────────────────┬────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │              Claude Agent SDK (Python)                   │
    │  - Spawns CLI as subprocess                             │
    │  - Manages stdin/stdout communication                   │
    │  - Uses ~/.claude/.credentials.json for auth            │
    └────────────────────────┬────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────┐
    │                   Anthropic API                          │
    └─────────────────────────────────────────────────────────┘
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator

# Import SDK
try:
    from claude_agent_sdk import query, ClaudeAgentOptions
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

logger = logging.getLogger("sdk-executor")


@dataclass
class ExecutionResult:
    """Result of an SDK execution."""
    success: bool
    response_text: str = ""
    json_data: Optional[Dict[str, Any]] = None
    message_count: int = 0
    tool_calls: int = 0
    duration_ms: int = 0
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)

    def get_json(self) -> Optional[Dict]:
        """Extract JSON from response text if not already parsed."""
        if self.json_data:
            return self.json_data

        if not self.response_text:
            return None

        try:
            start_idx = self.response_text.find('{')
            end_idx = self.response_text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = self.response_text[start_idx:end_idx + 1]
                self.json_data = json.loads(json_str)
                return self.json_data
        except json.JSONDecodeError:
            pass

        return None


class SDKExecutor:
    """
    Execute prompts using Claude Agent SDK.

    Replaces subprocess.run CLI calls with native SDK usage.

    Usage:
        executor = SDKExecutor()

        # Simple prompt
        result = await executor.run_prompt("What is 2+2?")
        print(result.response_text)

        # With tools
        result = await executor.run_prompt(
            "Read the file at /tmp/data.json",
            tools=["Read"]
        )

        # With options
        result = await executor.run_prompt(
            "Analyze this...",
            tools=["mcp__analyzer__*"],
            cwd="/app/agents/analyzer",
            max_turns=30
        )
    """

    def __init__(self, mcp_config_path: Optional[str] = None):
        """Initialize executor.

        Args:
            mcp_config_path: Path to MCP config file (default: /root/.claude/.mcp.json)
        """
        self.mcp_config_path = mcp_config_path or "/root/.claude/.mcp.json"

        if not SDK_AVAILABLE:
            logger.error("claude-agent-sdk not installed!")
            raise RuntimeError("claude-agent-sdk not available")

    async def run_prompt(
        self,
        prompt: str,
        tools: Optional[List[str]] = None,
        cwd: str = "/app",
        max_turns: int = 50,
        timeout_seconds: int = 300,
        log_file: Optional[Path] = None
    ) -> ExecutionResult:
        """
        Execute a prompt using Claude Agent SDK.

        Args:
            prompt: The prompt to send to Claude
            tools: List of allowed tool patterns (e.g., ["Read", "mcp__analyzer__*"])
            cwd: Working directory for the agent
            max_turns: Maximum conversation turns
            timeout_seconds: Timeout in seconds
            log_file: Optional path to write detailed logs

        Returns:
            ExecutionResult with response text, JSON data, and stats
        """
        start_time = datetime.now()
        result = ExecutionResult(success=False)

        try:
            # Build options
            options = ClaudeAgentOptions(
                cwd=cwd if Path(cwd).exists() else "/app",
                allowed_tools=tools or [],
                max_turns=max_turns
            )

            logger.info(f"[SDK] Running prompt ({len(prompt)} chars)")
            logger.info(f"[SDK] CWD: {cwd}")
            logger.info(f"[SDK] Tools: {tools}")

            response_parts = []
            message_count = 0
            tool_calls = 0
            log_entries = []

            # Open log file if specified
            log_handle = None
            if log_file:
                log_handle = open(log_file, "w")
                log_handle.write("=" * 60 + "\n")
                log_handle.write("   SDK EXECUTION LOG\n")
                log_handle.write("=" * 60 + "\n")
                log_handle.write(f"Time: {start_time.isoformat()}\n")
                log_handle.write(f"CWD: {cwd}\n")
                log_handle.write(f"Tools: {tools}\n")
                log_handle.write(f"Prompt: {prompt[:500]}...\n" if len(prompt) > 500 else f"Prompt: {prompt}\n")
                log_handle.write("=" * 60 + "\n\n")

            try:
                # Run with timeout
                async with asyncio.timeout(timeout_seconds):
                    async for message in query(prompt=prompt, options=options):
                        message_count += 1

                        if hasattr(message, 'content'):
                            for block in message.content:
                                if hasattr(block, 'text'):
                                    text = block.text
                                    response_parts.append(text)
                                    log_entries.append(f"[TEXT] {text[:200]}...")

                                    if log_handle:
                                        log_handle.write(f"\n📝 RESPONSE:\n{text}\n")

                                elif hasattr(block, 'type'):
                                    if block.type == 'tool_use':
                                        tool_calls += 1
                                        tool_name = getattr(block, 'name', 'unknown')
                                        tool_input = getattr(block, 'input', {})
                                        log_entries.append(f"[TOOL] {tool_name}")

                                        if log_handle:
                                            log_handle.write(f"\n🔧 TOOL: {tool_name}\n")
                                            log_handle.write(f"   Input: {json.dumps(tool_input, indent=2)}\n")

                                    elif block.type == 'tool_result':
                                        tool_result = getattr(block, 'content', '')
                                        if isinstance(tool_result, str) and len(tool_result) > 500:
                                            tool_result = tool_result[:500] + "..."

                                        if log_handle:
                                            log_handle.write(f"\n📥 RESULT:\n{tool_result}\n")

            except asyncio.TimeoutError:
                result.error = f"Timeout after {timeout_seconds}s"
                logger.error(f"[SDK] {result.error}")
                if log_handle:
                    log_handle.write(f"\n❌ TIMEOUT after {timeout_seconds}s\n")
                return result

            finally:
                if log_handle:
                    duration = (datetime.now() - start_time).total_seconds() * 1000
                    log_handle.write("\n" + "=" * 60 + "\n")
                    log_handle.write("   SUMMARY\n")
                    log_handle.write("=" * 60 + "\n")
                    log_handle.write(f"Messages: {message_count}\n")
                    log_handle.write(f"Tool calls: {tool_calls}\n")
                    log_handle.write(f"Duration: {duration:.0f}ms\n")
                    log_handle.write("=" * 60 + "\n")
                    log_handle.close()

            # Build result
            result.success = True
            result.response_text = "\n".join(response_parts)
            result.message_count = message_count
            result.tool_calls = tool_calls
            result.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            result.logs = log_entries

            # Try to parse JSON
            result.get_json()

            logger.info(f"[SDK] Complete: {message_count} messages, {tool_calls} tools, {result.duration_ms}ms")

            return result

        except Exception as e:
            logger.error(f"[SDK] Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.error = str(e)
            return result

    async def run_agent(
        self,
        agent_name: str,
        task: str,
        log_file: Optional[Path] = None
    ) -> ExecutionResult:
        """
        Run a registered agent by name.

        Uses AgentRegistry to get configuration.

        Args:
            agent_name: Name of the agent (from agents.yaml)
            task: Task description to send to agent
            log_file: Optional log file path

        Returns:
            ExecutionResult
        """
        from agent_registry import get_registry

        registry = get_registry()
        agent = registry.get_agent(agent_name)

        if not agent:
            return ExecutionResult(
                success=False,
                error=f"Agent not found: {agent_name}"
            )

        if not agent.enabled:
            return ExecutionResult(
                success=False,
                error=f"Agent is disabled: {agent_name}"
            )

        # Read agent.md if exists
        agent_md_path = Path(agent.cwd) / "agent.md"
        full_prompt = task

        if agent_md_path.exists():
            agent_instructions = agent_md_path.read_text()
            full_prompt = f"""You are running as the {agent_name} agent.

AGENT INSTRUCTIONS:
{agent_instructions}

TASK:
{task}"""

        return await self.run_prompt(
            prompt=full_prompt,
            tools=agent.tools_list,
            cwd=agent.cwd,
            max_turns=agent.max_turns,
            timeout_seconds=agent.timeout_seconds,
            log_file=log_file
        )


# Convenience function
async def run_prompt(
    prompt: str,
    tools: Optional[List[str]] = None,
    cwd: str = "/app",
    max_turns: int = 50,
    timeout_seconds: int = 300
) -> ExecutionResult:
    """
    Quick helper to run a prompt with SDK.

    Usage:
        result = await run_prompt("What is 2+2?")
        print(result.response_text)
    """
    executor = SDKExecutor()
    return await executor.run_prompt(
        prompt=prompt,
        tools=tools,
        cwd=cwd,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds
    )


# Check SDK availability
def check_sdk() -> bool:
    """Check if Claude Agent SDK is available."""
    return SDK_AVAILABLE
