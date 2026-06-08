#!/usr/bin/env python3
"""
parallel_renderer.py — Parallel Shot Rendering with Worker Pool

Renders multiple shots simultaneously using Python multiprocessing.
Dramatically speeds up production by utilizing all CPU cores.

Usage:
    python parallel_renderer.py render <project_slug> --engine eevee --workers 8
    python parallel_renderer.py render <project_slug> --shots SC001_SH001,SC001_SH002 --workers 4
"""

import argparse
import hashlib
import json
import multiprocessing
import os
import subprocess
import time
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"


def _shot_hash(shot: dict, engine: str, width: int, height: int) -> str:
    """Compute hash of shot parameters for cache invalidation."""
    data = json.dumps({
        "shot_id": shot["shot_id"],
        "scene_id": shot.get("scene_id", ""),
        "shot_type": shot.get("shot_type", ""),
        "camera_movement": shot.get("camera_movement", ""),
        "action": shot.get("action", ""),
        "engine": engine,
        "width": width,
        "height": height,
    }, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def render_shot_2d(args: dict) -> dict:
    """Render a single 2D shot (called by worker pool)."""
    project_slug = args["project_slug"]
    shot_id = args["shot_id"]
    duration = args.get("duration", 3.0)
    
    start = time.time()
    
    # Run 2D compositor
    result = subprocess.run([
        "python3", str(WORKSPACE_ROOT / "01_SKILLS" / "animation_2d_compositor.py"),
        "composite", project_slug, "--shot", shot_id, "--duration", str(duration),
    ], capture_output=True, text=True, cwd=WORKSPACE_ROOT)
    
    elapsed = time.time() - start
    
    try:
        data = json.loads(result.stdout.split("\n")[-2] if result.stdout else "{}")
        data["render_time_sec"] = round(elapsed, 2)
        return data
    except Exception:
        return {
            "status": "error",
            "shot_id": shot_id,
            "error": result.stderr[:200] if result.stderr else "Unknown error",
            "render_time_sec": round(elapsed, 2),
        }


def render_shot_3d(args: dict) -> dict:
    """Render a single 3D shot via Blender CLI (called by worker pool)."""
    project_slug = args["project_slug"]
    shot_id = args["shot_id"]
    engine = args.get("engine", "eevee")
    width = args.get("width", 1920)
    height = args.get("height", 1080)
    
    start = time.time()
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    output_dir = project_dir / "04-raw_renders" / shot_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build Blender render script
    blender_script = f'''
import bpy
bpy.ops.wm.open_mainfile(filepath=r"{str(layout_path)}")

# Find camera for this shot
for obj in bpy.context.scene.objects:
    if obj.type == "CAMERA" and "{shot_id}" in obj.name:
        bpy.context.scene.camera = obj
        break

bpy.context.scene.render.engine = "{engine.upper()}"
bpy.context.scene.render.resolution_x = {width}
bpy.context.scene.render.resolution_y = {height}
bpy.context.scene.render.filepath = r"{str(output_dir)}/frame_"
bpy.context.scene.render.image_settings.file_format = "PNG"
bpy.context.scene.frame_set(1)
bpy.ops.render.render(write_still=True)
'''
    
    script_path = output_dir / "_render.py"
    script_path.write_text(blender_script, encoding="utf-8")
    
    result = subprocess.run([
        BLENDER, "--background", "--python", str(script_path),
    ], capture_output=True, text=True, timeout=300)
    
    elapsed = time.time() - start
    
    return {
        "status": "ok" if result.returncode == 0 else "error",
        "shot_id": shot_id,
        "engine": engine,
        "render_time_sec": round(elapsed, 2),
        "output_dir": str(output_dir),
    }


def parallel_render(project_slug: str, shot_ids: list = None, engine: str = "eevee",
                    workers: int = None, mode: str = "2d") -> dict:
    """Render multiple shots in parallel."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    shot_list = json.loads((project_dir / "01-scripts" / "shot-list.json").read_text(encoding="utf-8"))
    
    shots = shot_list.get("shots", [])
    if shot_ids:
        shots = [s for s in shots if s["shot_id"] in shot_ids]
    
    if not shots:
        return {"status": "error", "message": "No shots to render"}
    
    workers = workers or min(os.cpu_count(), len(shots))
    render_fn = render_shot_2d if mode == "2d" else render_shot_3d
    
    # Build task list
    tasks = []
    for shot in shots:
        tasks.append({
            "project_slug": project_slug,
            "shot_id": shot["shot_id"],
            "duration": shot.get("duration_seconds", 3.0),
            "engine": engine,
        })
    
    start = time.time()
    
    # Render in parallel
    with multiprocessing.Pool(processes=workers) as pool:
        results = pool.map(render_fn, tasks)
    
    total_time = time.time() - start
    
    successes = sum(1 for r in results if r.get("status") == "ok")
    total_render_time = sum(r.get("render_time_sec", 0) for r in results)
    
    return {
        "status": "ok",
        "project": project_slug,
        "mode": mode,
        "total_shots": len(shots),
        "successful": successes,
        "failed": len(shots) - successes,
        "workers": workers,
        "parallel_time_sec": round(total_time, 2),
        "sequential_time_sec": round(total_render_time, 2),
        "speedup": round(total_render_time / max(total_time, 0.01), 2),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Parallel Renderer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="Render shots in parallel")
    p_render.add_argument("project_slug")
    p_render.add_argument("--shots", help="Comma-separated shot IDs")
    p_render.add_argument("--engine", default="eevee")
    p_render.add_argument("--workers", type=int)
    p_render.add_argument("--mode", default="2d", choices=["2d", "3d"])

    args = parser.parse_args()

    if args.command == "render":
        shot_ids = args.shots.split(",") if args.shots else None
        result = parallel_render(args.project_slug, shot_ids, args.engine, args.workers, args.mode)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
