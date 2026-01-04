"""
Hooks for Claude Agent SDK

Hooks are Python functions invoked at specific points of the agent loop.
They provide deterministic processing and safety checks.

Hook Types:
- PreToolUse: Called before a tool is executed (can block dangerous commands)
- PostToolUse: Called after a tool completes (can log or modify results)
"""

from claude_agent_sdk import HookMatcher
import logging

logger = logging.getLogger('hooks')


async def log_tool_use(tool_input: dict, tool_name: str) -> dict:
    """Log all tool usage for debugging."""
    logger.info(f"Tool called: {tool_name}")
    logger.debug(f"Input: {tool_input}")
    return {"decision": "allow"}


async def block_dangerous_bash(tool_input: dict, tool_name: str) -> dict:
    """
    Block dangerous bash commands.

    Returns:
        {"decision": "allow"} to proceed
        {"decision": "deny", "reason": "..."} to block
    """
    if tool_name != "Bash":
        return {"decision": "allow"}

    command = tool_input.get("command", "")

    # Dangerous patterns to block
    dangerous_patterns = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        ":(){:|:&};:",  # Fork bomb
        "> /dev/sda",
        "dd if=/dev/zero of=/dev/",
        "chmod -R 777 /",
    ]

    for pattern in dangerous_patterns:
        if pattern in command:
            logger.warning(f"Blocked dangerous command: {command}")
            return {
                "decision": "deny",
                "reason": f"Dangerous command pattern detected: {pattern}"
            }

    return {"decision": "allow"}


async def log_tool_result(tool_result: dict, tool_name: str) -> dict:
    """Log tool results after execution."""
    is_error = tool_result.get("isError", False)
    if is_error:
        logger.error(f"Tool {tool_name} failed")
    else:
        logger.info(f"Tool {tool_name} completed successfully")
    return {}


# Pre-configured hook matchers
SAFETY_HOOKS = {
    "PreToolUse": [
        HookMatcher(matcher="*", hooks=[log_tool_use]),
        HookMatcher(matcher="Bash", hooks=[block_dangerous_bash]),
    ],
    "PostToolUse": [
        HookMatcher(matcher="*", hooks=[log_tool_result]),
    ],
}

# Minimal hooks (just logging)
LOGGING_HOOKS = {
    "PreToolUse": [
        HookMatcher(matcher="*", hooks=[log_tool_use]),
    ],
    "PostToolUse": [
        HookMatcher(matcher="*", hooks=[log_tool_result]),
    ],
}
