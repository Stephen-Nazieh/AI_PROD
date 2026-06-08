#!/usr/bin/env python3
"""
project_dashboard.py — Web Dashboard for Production Progress

Serves HTML dashboard showing episode completion, shot progress,
audio status, quality gates, and pipeline stages.

Usage:
    python project_dashboard.py serve <project_slug> --port 8888
    python project_dashboard.py snapshot <project_slug>
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{project} — Dashboard</title>
<style>
body{{font-family:system-ui,sans-serif;margin:40px;background:#1a1a2e;color:#eee}}
h1{{color:#e94560}}h2{{color:#0f3460;border-bottom:2px solid #e94560;padding-bottom:8px}}
.card{{background:#16213e;border-radius:12px;padding:24px;margin:16px 0}}
.progress{{background:#0f3460;border-radius:8px;height:24px;overflow:hidden}}
.progress-bar{{background:#e94560;height:100%;width:{percent}%}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}}
.stat{{text-align:center;padding:16px}}
.stat-num{{font-size:48px;font-weight:bold;color:#e94560}}
.stat-label{{font-size:14px;color:#aaa;text-transform:uppercase}}
.shot{{display:inline-block;padding:6px 10px;margin:4px;border-radius:4px;font-size:12px}}
.done{{background:#1e5128;color:#4e9f3d}}.pending{{background:#3d2b1f;color:#d4a373}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #0f3460}}
th{{color:#e94560}}
</style></head><body>
<h1>{project}</h1><p>Updated: {timestamp}</p>
<div class="grid">
<div class="card"><div class="stat"><div class="stat-num">{total}</div><div class="stat-label">Shots</div></div></div>
<div class="card"><div class="stat"><div class="stat-num">{rendered}</div><div class="stat-label">Rendered</div></div></div>
<div class="card"><div class="stat"><div class="stat-num">{percent}%</div><div class="stat-label">Done</div></div></div>
<div class="card"><div class="stat"><div class="stat-num">{episodes}</div><div class="stat-label">Episodes</div></div></div>
</div>
<div class="card"><h2>Progress</h2><div class="progress"><div class="progress-bar"></div></div><p>{rendered}/{total} shots</p></div>
<div class="card"><h2>Shots</h2><p>{shots}</p></div>
<div class="card"><h2>Pipeline</h2><table>
<tr><th>Stage</th><th>Status</th></tr>
<tr><td>Screenplay</td><td>{s1}</td></tr>
<tr><td>Storyboards</td><td>{s2}</td></tr>
<tr><td>Characters</td><td>{s3}</td></tr>
<tr><td>Backgrounds</td><td>{s4}</td></tr>
<tr><td>Dialogue</td><td>{s5}</td></tr>
<tr><td>Music</td><td>{s6}</td></tr>
<tr><td>Rendering</td><td>{s7}</td></tr>
<tr><td>Editing</td><td>{s8}</td></tr>
<tr><td>Color</td><td>{s9}</td></tr>
<tr><td>Delivery</td><td>{s10}</td></tr>
</table></div>
</body></html>"""


def gather(project_slug: str) -> dict:
    d = Path(WORKSPACE_ROOT / "05_PROJECTS" / project_slug)
    shot_list = json.loads((d / "01-scripts" / "shot-list.json").read_text()) if (d / "01-scripts" / "shot-list.json").exists() else {"shots": []}
    shots = shot_list.get("shots", [])
    rendered = 0
    shot_html = ""
    for s in shots:
        sid = s["shot_id"]
        is_r = any((d / "04-raw_renders" / sid).rglob("*.png")) if (d / "04-raw_renders" / sid).exists() else False
        if is_r: rendered += 1
        shot_html += f'<span class="shot {'done' if is_r else 'pending'}">{sid}</span>'
    
    eps = 0
    if (d / "episodes" / "master_manifest.json").exists():
        eps = json.loads((d / "episodes" / "master_manifest.json").read_text()).get("total_episodes", 0)
    
    def check(path): return "yes" if path.exists() else "no"
    
    return {
        "project": project_slug, "timestamp": datetime.now().strftime("%H:%M:%S"),
        "total": len(shots), "rendered": rendered, "percent": round(rendered/max(len(shots),1)*100),
        "episodes": eps, "shots": shot_html,
        "s1": check(d / "01-scripts" / "shot-list.json"), "s2": "yes" if any((d / "02-storyboards").rglob("*.png")) else "no",
        "s3": "yes" if any((d / "05-assets").rglob("*.vrm")) else "no", "s4": "yes" if any((d / "05-assets" / "backgrounds_2d").rglob("*.png")) else "no",
        "s5": "yes" if any((d / "06-audio" / "dialogue").rglob("*.wav")) else "no", "s6": "yes" if any((d / "06-audio").rglob("*.wav")) else "no",
        "s7": f"{rendered}/{len(shots)}", "s8": "yes" if any((d / "07-editing").rglob("*.edl")) else "no",
        "s9": "yes" if any((d / "04-raw_renders").rglob("*_graded*")) else "no", "s10": "yes" if any((d / "09-deliver").rglob("*.mp4")) else "no",
    }


def serve(project_slug: str, port: int = 8888):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            data = gather(project_slug)
            self.wfile.write(HTML.format(**data).encode())
    print(f"Dashboard: http://localhost:{port}")
    HTTPServer(("0.0.0.0", port), H).serve_forever()


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("serve").add_argument("project_slug"); s.add_parser("snapshot").add_argument("project_slug")
    p.parse_args()._get_kwargs()
    args = p.parse_args()
    if args.cmd == "serve":
        serve(args.project_slug)
    else:
        print(json.dumps(gather(args.project_slug), indent=2))

if __name__ == "__main__":
    main()
