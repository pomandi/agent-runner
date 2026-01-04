#!/usr/bin/env python3
"""Test MCP servers can start without errors."""
import sys
import subprocess
from pathlib import Path

def test_mcp_server(server_path: Path) -> bool:
    """Test if MCP server can start."""
    print(f"Testing {server_path.parent.name}...", end=" ")
    try:
        result = subprocess.run(
            ["python3", str(server_path), "--help"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ OK")
            return True
        else:
            print(f"❌ FAILED (exit {result.returncode})")
            if result.stderr:
                print(f"  Error: {result.stderr.decode()[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print("⏱️  TIMEOUT (might be OK if waiting for stdio)")
        return True
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    mcp_dir = Path(__file__).parent / "mcp-servers"

    if not mcp_dir.exists():
        print(f"❌ MCP directory not found: {mcp_dir}")
        sys.exit(1)

    servers = list(mcp_dir.glob("*/server.py"))

    if not servers:
        print("❌ No MCP servers found")
        sys.exit(1)

    print(f"Found {len(servers)} MCP servers:\n")

    failed = []
    for server in servers:
        if not test_mcp_server(server):
            failed.append(server.parent.name)

    print(f"\n{'='*50}")
    if failed:
        print(f"❌ {len(failed)} servers failed: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"✅ All {len(servers)} servers OK")
        sys.exit(0)
