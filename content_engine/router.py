"""CONTENT ENGINE — local intent router.

Turns a plain-language request into ONE engine action via the local LLM's *structured output*
(JSON), then dispatches it. This works on local mlx models that DON'T support native tool-calling
— the model just writes JSON, which it does fine. Powers `engine.py chat "…"` and the single
`assistant` MCP tool, so Open WebUI users can talk naturally to the engine.
"""
import json, os, re, subprocess, sys
ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
PY = os.path.join(ROOT, "env/bin/python3")
sys.path.insert(0, ENGINE)
import llm

ACTIONS = {
    "list_channels": "list the content channels",
    "new_channel":   "create a channel — args: slug, name, niche, fmt(movie|talking_head|social|explainer)",
    "write_script":  "write a script (then user vets) — args: run, idea, fmt, channel, length",
    "make":          "one-shot idea→video (no vet) — args: run, idea, fmt, channel, length",
    "produce":       "produce the approved script of a run — args: run",
    "run_status":    "status of a run — args: run",
    "health":        "brain + tools health",
}

def route(request):
    system = ("You are an intent router for a local content engine. Map the user's request to "
              "EXACTLY ONE action and its arguments. Output STRICT JSON only: "
              '{"action":"<name>","args":{...}}. Available actions:\n'
              + "\n".join(f"  {k}: {v}" for k, v in ACTIONS.items())
              + "\nRules: if no run/slug is given, invent a short lowercase slug from the idea. "
              "Default fmt='movie'. Only use listed actions. Output JSON and nothing else.")
    raw = llm.chat(system, request, tier="fast", temperature=0.2, max_tokens=300)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"action": "unknown", "args": {}, "raw": raw[:200]}
    try:
        d = json.loads(m.group(0))
        return {"action": d.get("action", "unknown"), "args": d.get("args", {})}
    except Exception:
        return {"action": "unknown", "args": {}, "raw": raw[:200]}

def _sh(args, timeout=600, bg=False):
    cmd = [str(x) for x in [PY] + args]   # the local LLM may emit numeric args; subprocess needs str
    if bg:
        subprocess.Popen(cmd, cwd=ROOT, stdout=open(os.devnull, "w"), stderr=subprocess.STDOUT)
        return "started (runs in background — ask for status)"
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "")[-3000:]

def dispatch(action, args):
    a = args or {}
    if action == "list_channels":
        return _sh(["content_engine/new_channel.py", "--list"], 60)
    if action == "new_channel":
        return _sh(["content_engine/new_channel.py", a.get("slug", "channel"),
                    "--name", a.get("name", a.get("slug", "Channel")),
                    "--niche", a.get("niche", ""), "--format", a.get("fmt", "movie")], 120)
    if action == "write_script":
        run = a.get("run") or re.sub(r"\W+", "-", a.get("idea", "draft")[:20]).strip("-").lower()
        cmd = ["content_engine/engine.py", "write", "--run", run, "--idea", a.get("idea", ""),
               "--format", a.get("fmt", "movie"), "--length", a.get("length", "2-3 min")]
        if a.get("channel"): cmd += ["--channel", a["channel"]]
        return _sh(cmd, 300)
    if action == "make":
        run = a.get("run") or re.sub(r"\W+", "-", a.get("idea", "video")[:20]).strip("-").lower()
        cmd = ["content_engine/engine.py", "make", "--run", run, "--idea", a.get("idea", ""),
               "--format", a.get("fmt", "movie"), "--length", a.get("length", "2-3 min")]
        if a.get("channel"): cmd += ["--channel", a["channel"]]
        return f"run='{run}': " + _sh(cmd, bg=True)
    if action == "produce":
        return f"run='{a.get('run')}': " + _sh(["content_engine/engine.py", "produce", "--run", a.get("run", "")], bg=True)
    if action == "run_status":
        out = os.path.join(ENGINE, "runs", a.get("run", ""), "out")
        if not os.path.isdir(out): return f"run '{a.get('run')}': nothing yet."
        return json.dumps(sorted(f for f in os.listdir(out) if f.endswith((".mp4", ".jpg", ".srt"))))
    if action == "health":
        return json.dumps(llm.health())
    return f"(could not route that — try: {', '.join(ACTIONS)})"

def chat(request):
    r = route(request)
    head = f"→ {r['action']}({json.dumps(r.get('args', {}))})\n"
    return head + dispatch(r["action"], r.get("args", {}))

if __name__ == "__main__":
    print(chat(" ".join(sys.argv[1:]) or "list my channels"))
