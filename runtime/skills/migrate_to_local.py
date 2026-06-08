#!/usr/bin/env python3
"""
migrate_to_local.py — Batch migrate all Paperclip agents from claude_local to process adapter.

Usage:
    cd /Users/nazeera/Documents/AI_PRODUCER
    source env/bin/activate
    python3 runtime/migrate_to_local.py
"""

import json
import sys
import time
import urllib.request

PAPERCLIP_API = "http://127.0.0.1:3100"
COMPANY_ID = "15041ee2-b1c5-43ac-b488-04934bfa1806"

RUNTIME_PATH = "/Users/nazeera/Documents/AI_PRODUCER/runtime/local_agent_runtime.py"
PYTHON_PATH = "/Users/nazeera/Documents/AI_PRODUCER/env/bin/python3"


def api_request(method: str, path: str, payload: dict | None = None) -> dict | None:
    url = f"{PAPERCLIP_API}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️  API {method} {path} failed: {e}")
        return None


def get_all_agents() -> list[dict]:
    result = api_request("GET", f"/api/companies/{COMPANY_ID}/agents")
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return result.get("agents", result.get("items", result.get("results", [])))


def migrate_agent(agent: dict) -> bool:
    agent_id = agent["id"]
    name = agent.get("name", agent_id)
    current_type = agent.get("adapterType", "unknown")

    if current_type == "process":
        print(f"  ✓ {name} already on process")
        return True

    if current_type not in ("claude_local", "claude_cloud"):
        print(f"  ⏭ {name} uses {current_type} — skipping (not Claude)")
        return True

    payload = {
        "adapterType": "process",
        "adapterConfig": {
            "command": PYTHON_PATH,
            "args": [RUNTIME_PATH],
            "timeoutSec": 3600,
            "env": {
                "MLX_PRIMARY_URL": "http://127.0.0.1:8000/v1",
                "MLX_STANDARD_URL": "http://127.0.0.1:8001/v1",
                "MLX_FAST_URL": "http://127.0.0.1:8002/v1",
            },
        },
    }

    result = api_request("PATCH", f"/api/agents/{agent_id}", payload)
    if result:
        print(f"  ✅ {name} migrated")
        return True
    else:
        print(f"  ❌ {name} migration failed")
        return False


def main() -> int:
    print("🚀 Starting agent migration: claude_local → process")
    print(f"   Runtime: {RUNTIME_PATH}")
    print()

    agents = get_all_agents()
    print(f"Found {len(agents)} agents")

    # Count by adapter type
    from collections import Counter
    types = Counter(a.get("adapterType", "unknown") for a in agents)
    print(f"Current adapter breakdown: {dict(types)}")
    print()

    to_migrate = [a for a in agents if a.get("adapterType") == "claude_local"]
    print(f"Migrating {len(to_migrate)} claude_local agents...")
    print()

    success = 0
    failed = 0
    skipped = 0

    for i, agent in enumerate(to_migrate, 1):
        name = agent.get("name", agent["id"])
        print(f"[{i}/{len(to_migrate)}] {name}")
        if migrate_agent(agent):
            success += 1
        else:
            failed += 1
        time.sleep(0.2)  # Rate limit

    print()
    print(f"Migration complete: {success} migrated, {failed} failed, {skipped} skipped")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
