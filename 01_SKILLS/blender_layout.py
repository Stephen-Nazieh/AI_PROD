#!/usr/bin/env python3
"""
blender_layout.py — Storyboard → Blender Layout Converter

Autonomously converts storyboard frames and shot metadata into a Blender
layout scene ready for animation, blocking, and previz.

Usage (outside Blender):
    python blender_layout.py layout ap-stats-movie --engine eevee
    python blender_layout.py layout ap-stats-movie --engine cycles

Usage (inside Blender):
    blender --background --python blender_layout.py -- layout ap-stats-movie

Output:
    05_PROJECTS/<project_slug>/03-layout/layout.blend
    - One scene per project
    - One camera per shot with storyboard as background reference
    - Timeline markers for shot boundaries
    - Lighting based on INT/EXT + DAY/NIGHT
    - Basic floor geometry
    - Shot metadata stored as custom properties
"""

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

# ── Paths ───────────────────────────────────────────────────────────────────

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"

# ── Shot Type Camera Mapping ────────────────────────────────────────────────

SHOT_CAMERA_PRESETS = {
    "wide":           {"focal_length": 35,  "distance": 8.0,  "height": 2.5, "tilt": -8},
    "medium":         {"focal_length": 50,  "distance": 4.0,  "height": 1.8, "tilt": -3},
    "close_up":       {"focal_length": 85,  "distance": 1.5,  "height": 1.6, "tilt": 0},
    "extreme_close_up": {"focal_length": 135, "distance": 0.8,  "height": 1.5, "tilt": 0},
    "insert":         {"focal_length": 100, "distance": 1.0,  "height": 1.2, "tilt": -15},
    "over_shoulder":  {"focal_length": 50,  "distance": 3.5,  "height": 1.7, "tilt": -2, "offset_x": 1.2},
    "aerial":         {"focal_length": 24,  "distance": 15.0, "height": 10.0, "tilt": -60},
    "static":         {"focal_length": 50,  "distance": 5.0,  "height": 1.8, "tilt": -3},
    "tracking":       {"focal_length": 50,  "distance": 5.0,  "height": 1.8, "tilt": -3},
    "pan":            {"focal_length": 50,  "distance": 5.0,  "height": 1.8, "tilt": -3},
    "tilt":           {"focal_length": 50,  "distance": 5.0,  "height": 1.8, "tilt": -3},
    "dolly":          {"focal_length": 50,  "distance": 5.0,  "height": 1.8, "tilt": -3},
}

DEFAULT_CAMERA = {"focal_length": 50, "distance": 5.0, "height": 1.8, "tilt": -3}

# ── Scene Heading Parser ────────────────────────────────────────────────────

def parse_scene_heading(heading: str) -> dict:
    """Parse 'INT. CLASSROOM - DAY' into lighting context."""
    heading = heading.strip().upper()
    result = {"interior": heading.startswith("INT."), "exterior": heading.startswith("EXT."), "time": "day"}
    if "NIGHT" in heading or "EVENING" in heading or "DUSK" in heading:
        result["time"] = "night"
    elif "DAWN" in heading or "MORNING" in heading or "SUNRISE" in heading:
        result["time"] = "morning"
    return result


# ── Layout Inspector (runs inside Blender) ──────────────────────────────────

def _inspect_layout(project_slug: str) -> dict:
    import bpy
    import math
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    blend_path = project_dir / "03-layout" / "layout.blend"

    if not blend_path.exists():
        return {"status": "error", "message": f"Layout not found: {blend_path}"}

    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    scene = bpy.context.scene

    cameras = []
    for obj in scene.objects:
        if obj.type == "CAMERA":
            cameras.append({
                "name": obj.name,
                "lens_mm": obj.data.lens,
                "location": [round(v, 3) for v in obj.location],
                "rotation_euler": [round(math.degrees(v), 2) for v in obj.rotation_euler],
                "background_images": len(obj.data.background_images),
                "shot_id": obj.get("shot_id", ""),
                "shot_type": obj.get("shot_type", ""),
                "camera_movement": obj.get("camera_movement", ""),
                "frame_start": obj.get("layout_frame_start", 0),
                "frame_end": obj.get("layout_frame_end", 0),
            })

    markers = []
    for m in scene.timeline_markers:
        markers.append({
            "name": m.name,
            "frame": m.frame,
            "camera": m.camera.name if m.camera else None,
        })

    lights = []
    for obj in scene.objects:
        if obj.type == "LIGHT":
            lights.append({
                "name": obj.name,
                "type": obj.data.type,
                "energy": round(obj.data.energy, 1),
                "color": [round(v, 2) for v in obj.data.color],
            })

    return {
        "status": "ok",
        "project": project_slug,
        "blend_path": str(blend_path),
        "engine": scene.render.engine,
        "frame_range": [scene.frame_start, scene.frame_end],
        "camera_count": len(cameras),
        "cameras": cameras,
        "markers": markers,
        "light_count": len(lights),
        "lights": lights,
    }


# ── Layout Builder (runs inside Blender) ────────────────────────────────────

class BlenderLayoutBuilder:
    def __init__(self, project_slug: str, engine: str = "eevee", animate: bool = False):
        self.project_slug = project_slug
        self.engine = engine
        self.animate = animate
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_dir = self.project_dir / "03-layout"
        self.layout_dir.mkdir(parents=True, exist_ok=True)

        self.shot_list = self._load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.manifest = self._load_json(self.project_dir / "02-storyboards" / "storyboard_manifest.json")

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def build(self) -> dict:
        import bpy
        import math

        # Start with factory settings
        bpy.ops.wm.read_factory_settings(use_empty=True)

        scene = bpy.context.scene
        scene.name = f"{self.project_slug}_layout"

        # Set render engine
        if self.engine == "cycles":
            scene.render.engine = "CYCLES"
            scene.cycles.device = "GPU"
            scene.cycles.samples = 128
        else:
            scene.render.engine = "BLENDER_EEVEE"

        # Remove default cube
        if "Cube" in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects["Cube"], do_unlink=True)

        # Create shared floor
        self._create_floor()

        # Group shots by scene for lighting
        scenes_data = self.shot_list.get("scenes", [])
        shots = self.shot_list.get("shots", [])
        frame_lookup = {f["shot_id"]: f for f in self.manifest.get("frames", [])}

        current_frame = 1
        fps = scene.render.fps

        for shot in shots:
            shot_id = shot["shot_id"]
            frame_data = frame_lookup.get(shot_id, {})
            img_path = frame_data.get("output_path")

            # Parse scene context for lighting
            heading = shot.get("scene_heading", "")
            scene_context = parse_scene_heading(heading)

            # Calculate duration early (needed for animation)
            duration = shot.get("duration_seconds", 3.0)
            if duration <= 0:
                duration = 3.0
            frame_end = current_frame + int(duration * fps) - 1

            # Create camera
            cam_obj = self._create_shot_camera(shot, img_path)

            # Position camera
            self._position_camera(cam_obj, shot)

            # Animate camera if requested
            if self.animate:
                self._animate_camera(cam_obj, shot, current_frame, frame_end)

            # Add lighting (per scene heading, only once per unique heading)
            light_key = f"lights_{heading.replace(' ', '_').replace('.', '')}"
            if light_key not in bpy.data.collections:
                self._create_lighting(scene_context, light_key)

            # Timeline marker
            marker = scene.timeline_markers.new(name=shot_id, frame=current_frame)
            marker.camera = cam_obj

            # Store metadata on camera
            cam_obj["shot_id"] = shot_id
            cam_obj["scene_heading"] = heading
            cam_obj["shot_type"] = shot.get("shot_type", "medium")
            cam_obj["camera_movement"] = shot.get("camera_movement", "static")
            cam_obj["action"] = shot.get("action", "")
            cam_obj["dialogue"] = shot.get("dialogue", "")
            cam_obj["duration_seconds"] = shot.get("duration_seconds", 0.0)
            cam_obj["notes"] = shot.get("notes", "")
            cam_obj["layout_frame_start"] = current_frame
            cam_obj["layout_frame_end"] = frame_end

            # Advance frame
            current_frame += int(duration * fps)

        # Set scene end frame
        scene.frame_end = current_frame + fps

        # Set active camera to first shot
        if shots:
            first_shot_id = shots[0]["shot_id"]
            first_cam = bpy.data.objects.get(f"CAM_{first_shot_id}")
            if first_cam:
                scene.camera = first_cam

        # Save file
        blend_path = self.layout_dir / "layout.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

        return {
            "status": "ok",
            "project": self.project_slug,
            "blend_path": str(blend_path),
            "engine": self.engine,
            "total_shots": len(shots),
            "total_frames": current_frame,
        }

    def _create_floor(self):
        import bpy
        import math
        bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
        floor = bpy.context.active_object
        floor.name = "Floor"
        floor.data.name = "Floor_Mesh"
        # Add material
        mat = bpy.data.materials.new(name="Floor_Mat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.15, 0.15, 0.17, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.9
        floor.data.materials.append(mat)

    def _create_shot_camera(self, shot: dict, img_path: str | None):
        import bpy
        shot_id = shot["shot_id"]
        cam_data = bpy.data.cameras.new(name=f"CAM_{shot_id}")
        cam_obj = bpy.data.objects.new(name=f"CAM_{shot_id}", object_data=cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)

        # Apply shot type preset
        shot_type = shot.get("shot_type", "medium")
        preset = SHOT_CAMERA_PRESETS.get(shot_type, DEFAULT_CAMERA)
        cam_data.lens = preset.get("focal_length", 50)

        # Background image reference
        if img_path and Path(img_path).exists():
            cam_data.show_background_images = True
            bg = cam_data.background_images.new()
            try:
                img = bpy.data.images.load(str(img_path), check_existing=True)
                bg.image = img
                bg.display_depth = "FRONT"
                bg.alpha = 0.6
            except Exception as e:
                print(f"  ⚠️ Could not load background image {img_path}: {e}")

        return cam_obj

    def _position_camera(self, cam_obj, shot: dict):
        import bpy
        import math
        shot_type = shot.get("shot_type", "medium")
        preset = SHOT_CAMERA_PRESETS.get(shot_type, DEFAULT_CAMERA)

        distance = preset.get("distance", 5.0)
        height = preset.get("height", 1.8)
        tilt = math.radians(preset.get("tilt", -3))
        offset_x = preset.get("offset_x", 0.0)

        # Default: camera looks at origin from +Y
        cam_obj.location = (offset_x, -distance, height)
        cam_obj.rotation_euler = (math.radians(90) + tilt, 0, 0)

        # For aerial, adjust
        if shot_type == "aerial":
            cam_obj.location = (0, 0, distance)
            cam_obj.rotation_euler = (0, 0, 0)

    def _iter_fcurves(self, action_or_obj):
        """Iterate all fcurves in a Blender 5.x layered action."""
        import bpy
        if hasattr(action_or_obj, 'animation_data') and action_or_obj.animation_data:
            action = action_or_obj.animation_data.action
        else:
            action = action_or_obj
        if not action:
            return
        if hasattr(action, 'layers'):
            # Layered action (Blender 5.x)
            for layer in action.layers:
                for strip in layer.strips:
                    for cb in strip.channelbags:
                        for fc in cb.fcurves:
                            yield fc
        elif hasattr(action, 'fcurves'):
            # Legacy action
            for fc in action.fcurves:
                yield fc

    def _set_ease(self, obj_or_action, data_path: str, array_index: int = None):
        """Set BEZIER EASE_IN_OUT on matching fcurves."""
        for fc in self._iter_fcurves(obj_or_action):
            if fc.data_path == data_path:
                if array_index is None or fc.array_index == array_index:
                    for kp in fc.keyframe_points:
                        kp.interpolation = 'BEZIER'
                        kp.easing = 'EASE_IN_OUT'

    def _animate_camera(self, cam_obj, shot: dict, frame_start: int, frame_end: int):
        import bpy
        import math
        import random

        movement = shot.get("camera_movement", "static")
        if movement == "static":
            # Baseline keyframe only
            cam_obj.keyframe_insert(data_path="location", frame=frame_start)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)
            return

        # Get current transform as baseline
        base_loc = cam_obj.location.copy()
        base_rot = cam_obj.rotation_euler.copy()
        base_lens = cam_obj.data.lens

        if movement == "pan":
            # Horizontal sweep: rotate Z ±15 degrees
            cam_obj.rotation_euler = (base_rot.x, base_rot.y, base_rot.z - math.radians(15))
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)
            cam_obj.rotation_euler = (base_rot.x, base_rot.y, base_rot.z + math.radians(15))
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_end)
            self._set_ease(cam_obj, "rotation_euler", 2)

        elif movement == "tilt":
            # Vertical sweep: rotate X
            cam_obj.rotation_euler = (base_rot.x + math.radians(10), base_rot.y, base_rot.z)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)
            cam_obj.rotation_euler = (base_rot.x - math.radians(20), base_rot.y, base_rot.z)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_end)
            self._set_ease(cam_obj, "rotation_euler", 0)

        elif movement == "dolly":
            # Move forward
            cam_obj.location = base_loc.copy()
            cam_obj.keyframe_insert(data_path="location", frame=frame_start)
            cam_obj.location.y = base_loc.y * 0.4
            cam_obj.keyframe_insert(data_path="location", frame=frame_end)
            self._set_ease(cam_obj, "location", 1)

        elif movement == "tracking":
            # Slight orbit around origin
            import mathutils
            cam_obj.location = base_loc.copy()
            cam_obj.keyframe_insert(data_path="location", frame=frame_start)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)
            # Orbit to the side
            cam_obj.location.x = base_loc.x + 2.0
            cam_obj.location.y = base_loc.y + 1.0
            # Look at origin
            direction = mathutils.Vector((0, 0, base_loc.z)) - cam_obj.location
            rot_quat = direction.to_track_quat('-Z', 'Y')
            cam_obj.rotation_euler = rot_quat.to_euler()
            cam_obj.keyframe_insert(data_path="location", frame=frame_end)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_end)
            self._set_ease(cam_obj, "location", 0)

        elif movement == "zoom":
            # Animate focal length
            cam_obj.data.lens = base_lens
            cam_obj.data.keyframe_insert(data_path="lens", frame=frame_start)
            cam_obj.data.lens = base_lens * 1.5
            cam_obj.data.keyframe_insert(data_path="lens", frame=frame_end)
            self._set_ease(cam_obj.data, "lens")

        elif movement == "handheld":
            # Add subtle noise keyframes throughout
            frames = range(frame_start, frame_end + 1, max(1, (frame_end - frame_start) // 8))
            for f in frames:
                noise_loc = (
                    base_loc.x + random.uniform(-0.03, 0.03),
                    base_loc.y + random.uniform(-0.03, 0.03),
                    base_loc.z + random.uniform(-0.02, 0.02),
                )
                noise_rot = (
                    base_rot.x + math.radians(random.uniform(-0.3, 0.3)),
                    base_rot.y + math.radians(random.uniform(-0.3, 0.3)),
                    base_rot.z + math.radians(random.uniform(-0.3, 0.3)),
                )
                cam_obj.location = noise_loc
                cam_obj.rotation_euler = noise_rot
                cam_obj.keyframe_insert(data_path="location", frame=f)
                cam_obj.keyframe_insert(data_path="rotation_euler", frame=f)

        elif movement == "crane":
            # Arc up and over
            import mathutils
            cam_obj.location = base_loc.copy()
            cam_obj.keyframe_insert(data_path="location", frame=frame_start)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)
            mid_frame = (frame_start + frame_end) // 2
            cam_obj.location = (base_loc.x, base_loc.y + 2.0, base_loc.z + 4.0)
            direction = mathutils.Vector((0, 0, base_loc.z)) - cam_obj.location
            rot_quat = direction.to_track_quat('-Z', 'Y')
            cam_obj.rotation_euler = rot_quat.to_euler()
            cam_obj.keyframe_insert(data_path="location", frame=mid_frame)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=mid_frame)
            cam_obj.location = (base_loc.x + 3.0, base_loc.y + 4.0, base_loc.z)
            direction = mathutils.Vector((0, 0, base_loc.z)) - cam_obj.location
            rot_quat = direction.to_track_quat('-Z', 'Y')
            cam_obj.rotation_euler = rot_quat.to_euler()
            cam_obj.keyframe_insert(data_path="location", frame=frame_end)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_end)
            self._set_ease(cam_obj, "location", 0)

        else:
            # Unknown movement: static fallback
            cam_obj.keyframe_insert(data_path="location", frame=frame_start)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)

    def _create_lighting(self, context: dict, collection_name: str):
        import bpy
        import math

        coll = bpy.data.collections.new(name=collection_name)
        bpy.context.scene.collection.children.link(coll)

        is_interior = context.get("interior", True)
        time_of_day = context.get("time", "day")

        if is_interior:
            if time_of_day == "day":
                # Key light (warm, window-side)
                self._add_light("AREA", "Key", (5, -3, 4), 150, (1.0, 0.95, 0.9), coll)
                # Fill light (cool, opposite)
                self._add_light("AREA", "Fill", (-4, -2, 3), 50, (0.85, 0.9, 1.0), coll)
                # Rim light (back)
                self._add_light("AREA", "Rim", (0, 4, 3), 80, (1.0, 1.0, 1.0), coll)
            else:
                # Night interior: warmer, dimmer
                self._add_light("POINT", "Key", (3, -2, 2.5), 80, (1.0, 0.85, 0.7), coll)
                self._add_light("POINT", "Fill", (-2, -1, 2), 25, (0.7, 0.75, 0.9), coll)
                self._add_light("AREA", "Rim", (0, 3, 2.5), 40, (0.9, 0.9, 1.0), coll)
        else:
            if time_of_day == "day":
                # Sun + sky
                self._add_light("SUN", "Sun", (5, 5, 8), 3.0, (1.0, 0.98, 0.95), coll)
                # Fill
                self._add_light("AREA", "Sky_Fill", (-5, 3, 6), 30, (0.85, 0.9, 1.0), coll)
            else:
                # Moonlight
                self._add_light("SUN", "Moon", (5, 5, 8), 0.5, (0.6, 0.7, 1.0), coll)
                self._add_light("POINT", "Street", (-3, -2, 2), 40, (1.0, 0.8, 0.6), coll)

    def _add_light(self, ltype: str, name: str, location: tuple, energy: float, color: tuple, collection):
        import bpy
        import math
        bpy.ops.object.light_add(type=ltype, location=location)
        light = bpy.context.active_object
        light.name = f"{name}_{collection.name}"
        light.data.energy = energy
        light.data.color = color
        # Move to collection
        bpy.context.scene.collection.objects.unlink(light)
        collection.objects.link(light)


# ── CLI / Entry Point ───────────────────────────────────────────────────────

def run_inside_blender():
    """Parse args passed after '--' when invoked via blender --python."""
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Blender Layout Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    p_layout = sub.add_parser("layout", help="Build layout scene from storyboards")
    p_layout.add_argument("project_slug", help="Project identifier")
    p_layout.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    p_layout.add_argument("--animate", action="store_true", help="Add camera movement keyframes")

    p_info = sub.add_parser("info", help="Inspect existing layout file")
    p_info.add_argument("project_slug", help="Project identifier")

    args = parser.parse_args(argv)

    if args.command == "layout":
        builder = BlenderLayoutBuilder(args.project_slug, engine=args.engine, animate=args.animate)
        result = builder.build()
        print(json.dumps(result, indent=2))

    elif args.command == "info":
        result = _inspect_layout(args.project_slug)
        print(json.dumps(result, indent=2))


def run_outside_blender():
    """Invoke Blender in background mode to run the layout builder."""
    parser = argparse.ArgumentParser(description="Blender Layout Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    p_layout = sub.add_parser("layout", help="Build layout scene from storyboards")
    p_layout.add_argument("project_slug", help="Project identifier")
    p_layout.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    p_layout.add_argument("--animate", action="store_true", help="Add camera movement keyframes")

    p_info = sub.add_parser("info", help="Inspect existing layout file")
    p_info.add_argument("project_slug", help="Project identifier")

    args = parser.parse_args()

    script_path = Path(__file__).resolve()

    if args.command == "layout":
        cmd = [
            BLENDER_BINARY,
            "--background",
            "--python", str(script_path),
            "--",
            "layout", args.project_slug,
            "--engine", args.engine,
        ]
        if args.animate:
            cmd.append("--animate")
        print(f"🎬 Building Blender layout for {args.project_slug}...")
        print(f"   Engine: {args.engine}")
        if args.animate:
            print("   Camera animation: enabled")
        subprocess.run(cmd, check=True)

    elif args.command == "info":
        cmd = [
            BLENDER_BINARY,
            "--background",
            "--python", str(script_path),
            "--",
            "info", args.project_slug,
        ]
        print(f"🔍 Inspecting layout for {args.project_slug}...")
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
