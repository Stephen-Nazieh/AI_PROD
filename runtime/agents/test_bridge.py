#!/usr/bin/env python3
"""
test_bridge.py — Smoke test for the Paperclip ↔ DeParadigm Media bridge server.

Usage:
    cd /Users/nazeera/Documents/AI_PRODUCER
    source env/bin/activate
    python3 runtime/test_bridge.py
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

BRIDGE_URL = "http://127.0.0.1:3101"
MLX_URL = "http://127.0.0.1:8000/v1/chat/completions"


def _fetch(method: str, endpoint: str, payload: dict | None = None) -> dict:
    url = f"{BRIDGE_URL}{endpoint}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def test_health() -> bool:
    print("🔍 Testing /health ...")
    try:
        r = _fetch("GET", "/health")
        if r.get("status") != "ok":
            print(f"   ❌ Unexpected status: {r}")
            return False
        checks = r.get("checks", {})
        for name, check in checks.items():
            if check.get("status") != "ok":
                print(f"   ⚠️  {name}: {check}")
            else:
                print(f"   ✅ {name}: {check.get('status')}")
        print(f"   ✅ /health passed ({r.get('elapsed_ms')} ms)")
        return True
    except Exception as e:
        print(f"   ❌ /health failed: {e}")
        return False


def test_vault_search() -> bool:
    print("🔍 Testing /vault/search ...")
    try:
        r = _fetch("POST", "/vault/search", {"query": "z-score", "limit": 3})
        if r.get("status") != "ok":
            print(f"   ❌ Unexpected status: {r}")
            return False
        print(f"   ✅ Found {len(r.get('results', []))} results ({r.get('elapsed_ms')} ms)")
        return True
    except Exception as e:
        print(f"   ❌ /vault/search failed: {e}")
        return False


def test_vault_create() -> bool:
    print("🔍 Testing /vault/create ...")
    try:
        note_path = f"02_CURRICULUM/compiled_wiki/_bridge_test_{int(time.time())}.md"
        r = _fetch("POST", "/vault/create", {"path": note_path, "content": "# Bridge Test\n\nThis note was created by test_bridge.py."})
        if r.get("status") != "ok":
            print(f"   ❌ Unexpected status: {r}")
            return False
        print(f"   ✅ Created {note_path} ({r.get('elapsed_ms')} ms)")
        return True
    except Exception as e:
        print(f"   ❌ /vault/create failed: {e}")
        return False


def test_mlx_direct() -> bool:
    print("🔍 Testing local MLX server directly ...")
    try:
        req = urllib.request.Request(
            MLX_URL,
            data=json.dumps({
                "model": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
                "messages": [
                    {"role": "system", "content": "You are a concise assistant."},
                    {"role": "user", "content": "Say 'bridge ok'"},
                ],
                "temperature": 0.1,
                "max_tokens": 5,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"   ✅ MLX response: {content.strip()!r}")
            return True
    except Exception as e:
        print(f"   ❌ MLX direct test failed: {e}")
        return False


def main() -> int:
    print("🧪 DeParadigm Media Bridge Smoke Tests")
    print(f"   Bridge: {BRIDGE_URL}")
    print(f"   MLX:    {MLX_URL}")
    print()

    results = []
    results.append(("MLX Direct", test_mlx_direct()))
    results.append(("Health", test_health()))
    results.append(("Vault Search", test_vault_search()))
    results.append(("Vault Create", test_vault_create()))

    print()
    print("─" * 40)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        icon = "✅" if ok else "❌"
        print(f"   {icon} {name}")
    print()
    if passed == total:
        print(f"🎉 All {total} tests passed.")
        return 0
    else:
        print(f"⚠️  {passed}/{total} tests passed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
