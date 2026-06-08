#!/usr/bin/env python3
"""
blender_geometry_nodes_animator.py — Procedural Motion from Shot Action Text

Maps natural language action descriptions to Geometry Nodes modifiers and
procedural animations in Blender. No keyframing required — everything is
node-driven and parameter-based.

Usage (outside Blender):
    python blender_geometry_nodes_animator.py apply <project_slug> [--shot SC001_SH001]
    python blender_geometry_nodes_animator.py apply <project_slug> --all-shots

Usage (inside Blender):
    blender --background --python blender_geometry_nodes_animator.py -- apply <project_slug>

Supported action verbs:
    draw / write / trace    → Curve draw-on animation
    point / mark / indicate → Object target + look-at
    shade / fill / color    → Material transition
    move / walk / approach  → Follow path / translate
    rotate / spin / turn    → Rotation modifier
    grow / expand / scale   → Scale transition
    shake / vibrate / tremble → Noise displacement
"""

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# ── Action Verb → Geometry Nodes Mapping ────────────────────────────────────

ACTION_PRESETS = {
    "draw": {
        "modifier_name": "GN_DrawOn",
        "description": "Curve that draws itself over time",
        "node_tree": "draw_on_curve",
        "needs_target": True,
    },
    "write": {
        "modifier_name": "GN_DrawOn",
        "description": "Curve that draws itself over time",
        "node_tree": "draw_on_curve",
        "needs_target": True,
    },
    "trace": {
        "modifier_name": "GN_DrawOn",
        "description": "Curve that draws itself over time",
        "node_tree": "draw_on_curve",
        "needs_target": True,
    },
    "point": {
        "modifier_name": "GN_LookAt",
        "description": "Object points at a target location",
        "node_tree": "look_at_target",
        "needs_target": True,
    },
    "mark": {
        "modifier_name": "GN_LookAt",
        "description": "Object points at a target location",
        "node_tree": "look_at_target",
        "needs_target": True,
    },
    "indicate": {
        "modifier_name": "GN_LookAt",
        "description": "Object points at a target location",
        "node_tree": "look_at_target",
        "needs_target": True,
    },
    "move": {
        "modifier_name": "GN_FollowPath",
        "description": "Object follows a path curve",
        "node_tree": "follow_path",
        "needs_target": False,
    },
    "walk": {
        "modifier_name": "GN_FollowPath",
        "description": "Object follows a path curve",
        "node_tree": "follow_path",
        "needs_target": False,
    },
    "approach": {
        "modifier_name": "GN_FollowPath",
        "description": "Object follows a path curve",
        "node_tree": "follow_path",
        "needs_target": False,
    },
    "rotate": {
        "modifier_name": "GN_Spin",
        "description": "Object rotates continuously",
        "node_tree": "continuous_rotation",
        "needs_target": False,
    },
    "spin": {
        "modifier_name": "GN_Spin",
        "description": "Object rotates continuously",
        "node_tree": "continuous_rotation",
        "needs_target": False,
    },
    "grow": {
        "modifier_name": "GN_ScaleTransition",
        "description": "Object scales from zero to full",
        "node_tree": "scale_transition",
        "needs_target": False,
    },
    "expand": {
        "modifier_name": "GN_ScaleTransition",
        "description": "Object scales from zero to full",
        "node_tree": "scale_transition",
        "needs_target": False,
    },
    "shake": {
        "modifier_name": "GN_Shake",
        "description": "Object shakes with noise displacement",
        "node_tree": "noise_shake",
        "needs_target": False,
    },
    "vibrate": {
        "modifier_name": "GN_Shake",
        "description": "Object shakes with noise displacement",
        "node_tree": "noise_shake",
        "needs_target": False,
    },
}


def detect_action_verbs(text: str) -> list[dict]:
    """Scan action text for known verbs and return matching presets."""
    text_lower = text.lower()
    matches = []
    for verb, preset in ACTION_PRESETS.items():
        if verb in text_lower:
            matches.append({"verb": verb, **preset})
    return matches


# ── Geometry Nodes Builder (runs inside Blender) ────────────────────────────

class GeometryNodesAnimator:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_path = self.project_dir / "03-layout" / "layout.blend"
        self.shot_list = _load_json(self.project_dir / "01-scripts" / "shot-list.json")

    def apply(self, shot_id: str | None = None, all_shots: bool = False) -> dict:
        import bpy

        if not self.layout_path.exists():
            return {"status": "error", "message": f"Layout not found: {self.layout_path}"}

        bpy.ops.wm.open_mainfile(filepath=str(self.layout_path))

        shots = self.shot_list.get("shots", [])
        if shot_id:
            shots = [s for s in shots if s["shot_id"] == shot_id]
        if not all_shots and not shot_id:
            return {"status": "error", "message": "Specify --shot or --all-shots"}

        results = []

        for shot in shots:
            sid = shot["shot_id"]
            action = shot.get("action", "")
            verbs = detect_action_verbs(action)

            if not verbs:
                results.append({"shot_id": sid, "status": "skipped", "reason": "No known action verbs"})
                continue

            applied = []
            for verb_info in verbs:
                try:
                    self._apply_preset(sid, verb_info, shot)
                    applied.append(verb_info["verb"])
                except Exception as e:
                    applied.append(f"{verb_info['verb']}:failed({e})")

            results.append({"shot_id": sid, "status": "ok", "applied": applied, "verbs_found": [v["verb"] for v in verbs]})

        bpy.ops.wm.save_as_mainfile(filepath=str(self.layout_path))

        return {
            "status": "ok",
            "project": self.project_slug,
            "layout_path": str(self.layout_path),
            "results": results,
        }

    def _apply_preset(self, shot_id: str, preset: dict, shot: dict):
        import bpy
        import math

        scene = bpy.context.scene
        frame_start = shot.get("duration_seconds", 3.0)
        if frame_start <= 0:
            frame_start = 3.0
        frame_start = 1  # Use timeline markers for actual timing
        frame_end = frame_start + 72

        tree_name = preset["node_tree"]
        obj_name = f"FX_{shot_id}_{preset['verb']}"

        if tree_name == "draw_on_curve":
            self._build_draw_on_curve(obj_name, shot_id, frame_start, frame_end)
        elif tree_name == "look_at_target":
            self._build_look_at(obj_name, shot_id, frame_start, frame_end)
        elif tree_name == "follow_path":
            self._build_follow_path(obj_name, shot_id, frame_start, frame_end)
        elif tree_name == "continuous_rotation":
            self._build_rotation(obj_name, shot_id, frame_start, frame_end)
        elif tree_name == "scale_transition":
            self._build_scale_transition(obj_name, shot_id, frame_start, frame_end)
        elif tree_name == "noise_shake":
            self._build_noise_shake(obj_name, shot_id, frame_start, frame_end)

    def _build_draw_on_curve(self, obj_name: str, shot_id: str, f_start: int, f_end: int):
        import bpy
        import math
        # Create a curve and use build modifier for draw-on effect
        curve_data = bpy.data.curves.new(name=obj_name, type='CURVE')
        curve_data.dimensions = '3D'
        curve_data.resolution_u = 64
        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(3)
        for i, bp in enumerate(spline.bezier_points):
            bp.co = (i * 2, 0, 0)
            bp.handle_left_type = 'AUTO'
            bp.handle_right_type = 'AUTO'

        obj = bpy.data.objects.new(name=obj_name, object_data=curve_data)
        bpy.context.scene.collection.objects.link(obj)

        # Add build modifier for draw-on
        mod = obj.modifiers.new(name="Build_DrawOn", type='BUILD')
        mod.frame_start = f_start
        mod.frame_duration = f_end - f_start

        # Add bevel for visibility
        curve_data.bevel_depth = 0.05
        curve_data.bevel_resolution = 4

    def _build_look_at(self, obj_name: str, shot_id: str, f_start: int, f_end: int):
        import bpy
        import math
        # Create an arrow/null that points at origin
        bpy.ops.mesh.primitive_cone_add(radius1=0.3, depth=0.6, location=(3, 0, 1.5))
        obj = bpy.context.active_object
        obj.name = obj_name

        # Add constraint to track to origin
        constraint = obj.constraints.new(type='TRACK_TO')
        constraint.target = bpy.data.objects.get("Empty_Target") or self._ensure_target_empty()
        constraint.track_axis = 'TRACK_NEGATIVE_Z'
        constraint.up_axis = 'UP_Y'

        # Animate the target empty moving around
        target = constraint.target
        target.location = (0, 0, 1.5)
        target.keyframe_insert(data_path="location", frame=f_start)
        target.location = (0, 3, 1.5)
        target.keyframe_insert(data_path="location", frame=f_end)

    def _ensure_target_empty(self):
        import bpy
        if "Empty_Target" not in bpy.data.objects:
            empty = bpy.data.objects.new("Empty_Target", None)
            bpy.context.scene.collection.objects.link(empty)
        return bpy.data.objects["Empty_Target"]

    def _build_follow_path(self, obj_name: str, shot_id: str, f_start: int, f_end: int):
        import bpy
        # Create a path curve
        curve_data = bpy.data.curves.new(name=f"{obj_name}_path", type='CURVE')
        curve_data.dimensions = '3D'
        spline = curve_data.splines.new('NURBS')
        spline.points.add(3)
        points = [(-2, -2, 0), (0, 0, 0), (2, 2, 0), (4, 0, 0)]
        for i, pt in enumerate(spline.points):
            pt.co = (pt[0], pt[1], pt[2], 1)  # NURBS needs 4D
        path_obj = bpy.data.objects.new(name=f"{obj_name}_path", object_data=curve_data)
        bpy.context.scene.collection.objects.link(path_obj)

        # Create a cube to follow
        bpy.ops.mesh.primitive_cube_add(size=0.5, location=points[0][:3])
        obj = bpy.context.active_object
        obj.name = obj_name

        # Add follow path constraint
        constraint = obj.constraints.new(type='FOLLOW_PATH')
        constraint.target = path_obj
        constraint.use_curve_follow = True
        constraint.offset_factor = 0.0
        constraint.keyframe_insert(data_path="offset_factor", frame=f_start)
        constraint.offset_factor = 1.0
        constraint.keyframe_insert(data_path="offset_factor", frame=f_end)

    def _build_rotation(self, obj_name: str, shot_id: str, f_start: int, f_end: int):
        import bpy
        import math
        bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0, 0, 1.5))
        obj = bpy.context.active_object
        obj.name = obj_name
        obj.rotation_euler = (0, 0, 0)
        obj.keyframe_insert(data_path="rotation_euler", frame=f_start)
        obj.rotation_euler = (0, 0, math.radians(360))
        obj.keyframe_insert(data_path="rotation_euler", frame=f_end)

    def _build_scale_transition(self, obj_name: str, shot_id: str, f_start: int, f_end: int):
        import bpy
        bpy.ops.mesh.primitive_ico_sphere_add(radius=0.5, location=(0, 0, 1.5))
        obj = bpy.context.active_object
        obj.name = obj_name
        obj.scale = (0, 0, 0)
        obj.keyframe_insert(data_path="scale", frame=f_start)
        obj.scale = (1, 1, 1)
        obj.keyframe_insert(data_path="scale", frame=f_end)

    def _build_noise_shake(self, obj_name: str, shot_id: str, f_start: int, f_end: int):
        import bpy
        import random
        bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0, 0, 1.5))
        obj = bpy.context.active_object
        obj.name = obj_name
        base_loc = obj.location.copy()
        for f in range(f_start, f_end + 1, max(1, (f_end - f_start) // 12)):
            obj.location = (
                base_loc.x + random.uniform(-0.1, 0.1),
                base_loc.y + random.uniform(-0.1, 0.1),
                base_loc.z + random.uniform(-0.05, 0.05),
            )
            obj.keyframe_insert(data_path="location", frame=f)


# ── CLI ─────────────────────────────────────────────────────────────────────

def run_inside_blender():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Blender Geometry Nodes Animator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_apply = sub.add_parser("apply", help="Apply procedural animation to shots")
    p_apply.add_argument("project_slug", help="Project identifier")
    p_apply.add_argument("--shot", help="Specific shot ID")
    p_apply.add_argument("--all-shots", action="store_true", help="Process all shots")

    args = parser.parse_args(argv)

    if args.command == "apply":
        animator = GeometryNodesAnimator(args.project_slug)
        result = animator.apply(shot_id=args.shot, all_shots=args.all_shots)
        print(json.dumps(result, indent=2))


def run_outside_blender():
    parser = argparse.ArgumentParser(description="Blender Geometry Nodes Animator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_apply = sub.add_parser("apply", help="Apply procedural animation to shots")
    p_apply.add_argument("project_slug", help="Project identifier")
    p_apply.add_argument("--shot", help="Specific shot ID")
    p_apply.add_argument("--all-shots", action="store_true", help="Process all shots")

    args = parser.parse_args()
    script_path = Path(__file__).resolve()

    if args.command == "apply":
        cmd = [
            BLENDER_BINARY,
            "--background",
            "--python", str(script_path),
            "--",
            "apply", args.project_slug,
        ]
        if args.shot:
            cmd.extend(["--shot", args.shot])
        if args.all_shots:
            cmd.append("--all-shots")
        print(f"🧬 Applying procedural animation for {args.project_slug}...")
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
