"""CONTENT ENGINE — Paperclip oversight sync.

Surfaces channels and runs into Paperclip (the governance dashboard, :3100) so the business
side is visible: each CHANNEL becomes a Paperclip project; each produced RUN updates it.
Best-effort + offline-safe — if Paperclip isn't running, the engine still works.

  register_channel(slug, name, niche) -> project_id (find or create)
  report_run(channel_name, run, status, output) -> update the channel's project
"""
import json, re, urllib.request, urllib.error
API = "http://127.0.0.1:3100"
COMPANY_NAME = "DeParadigm Media"   # the umbrella company for channels (neutralized framing)

def _norm(s):
    """Stable channel key: strip non-alphanumerics + Paperclip's dedup numeric suffix.
    So 'Daily Curiosities', 'daily-curiosities', 'daily-curiosities 6' all map to one channel."""
    return re.sub(r"\d+$", "", re.sub(r"[^a-z0-9]+", "", (s or "").lower()))

def _api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    if data: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            b = r.read().decode(); return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None   # Paperclip not running → no-op

def _as_list(x):
    return x if isinstance(x, list) else ((x or {}).get("projects") or (x or {}).get("data") or [])

def _company_id():
    code, comps = _api("GET", "/api/companies")
    for c in _as_list(comps) or (comps if isinstance(comps, list) else []):
        if c.get("name") == COMPANY_NAME:
            return c.get("id")
    cs = comps if isinstance(comps, list) else _as_list(comps)
    return cs[0].get("id") if cs else None

def _projects(cid):
    code, projects = _api("GET", f"/api/companies/{cid}/projects")
    return _as_list(projects) or (projects if isinstance(projects, list) else [])

def register_channel(slug, name, niche=""):
    """Find or create ONE canonical Paperclip project per channel. Returns project id (or None).
    Matches on a normalized key so name variants + dedup suffixes don't spawn duplicates."""
    cid = _company_id()
    if not cid: return None
    key = _norm(name)
    matches = [p for p in _projects(cid) if _norm(p.get("name")) == key]
    if matches:                                  # canonical = stable pick (shortest name, then id)
        matches.sort(key=lambda p: (len(p.get("name") or ""), p.get("name") or "", str(p.get("id"))))
        return matches[0].get("id")
    code, created = _api("POST", f"/api/companies/{cid}/projects",
                         {"name": name, "description": f"Content Engine channel · {niche}".strip()})
    return (created or {}).get("id")

def cleanup_duplicates(name):
    """Delete Content-Engine duplicate projects for a channel, keeping the canonical one.
    Best-effort: only touches projects whose description marks them as Content Engine channels."""
    cid = _company_id()
    if not cid: return 0
    key = _norm(name); keep = register_channel(name.lower().replace(" ", "-"), name)
    removed = 0
    for p in _projects(cid):
        if _norm(p.get("name")) != key or p.get("id") == keep:
            continue
        if "content engine channel" not in (p.get("description") or "").lower():
            continue                              # never delete legit business-unit projects
        code, _ = _api("DELETE", f"/api/projects/{p.get('id')}")
        if code in (200, 204): removed += 1
    return removed

def set_channel_summary(channel_name, text):
    """Set the channel project's description to a rollup summary (e.g. 'N shorts ready')."""
    pid = register_channel(channel_name.lower().replace(" ", "-"), channel_name)
    if not pid: return False
    _api("PATCH", f"/api/projects/{pid}", {"description": text})
    return True

def report_run(channel_name, run, status, output=""):
    """Surface a produced run onto the channel's Paperclip project (description summary)."""
    pid = register_channel(channel_name.lower().replace(" ", "-"), channel_name)
    if not pid: return False
    _api("PATCH", f"/api/projects/{pid}",
         {"description": f"Content Engine channel · latest run: {run} — {status}"
                         + (f" → {output.split('/')[-1]}" if output else "")})
    return True

if __name__ == "__main__":
    import sys
    print("company:", _company_id())
    if len(sys.argv) > 2:
        print("project:", register_channel(sys.argv[1], sys.argv[2]))
