"""
Example Custom Tools for Claude Agent SDK

These tools demonstrate how to create custom Python tools
that Claude can invoke during agent execution.

Custom tools run as in-process MCP servers - no separate process needed.
"""

from claude_agent_sdk import tool


@tool(
    name="get_current_time",
    description="Get the current date and time",
    input_schema={}
)
async def get_current_time(args: dict) -> dict:
    """Return current timestamp."""
    from datetime import datetime
    now = datetime.now()
    return {
        "content": [{
            "type": "text",
            "text": now.strftime("%Y-%m-%d %H:%M:%S")
        }]
    }


@tool(
    name="calculate",
    description="Perform a mathematical calculation",
    input_schema={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate (e.g., '2 + 2')"
            }
        },
        "required": ["expression"]
    }
)
async def calculate(args: dict) -> dict:
    """Safely evaluate a mathematical expression."""
    import ast
    import operator

    # Safe operators only
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    def eval_expr(node):
        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.BinOp):
            return operators[type(node.op)](eval_expr(node.left), eval_expr(node.right))
        elif isinstance(node, ast.UnaryOp):
            return operators[type(node.op)](eval_expr(node.operand))
        else:
            raise ValueError(f"Unsupported operation: {type(node)}")

    try:
        expression = args.get("expression", "")
        tree = ast.parse(expression, mode='eval')
        result = eval_expr(tree.body)
        return {
            "content": [{
                "type": "text",
                "text": f"{expression} = {result}"
            }]
        }
    except Exception as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: {str(e)}"
            }],
            "isError": True
        }


@tool(
    name="format_json",
    description="Format a JSON string with proper indentation",
    input_schema={
        "type": "object",
        "properties": {
            "json_string": {
                "type": "string",
                "description": "JSON string to format"
            }
        },
        "required": ["json_string"]
    }
)
async def format_json(args: dict) -> dict:
    """Pretty print JSON."""
    import json
    try:
        data = json.loads(args.get("json_string", "{}"))
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        return {
            "content": [{
                "type": "text",
                "text": formatted
            }]
        }
    except json.JSONDecodeError as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Invalid JSON: {str(e)}"
            }],
            "isError": True
        }


# List of all tools to export
ALL_TOOLS = [
    get_current_time,
    calculate,
    format_json,
]
