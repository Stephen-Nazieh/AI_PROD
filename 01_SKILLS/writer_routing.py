#!/usr/bin/env python3
"""Toggle the writer agents between local MLX and the real Claude API.

The writer agents (the dedicated channel writers + the shared script agent) are the
quality-critical ones. This flips their adapter env flag CLAUDE_USE_API, which the
claude-local wrapper reads to route to the real Anthropic API (quality) vs the local
MLX proxy :8003 (cheap). The API key lives in .env — never in the agent config.

Usage:
  writer_routing.py --status                 # show each writer's current routing
  writer_routing.py --api [--model M]        # route writers to the real Claude API
  writer_routing.py --local                  # route writers back to local MLX

Prereq for --api: a valid `sk-ant-api03-…` key in .env, OR a logged-in `claude` CLI.
"""
from __future__ import annotations
import json, sys, urllib.request, urllib.error

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import studio_lib as S  # noqa: E402

API = "http://127.0.0.1:3100"
COMPANY = S.company_id()
# A writer = name contains one of these (lowercased).
WRITER_MATCH = ("writer", "script agent")


def _req(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(f"{API}{path}", data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=15) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def _envval(v):
    """Paperclip stores env values as {"type":"plain","value":"…"} objects."""
    return v.get("value") if isinstance(v, dict) else v


def _writers() -> list[dict]:
    code, agents = _req("GET", f"/api/companies/{COMPANY}/agents")
    if not isinstance(agents, list):
        print(f"❌ could not list agents ({code})", file=sys.stderr)
        sys.exit(1)
    return [a for a in agents if any(m in (str(a.get("name")) or "").lower() for m in WRITER_MATCH)]


def main() -> int:
    args = sys.argv[1:]
    mode = "--status"
    for a in args:
        if a in ("--status", "--api", "--local"):
            mode = a
    model = None
    if "--model" in args:
        model = args[args.index("--model") + 1]

    writers = _writers()
    if not writers:
        print("No writer agents found.")
        return 0

    for w in writers:
        ac = w.get("adapterConfig") or {}
        env = dict(ac.get("env") or {})
        cur = "API" if _envval(env.get("CLAUDE_USE_API")) == "1" else "local"
        if mode == "--status":
            m = _envval(env.get("ANTHROPIC_MODEL"))
            extra = f" (model {m})" if m else ""
            print(f"  {w['name']:32} → {cur}{extra}")
            continue
        if mode == "--api":
            env["CLAUDE_USE_API"] = {"type": "plain", "value": "1"}
            if model:
                env["ANTHROPIC_MODEL"] = {"type": "plain", "value": model}
        else:  # --local
            env.pop("CLAUDE_USE_API", None)
            env.pop("ANTHROPIC_MODEL", None)
        ac["env"] = env
        code, _ = _req("PATCH", f"/api/agents/{w['id']}", {"adapterConfig": ac})
        ok = "✅" if code in (200, 201) else f"❌({code})"
        print(f"  {ok} {w['name']:32} → {'API' if mode=='--api' else 'local'}")
    if mode == "--api":
        print("\n  Writers now route to the cloud API (Kimi Code, kimi-for-coding) via the "
              "claude-local wrapper. Ensure KIMI_API_KEY is set in .env. Note: Kimi is a "
              "heavier model (~60-70s/run) but higher quality. Revert with --local.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
