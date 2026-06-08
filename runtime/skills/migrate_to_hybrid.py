#!/usr/bin/env python3
"""
migrate_to_hybrid.py — Update Paperclip agent adapters to hybrid/local.

Reads agent categorization and updates each agent's process adapter config:
- hybrid agents → hybrid_agent_runtime.py (Claude THINK + local EXECUTE)
- local agents → local_agent_runtime.py (full ReAct loop with MLX)
- openclaw_proxy → unchanged

Usage:
    python migrate_to_hybrid.py [--dry-run]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PAPERCLIP_API_BASE = os.environ.get("PAPERCLIP_API_URL", "http://127.0.0.1:3100")
COMPANY_ID = os.environ.get("PAPERCLIP_COMPANY_ID", "15041ee2-b1c5-43ac-b488-04934bfa1806")

def _env_plain(value: str) -> dict:
    return {"type": "plain", "value": value}

HYBRID_CONFIG = {
    "command": "/Users/nazeera/Documents/AI_PRODUCER/env/bin/python3",
    "args": [
        "/Users/nazeera/Documents/AI_PRODUCER/runtime/hybrid_agent_runtime.py",
    ],
    "timeoutSec": 3600,
    "env": {
        "ANTHROPIC_BASE_URL": _env_plain("http://127.0.0.1:8003"),
        "ANTHROPIC_AUTH_TOKEN": _env_plain("local"),
        "ANTHROPIC_API_KEY": _env_plain(""),
    },
}

LOCAL_CONFIG = {
    "command": "/Users/nazeera/Documents/AI_PRODUCER/env/bin/python3",
    "args": [
        "/Users/nazeera/Documents/AI_PRODUCER/runtime/local_agent_runtime.py",
    ],
    "timeoutSec": 3600,
    "env": {
        "MLX_PRIMARY_URL": _env_plain("http://127.0.0.1:8000/v1"),
        "MLX_STANDARD_URL": _env_plain("http://127.0.0.1:8001/v1"),
        "MLX_FAST_URL": _env_plain("http://127.0.0.1:8002/v1"),
    },
}


def api_request(method: str, path: str, payload: dict | None = None) -> dict | None:
    url = f"{PAPERCLIP_API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"  ⚠️  HTTP {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ⚠️  {e}", file=sys.stderr)
        return None


def get_agents() -> list[dict]:
    resp = api_request("GET", f"/api/companies/{COMPANY_ID}/agents")
    return resp if isinstance(resp, list) else []


def update_agent(agent_id: str, adapter_type: str, adapter_config: dict) -> bool:
    resp = api_request("PATCH", f"/api/agents/{agent_id}", {
        "adapterType": adapter_type,
        "adapterConfig": adapter_config,
    })
    return resp is not None


def categorize_agent(name: str, adapter_type: str) -> str:
    """Categorize an agent by name."""
    if adapter_type == "openclaw_gateway":
        return "other"

    name_lower = name.lower()

    # Executive agents
    executives = ["chief executive officer", "ceo", "chief technology officer", "cto",
                  "chief financial officer", "cfo", "chief operating officer", "coo",
                  "chief of staff"]
    for exec_name in executives:
        if exec_name in name_lower:
            return "hybrid"

    # Hybrid keywords — coding, creative, file-creation
    hybrid_kws = [
        "engineer", "developer", "architect", "scripter", "coder",
        "designer", "creator", "builder", "prototype", "script", "editor",
        "visual", "thumbnail", "seo", "content strategist", "content creator",
        "writer", "author", "narrative", "narratologist", "storyteller",
        "gameplay", "game designer", "level designer", "audio",
        "shader", "shader graph", "technical artist", "artist",
        "godot", "unity", "unreal", "roblox", "blender",
        "solidity", "smart contract", "blockchain",
        "frontend", "backend", "fullstack", "next.js", "supabase", "vercel",
        "stripe", "cms", "devops", "sre", "infrastructure", "automation", "workflow",
        "api", "tester", "reviewer", "git", "lsp", "index",
        "mcp", "embedded", "firmware", "spatial", "metal", "visionos", "xr", "immersive",
        "mini program", "integration", "bridge", "operator", "vault",
        "mobile app", "app store", "voice ai",
        "codebase", "onboarding", "minimal change",
        "principal agent engineer", "da vinci",
        "salesforce", "salesforce architect",
        "local devops", "local sre", "python bridge",
    ]
    for kw in hybrid_kws:
        if kw in name_lower:
            return "hybrid"

    # Default to local for research/analysis/strategy agents
    return "local"


def main():
    parser = argparse.ArgumentParser(description="Migrate Paperclip agents to hybrid/local adapters")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    parser.add_argument("--category", choices=["hybrid", "local", "all"], default="all",
                        help="Only migrate agents in this category")
    args = parser.parse_args()

    print(f"🔍 Fetching agents from Paperclip...")
    agents = get_agents()
    print(f"   Found {len(agents)} agents\n")

    hybrid_count = 0
    local_count = 0
    other_count = 0
    updated = 0
    failed = 0
    skipped = 0

    for agent in agents:
        agent_id = agent.get("id", "")
        name = agent.get("name", "unknown")
        current_adapter = agent.get("adapterType", "")

        cat = categorize_agent(name, current_adapter)

        if cat == "hybrid":
            hybrid_count += 1
            target_config = HYBRID_CONFIG
            target_type = "process"
            label = "🧠 HYBRID"
        elif cat == "local":
            local_count += 1
            target_config = LOCAL_CONFIG
            target_type = "process"
            label = "⚙️  LOCAL"
        else:
            other_count += 1
            label = "🔒 OTHER"
            print(f"{label}  {name} (keeping {current_adapter})")
            continue

        # Check if already correct
        current_args = agent.get("adapterConfig", {}).get("args", [])
        target_script = target_config["args"][0]

        if target_script in current_args:
            print(f"{label}  {name} → already correct, skipping")
            skipped += 1
            continue

        print(f"{label}  {name}")

        if args.dry_run:
            continue

        if args.category != "all" and cat != args.category:
            skipped += 1
            continue

        if update_agent(agent_id, target_type, target_config):
            updated += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"  Hybrid agents:     {hybrid_count}")
    print(f"  Local agents:      {local_count}")
    print(f"  Other agents:      {other_count}")
    print(f"  Updated:           {updated}")
    print(f"  Failed:            {failed}")
    print(f"  Skipped (correct): {skipped}")
    if args.dry_run:
        print(f"\n  ⚠️  DRY RUN — no changes applied")
        print(f"  Run without --dry-run to apply changes")


if __name__ == "__main__":
    main()
