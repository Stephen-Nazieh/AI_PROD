#!/usr/bin/env python3
"""CONTENT ENGINE — MCP server.

Exposes the engine as MCP tools so any MCP client (Open WebUI via mcpo, Claude Desktop, …)
can drive it conversationally. The brain (scriptwriting/directing) and all production stay
LOCAL — these tools just trigger the local pipeline.

Run standalone (stdio):   env/bin/python3 content_engine/mcp_server.py
Bridge to Open WebUI:      env/bin/mcpo --port 8900 -- env/bin/python3 content_engine/mcp_server.py
"""
import json, os, subprocess, sys
from mcp.server.fastmcp import FastMCP

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
PY = os.path.join(ROOT, "env/bin/python3")
sys.path.insert(0, ENGINE); sys.path.insert(0, os.path.join(ENGINE, "memory"))
import llm
import memory

mcp = FastMCP("content-engine")

def _run(args, timeout=600):
    r = subprocess.run([PY] + args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "")[-4000:] + (("\n[stderr] " + r.stderr[-500:]) if r.returncode else "")

@mcp.tool()
def assistant(request: str) -> str:
    """Natural-language entry point — describe what you want ("write a 1-min horror short for
    midnight-tales about a haunted elevator") and the engine routes + runs it locally. Use this
    one tool if your local model is weak at picking tools; it does the routing itself."""
    import router
    return router.chat(request)

@mcp.tool()
def health() -> str:
    """Status of the local LLM brain and the engine tools."""
    return json.dumps({"brain": llm.health(),
                       "tools": {"ffmpeg": bool(subprocess.run(["which", "ffmpeg"], capture_output=True).stdout),
                                 "blender": os.path.exists("/Applications/Blender.app")}}, indent=2)

@mcp.tool()
def list_channels() -> str:
    """List the content channels and their brand/niche."""
    d = os.path.join(ENGINE, "channels"); out = []
    if os.path.isdir(d):
        for c in sorted(os.listdir(d)):
            p = os.path.join(d, c, "channel.json")
            if os.path.exists(p):
                j = json.load(open(p)); out.append({"slug": c, "name": j.get("name"), "niche": j.get("niche"), "voice": j.get("voice")})
    return json.dumps(out, indent=2)

@mcp.tool()
def new_channel(slug: str, name: str, niche: str = "", fmt: str = "movie") -> str:
    """Create a new content channel. The local LLM drafts its brand voice/audience/pillars."""
    return _run(["content_engine/new_channel.py", slug, "--name", name, "--niche", niche, "--format", fmt], timeout=120)

@mcp.tool()
def write_script(run: str, idea: str, fmt: str = "movie", channel: str = "", length: str = "2-3 min") -> str:
    """Write a production-ready script from an idea (local brain). Returns the DRAFT for you to
    vet/edit at content_engine/runs/<run>/script.md before producing. fmt: movie|talking_head|social|explainer."""
    d = os.path.join(ENGINE, "runs", run); os.makedirs(d, exist_ok=True)
    args = ["content_engine/agents/scriptwriter.py", "--idea", idea, "--format", fmt,
            "--length", length, "--out", os.path.join(d, "script.md")]
    if channel: args += ["--channel", channel]
    _run(args, timeout=300)
    p = os.path.join(d, "script.md")
    txt = open(p).read() if os.path.exists(p) else "(no script produced)"
    return f"DRAFT at {p} — review/edit, then call produce(run='{run}').\n\n{txt}"

@mcp.tool()
def produce(run: str) -> str:
    """Cast (director) → render → distribute the APPROVED script for a run. Long-running: starts
    in the background and returns immediately. Poll with run_status(run)."""
    d = os.path.join(ENGINE, "runs", run)
    if not os.path.exists(os.path.join(d, "script.md")):
        return f"No script at runs/{run}/script.md — call write_script first."
    log = os.path.join(d, "produce.log")
    subprocess.Popen([PY, "content_engine/engine.py", "produce", "--run", run],
                     cwd=ROOT, stdout=open(log, "w"), stderr=subprocess.STDOUT)
    return f"Production started for '{run}' (cast → render → distribute). Poll run_status('{run}'). Log: {log}"

@mcp.tool()
def run_status(run: str) -> str:
    """What a run has produced so far (scenes, episode, vertical, thumbnail)."""
    out = os.path.join(ENGINE, "runs", run, "out")
    if not os.path.isdir(out):
        return f"run '{run}': nothing produced yet."
    files = sorted(f for f in os.listdir(out) if f.endswith((".mp4", ".jpg", ".srt")))
    ep = os.path.join(out, run + ".mp4")
    done = "✅ episode ready" if os.path.exists(ep) else "… in progress"
    return json.dumps({"run": run, "status": done, "deliverables": files}, indent=2)

@mcp.tool()
def make(run: str, idea: str, fmt: str = "movie", channel: str = "", length: str = "2-3 min") -> str:
    """One-shot idea→video (skips the vet gate). Starts in background; poll run_status(run)."""
    d = os.path.join(ENGINE, "runs", run); os.makedirs(d, exist_ok=True)
    log = os.path.join(d, "make.log")
    args = [PY, "content_engine/engine.py", "make", "--run", run, "--idea", idea, "--format", fmt, "--length", length]
    if channel: args += ["--channel", channel]
    subprocess.Popen(args, cwd=ROOT, stdout=open(log, "w"), stderr=subprocess.STDOUT)
    return f"idea→video started for '{run}'. Poll run_status('{run}'). Log: {log}"

if __name__ == "__main__":
    mcp.run()
