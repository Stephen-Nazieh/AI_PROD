#!/usr/bin/env python3
"""
blender_render_dispatcher.py — Batch Shot Renderer for Blender Layout

Renders each shot from a layout .blend file as individual image sequences
or still frames. Supports both Eevee (fast previz) and Cycles (final quality).

Usage (outside Blender):
    python blender_render_dispatcher.py render <project_slug> [--engine eevee] [--shots SC001_SH001,SC001_SH002]
    python blender_render_dispatcher.py render <project_slug> --still-frames
    python blender_render_dispatcher.py render <project_slug> --engine cycles --samples 256

Usage (inside Blender):
    blender --background --python blender_render_dispatcher.py -- render <project_slug>

Output:
    05_PROJECTS/<project_slug>/04-raw_renders/<shot_id>/frame_####.png
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"


# ── Render Dispatcher (runs inside Blender) ─────────────────────────────────

class RenderDispatcher:
    def __init__(self, project_slug: str, engine: str = "eevee", samples: int = None,
                 still_frames: bool = False, shot_ids: list[str] = None,
                 width: int = None, height: int = None):
        self.project_slug = project_slug
        self.engine = engine
        self.samples = samples
        self.still_frames = still_frames
        self.shot_ids = shot_ids
        self.width = width
        self.height = height

        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_path = self.project_dir / "03-layout" / "layout.blend"
        self.output_dir = self.project_dir / "04-raw_renders"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render(self) -> dict:
        import bpy

        if not self.layout_path.exists():
            return {"status": "error", "message": f"Layout not found: {self.layout_path}"}

        bpy.ops.wm.open_mainfile(filepath=str(self.layout_path))
        scene = bpy.context.scene

        # Configure render engine
        if self.engine == "cycles":
            scene.render.engine = "CYCLES"
            scene.cycles.device = "GPU"
            if self.samples:
                scene.cycles.samples = self.samples
            else:
                scene.cycles.samples = 128
        else:
            scene.render.engine = "BLENDER_EEVEE"

        # Configure resolution
        if self.width:
            scene.render.resolution_x = self.width
        if self.height:
            scene.render.resolution_y = self.height

        # Find all shot cameras
        shot_cameras = []
        for obj in scene.objects:
            if obj.type == "CAMERA" and obj.name.startswith("CAM_"):
                shot_id = obj.get("shot_id", obj.name[4:])
                if self.shot_ids and shot_id not in self.shot_ids:
                    continue
                frame_start = obj.get("layout_frame_start", 1)
                frame_end = obj.get("layout_frame_end", frame_start)
                shot_cameras.append({
                    "shot_id": shot_id,
                    "camera": obj,
                    "frame_start": frame_start,
                    "frame_end": frame_end,
                })

        if not shot_cameras:
            return {"status": "error", "message": "No shot cameras found in layout"}

        # Sort by frame start
        shot_cameras.sort(key=lambda x: x["frame_start"])

        rendered = []
        failed = []

        for shot in shot_cameras:
            shot_id = shot["shot_id"]
            cam = shot["camera"]
            frame_start = shot["frame_start"]
            frame_end = shot["frame_end"]

            # Set active camera
            scene.camera = cam

            # Configure output
            shot_output_dir = self.output_dir / shot_id
            shot_output_dir.mkdir(parents=True, exist_ok=True)
            scene.render.filepath = str(shot_output_dir / "frame_")
            scene.render.image_settings.file_format = "PNG"
            scene.render.image_settings.color_mode = "RGBA"

            try:
                if self.still_frames:
                    # Render a single representative frame (middle of shot)
                    mid_frame = (frame_start + frame_end) // 2
                    scene.frame_set(mid_frame)
                    scene.frame_start = mid_frame
                    scene.frame_end = mid_frame
                    bpy.ops.render.render(write_still=True)
                    rendered.append({
                        "shot_id": shot_id,
                        "frame": mid_frame,
                        "output_dir": str(shot_output_dir),
                        "mode": "still",
                    })
                else:
                    # Render animation for the shot duration
                    scene.frame_start = frame_start
                    scene.frame_end = frame_end
                    bpy.ops.render.render(animation=True)
                    rendered.append({
                        "shot_id": shot_id,
                        "frame_start": frame_start,
                        "frame_end": frame_end,
                        "output_dir": str(shot_output_dir),
                        "mode": "animation",
                    })
            except Exception as e:
                failed.append({"shot_id": shot_id, "error": str(e)})

        return {
            "status": "ok",
            "project": self.project_slug,
            "engine": self.engine,
            "still_frames": self.still_frames,
            "total_shots": len(shot_cameras),
            "rendered": rendered,
            "failed": failed,
            "output_dir": str(self.output_dir),
        }


# ── CLI ─────────────────────────────────────────────────────────────────────

def run_inside_blender():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Blender Render Dispatcher")
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="Render shots from layout")
    p_render.add_argument("project_slug", help="Project identifier")
    p_render.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    p_render.add_argument("--samples", type=int, help="Cycles samples (default: 128)")
    p_render.add_argument("--still-frames", action="store_true", help="Render one still per shot instead of animation")
    p_render.add_argument("--shots", help="Comma-separated shot IDs (default: all)")
    p_render.add_argument("--width", type=int, help="Render width")
    p_render.add_argument("--height", type=int, help="Render height")

    args = parser.parse_args(argv)

    if args.command == "render":
        shot_ids = [s.strip() for s in args.shots.split(",")] if args.shots else None
        dispatcher = RenderDispatcher(
            args.project_slug,
            engine=args.engine,
            samples=args.samples,
            still_frames=args.still_frames,
            shot_ids=shot_ids,
            width=args.width,
            height=args.height,
        )
        result = dispatcher.render()
        print(json.dumps(result, indent=2))


def run_outside_blender():
    parser = argparse.ArgumentParser(description="Blender Render Dispatcher")
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="Render shots from layout")
    p_render.add_argument("project_slug", help="Project identifier")
    p_render.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    p_render.add_argument("--samples", type=int, help="Cycles samples")
    p_render.add_argument("--still-frames", action="store_true", help="Render one still per shot")
    p_render.add_argument("--shots", help="Comma-separated shot IDs")
    p_render.add_argument("--width", type=int, help="Render width")
    p_render.add_argument("--height", type=int, help="Render height")

    args = parser.parse_args()
    script_path = Path(__file__).resolve()

    if args.command == "render":
        cmd = [
            BLENDER_BINARY,
            "--background",
            "--python", str(script_path),
            "--",
            "render", args.project_slug,
            "--engine", args.engine,
        ]
        if args.samples:
            cmd.extend(["--samples", str(args.samples)])
        if args.still_frames:
            cmd.append("--still-frames")
        if args.shots:
            cmd.extend(["--shots", args.shots])
        if args.width:
            cmd.extend(["--width", str(args.width)])
        if args.height:
            cmd.extend(["--height", str(args.height)])
        print(f"🎬 Rendering {args.project_slug} with {args.engine}...")
        subprocess.run(cmd, check=True)


def main():
    try:
        import bpy
        INSIDE_BLENDER = True
    except ImportError:
        INSIDE_BLENDER = False

    if INSIDE_BLENDER:
        run_inside_blender()
    else:
        run_outside_blender()


if __name__ == "__main__":
    main()
