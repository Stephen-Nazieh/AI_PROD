#!/usr/bin/env python3
"""
render_farm_dispatcher.py — Distributed Render Farm via Paperclip

Dispatches shot renders as Paperclip issues, tracks progress, and aggregates
results. Designed to scale across multiple worker nodes (MLX-clustered Macs).

Usage:
    python render_farm_dispatcher.py dispatch <project_slug> [--engine cycles]
    python render_farm_dispatcher.py status <project_slug>
    python render_farm_dispatcher.py collect <project_slug>
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PAPERCLIP_URL = "http://localhost:3100"
COMPANY_ID = "15041ee2-b1c5-43ac-b488-04934bfa1806"
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def paperclip_post(path: str, payload: dict) -> dict:
    import urllib.request
    req = urllib.request.Request(
        f"{PAPERCLIP_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.read() else ""
        return {"status": "error", "code": e.code, "message": body or str(e)}


def paperclip_get(path: str) -> dict:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{PAPERCLIP_URL}{path}", timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.read() else ""
        return {"status": "error", "code": e.code, "message": body or str(e)}


def create_render_job(project_slug: str, shot_id: str, engine: str, frame_start: int, frame_end: int) -> dict:
    """Create a Paperclip issue for a render job."""
    title = f"Render {shot_id} ({engine})"
    body = f"""Project: {project_slug}
Shot: {shot_id}
Engine: {engine}
Frame range: {frame_start} - {frame_end}

Worker command:
python blender_render_dispatcher.py render {project_slug} --engine {engine} --shots {shot_id}
"""
    try:
        result = paperclip_post(f"/api/companies/{COMPANY_ID}/issues", {
            "title": title,
            "description": body,
            "status": "backlog",
            "priority": "medium",
            "labels": ["render", engine, project_slug],
        })
        if result.get("status") == "error":
            return {"status": "error", "message": result.get("message", "Unknown error")}
        return {"status": "ok", "issue_id": result.get("id"), "title": title}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def dispatch_project(project_slug: str, engine: str = "eevee", shots: list[str] = None) -> dict:
    """Create render jobs for all shots in a project."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"

    if not layout_path.exists():
        return {"status": "error", "message": f"Layout not found: {layout_path}"}

    # Load shot list from Blender file
    blender_script = "import bpy, json\nshots = []\nfor obj in bpy.context.scene.objects:\n    if obj.type == 'CAMERA' and obj.name.startswith('CAM_'):\n        shots.append({'shot_id': obj.get('shot_id', obj.name[4:]), 'frame_start': obj.get('layout_frame_start', 1), 'frame_end': obj.get('layout_frame_end', 1)})\nprint(json.dumps(shots))"
    result = subprocess.run([
        BLENDER_BINARY, "--background", str(layout_path),
        "--python-expr", blender_script,
    ], capture_output=True, text=True, timeout=60)

    shot_data = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            try:
                shot_data = json.loads(line)
                break
            except Exception:
                pass

    if shots:
        shot_data = [s for s in shot_data if s["shot_id"] in shots]

    jobs = []
    for shot in shot_data:
        job = create_render_job(
            project_slug, shot["shot_id"], engine,
            shot["frame_start"], shot["frame_end"]
        )
        jobs.append(job)
        time.sleep(0.2)

    return {
        "status": "ok",
        "project": project_slug,
        "engine": engine,
        "total_jobs": len(jobs),
        "jobs": jobs,
    }


def check_status(project_slug: str) -> dict:
    """Check Paperclip for render job status."""
    try:
        result = paperclip_get(f"/api/companies/{COMPANY_ID}/issues")
        if isinstance(result, dict) and result.get("status") == "error":
            return {"status": "error", "message": result.get("message", "Unknown error")}
        issues = result if isinstance(result, list) else result.get("issues", []) if isinstance(result, dict) else []
        render_issues = [i for i in issues if isinstance(i, dict) and (project_slug in (i.get("labels", []) or []) or project_slug in (i.get("title", "") or ""))]
        return {
            "status": "ok",
            "project": project_slug,
            "total_issues": len(render_issues),
            "issues": [{"id": i.get("id"), "title": i.get("title"), "state": i.get("state")} for i in render_issues],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def collect_results(project_slug: str) -> dict:
    """Check for rendered output files."""
    renders_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug / "04-raw_renders"
    if not renders_dir.exists():
        return {"status": "ok", "project": project_slug, "shots": [], "total_frames": 0}

    shots = []
    total_frames = 0
    for shot_dir in sorted(renders_dir.iterdir()):
        if shot_dir.is_dir():
            frames = list(shot_dir.glob("*.png"))
            total_frames += len(frames)
            shots.append({
                "shot_id": shot_dir.name,
                "frame_count": len(frames),
                "output_dir": str(shot_dir),
            })

    return {
        "status": "ok",
        "project": project_slug,
        "shots": shots,
        "total_frames": total_frames,
        "renders_dir": str(renders_dir),
    }


def main():
    parser = argparse.ArgumentParser(description="Render Farm Dispatcher")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dispatch = sub.add_parser("dispatch", help="Dispatch render jobs")
    p_dispatch.add_argument("project_slug")
    p_dispatch.add_argument("--engine", default="eevee")
    p_dispatch.add_argument("--shots", help="Comma-separated shot IDs")

    p_status = sub.add_parser("status", help="Check render job status")
    p_status.add_argument("project_slug")

    p_collect = sub.add_parser("collect", help="Collect render results")
    p_collect.add_argument("project_slug")

    args = parser.parse_args()

    if args.command == "dispatch":
        shots = [s.strip() for s in args.shots.split(",")] if args.shots else None
        result = dispatch_project(args.project_slug, engine=args.engine, shots=shots)
        print(json.dumps(result, indent=2))

    elif args.command == "status":
        result = check_status(args.project_slug)
        print(json.dumps(result, indent=2))

    elif args.command == "collect":
        result = collect_results(args.project_slug)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
