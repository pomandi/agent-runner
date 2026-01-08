#!/usr/bin/env python3
"""
Remote Workflow Trigger via SSH
Triggers workflow by executing command on remote server
"""
import subprocess
import sys

def trigger_remote_workflow(brand="pomandi"):
    """Trigger workflow via SSH on Coolify server"""

    server = "46.224.117.155"
    container = "agent-worker-k0kcc48sw04k8wwcwwc04s4o-135434425309"

    cmd = [
        "ssh",
        f"root@{server}",
        f"docker exec -it {container} python3 /app/scripts/trigger_workflow.py {brand}"
    ]

    print(f"🚀 Triggering workflow for {brand} on remote server...")
    print(f"   Server: {server}")
    print(f"   Container: {container}\n")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        print("\n✅ Workflow triggered successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        print(f"   Output: {e.output}")
        return False

if __name__ == "__main__":
    brand = sys.argv[1] if len(sys.argv) > 1 else "pomandi"
    success = trigger_remote_workflow(brand)
    sys.exit(0 if success else 1)
