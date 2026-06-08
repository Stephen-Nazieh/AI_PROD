#!/usr/bin/env python3
"""
blender_grease_pencil.py — Storyboard → Grease Pencil Timeline Converter

Converts storyboard frames into timed Grease Pencil layers for 2D/3D hybrid
animation, animatic review, or draw-over workflows.

Usage (outside Blender):
    python blender_grease_pencil.py build <project_slug>
    python blender_grease_pencil.py build <project_slug> --opacity 0.8

Usage (inside Blender):
    blender --background --python blender_grease_pencil.py -- build <project_slug>

Output:
    05_PROJECTS/<project_slug>/03-layout/layout_gpencil.blend
    - Grease Pencil object with one layer per shot
    - Storyboard images as image references on GPencil strokes
    - Timed visibility matching shot markers
    - Additional blank "sketch" layers for animation draw-over
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"


# ── Grease Pencil Builder (runs inside Blender) ─────────────────────────────

class GreasePencilBuilder:
    def __init__(self, project_slug: str, opacity: float = 0.7, add_sketch_layers: bool = True):
        self.project_slug = project_slug
        self.opacity = opacity
        self.add_sketch_layers = add_sketch_layers

        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_path = self.project_dir / "03-layout" / "layout.blend"
        self.output_path = self.project_dir / "03-layout" / "layout_gpencil.blend"

        self.shot_list = self._load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.manifest = self._load_json(self.project_dir / "02-storyboards" / "storyboard_manifest.json")

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def build(self) -> dict:
        import bpy

        if not self.layout_path.exists():
            return {"status": "error", "message": f"Layout not found: {self.layout_path}"}

        bpy.ops.wm.open_mainfile(filepath=str(self.layout_path))
        scene = bpy.context.scene

        # Create Grease Pencil object
        gp_data = bpy.data.grease_pencils.new(name="Storyboard_GP")
        gp_obj = bpy.data.objects.new(name="Storyboard_GP", object_data=gp_data)
        scene.collection.objects.link(gp_obj)

        # Create a base frame layer for timing reference
        base_layer = gp_data.layers.new(name="_timing", set_active=True)
        base_frame = base_layer.frames.new(frame_number=1)

        shots = self.shot_list.get("shots", [])
        frame_lookup = {f["shot_id"]: f for f in self.manifest.get("frames", [])}
        fps = scene.render.fps
        current_frame = 1

        created_layers = []

        for shot in shots:
            shot_id = shot["shot_id"]
            frame_data = frame_lookup.get(shot_id, {})
            img_path = frame_data.get("output_path")

            duration = shot.get("duration_seconds", 3.0)
            if duration <= 0:
                duration = 3.0
            frame_end = current_frame + int(duration * fps) - 1

            # Create layer for this shot
            layer = gp_data.layers.new(name=shot_id, set_active=False)
            layer.opacity = self.opacity
            layer.blend_mode = 'REGULAR'

            # Add frame at shot start
            gpf = layer.frames.new(frame_number=current_frame)

            # Create an image stroke (reference)
            if img_path and Path(img_path).exists():
                try:
                    img = bpy.data.images.load(str(img_path), check_existing=True)
                    # Create a rectangle stroke as image reference frame
                    aspect = img.size[0] / img.size[1] if img.size[1] > 0 else 1.78
                    h = 3.0  # world units height
                    w = h * aspect

                    # Add stroke with 4 points (rectangle)
                    gpf.drawing.add_strokes(sizes=[4])
                    stroke = gpf.drawing.strokes[-1]
                    stroke.cyclic = True
                    stroke.material_index = 0

                    points = [
                        (-w/2, 0, -h/2),
                        (w/2, 0, -h/2),
                        (w/2, 0, h/2),
                        (-w/2, 0, h/2),
                    ]
                    for i, co in enumerate(points):
                        stroke.points[i].position = co

                except Exception as e:
                    print(f"  ⚠️ Could not load image for {shot_id}: {e}")

            # Add blank sketch layer if requested
            if self.add_sketch_layers:
                sketch_layer = gp_data.layers.new(name=f"{shot_id}_sketch", set_active=False)
                sketch_layer.opacity = 1.0
                sketch_gpf = sketch_layer.frames.new(frame_number=current_frame)
                # Add a small note stroke
                sketch_gpf.drawing.add_strokes(sizes=[2])
                stroke = sketch_gpf.drawing.strokes[-1]
                stroke.points[0].position = (-2, 0, 2)
                stroke.points[1].position = (2, 0, 2)

            created_layers.append({
                "shot_id": shot_id,
                "layer": layer.name,
                "frame_start": current_frame,
                "frame_end": frame_end,
                "has_image": img_path is not None and Path(img_path).exists(),
            })

            current_frame += int(duration * fps)

        # Save as separate file (don't overwrite layout)
        bpy.ops.wm.save_as_mainfile(filepath=str(self.output_path))

        return {
            "status": "ok",
            "project": self.project_slug,
            "output_path": str(self.output_path),
            "source_layout": str(self.layout_path),
            "layers": created_layers,
            "total_layers": len(created_layers),
        }


# ── CLI ─────────────────────────────────────────────────────────────────────

def run_inside_blender():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Blender Grease Pencil Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build Grease Pencil storyboard from layout")
    p_build.add_argument("project_slug", help="Project identifier")
    p_build.add_argument("--opacity", type=float, default=0.7, help="Layer opacity (0-1)")
    p_build.add_argument("--no-sketch", action="store_true", help="Skip sketch layers")

    args = parser.parse_args(argv)

    if args.command == "build":
        builder = GreasePencilBuilder(
            args.project_slug,
            opacity=args.opacity,
            add_sketch_layers=not args.no_sketch,
        )
        result = builder.build()
        print(json.dumps(result, indent=2))


def run_outside_blender():
    parser = argparse.ArgumentParser(description="Blender Grease Pencil Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build Grease Pencil storyboard from layout")
    p_build.add_argument("project_slug", help="Project identifier")
    p_build.add_argument("--opacity", type=float, default=0.7, help="Layer opacity (0-1)")
    p_build.add_argument("--no-sketch", action="store_true", help="Skip sketch layers")

    args = parser.parse_args()
    script_path = Path(__file__).resolve()

    if args.command == "build":
        cmd = [
            BLENDER_BINARY,
            "--background",
            "--python", str(script_path),
            "--",
            "build", args.project_slug,
            "--opacity", str(args.opacity),
        ]
        if args.no_sketch:
            cmd.append("--no-sketch")
        print(f"✏️ Building Grease Pencil storyboard for {args.project_slug}...")
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
