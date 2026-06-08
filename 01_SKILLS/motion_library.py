#!/usr/bin/env python3
"""
motion_library.py — Reusable Animation Clips & Pose Library

Creates, stores, and blends reusable animation clips (walk cycles,
run cycles, idle poses, gestures) for rapid character animation.

Usage:
    python motion_library.py init
    python motion_library.py save-pose <name> --project <slug> --armature BodyMocap
    python motion_library.py save-clip <name> --project <slug> --start 1 --end 24
    python motion_library.py apply <name> --project <slug> --frame 100
    python motion_library.py blend <clip1> <clip2> --project <slug> --frame 100 --weight 0.5

Library structure:
    06_SHARED_ASSETS/motion-library/
    ├── poses/          # Single-frame pose presets
    ├── clips/          # Multi-frame animation clips
    └── manifest.json
"""

import argparse
import json
import shutil
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
LIBRARY = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "motion-library"


def init_library() -> dict:
    (LIBRARY / "poses").mkdir(parents=True, exist_ok=True)
    (LIBRARY / "clips").mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "poses": {},
        "clips": {},
        "note": "Poses are single-frame keyframe data. Clips are multi-frame animations.",
    }
    (LIBRARY / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "ok", "library_dir": str(LIBRARY)}


def save_pose(name: str, project_slug: str, armature_name: str = "BodyMocap") -> dict:
    import bpy
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    
    if not layout_path.exists():
        return {"status": "error", "message": "Layout not found"}
    
    bpy.ops.wm.open_mainfile(filepath=str(layout_path))
    
    arm_obj = None
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE" and obj.name == armature_name:
            arm_obj = obj
            break
    
    if not arm_obj:
        return {"status": "error", "message": f"Armature {armature_name} not found"}
    
    pose_data = {}
    for bone in arm_obj.pose.bones:
        pose_data[bone.name] = {
            "location": list(bone.location),
            "rotation_euler": list(bone.rotation_euler),
            "scale": list(bone.scale),
        }
    
    pose_path = LIBRARY / "poses" / f"{name}.json"
    pose_path.write_text(json.dumps(pose_data, indent=2), encoding="utf-8")
    
    # Update manifest
    manifest = json.loads((LIBRARY / "manifest.json").read_text(encoding="utf-8"))
    manifest["poses"][name] = {"file": str(pose_path), "bones": list(pose_data.keys())}
    (LIBRARY / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    return {"status": "ok", "pose": name, "bones": len(pose_data)}


def save_clip(name: str, project_slug: str, start_frame: int, end_frame: int,
              armature_name: str = "BodyMocap") -> dict:
    import bpy
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    
    if not layout_path.exists():
        return {"status": "error", "message": "Layout not found"}
    
    bpy.ops.wm.open_mainfile(filepath=str(layout_path))
    
    arm_obj = None
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE" and obj.name == armature_name:
            arm_obj = obj
            break
    
    if not arm_obj:
        return {"status": "error", "message": f"Armature {armature_name} not found"}
    
    clip_data = {"frames": [], "bones": [b.name for b in arm_obj.pose.bones]}
    
    for frame in range(start_frame, end_frame + 1):
        bpy.context.scene.frame_set(frame)
        frame_data = {"frame": frame, "bones": {}}
        for bone in arm_obj.pose.bones:
            frame_data["bones"][bone.name] = {
                "location": list(bone.location),
                "rotation_euler": list(bone.rotation_euler),
                "scale": list(bone.scale),
            }
        clip_data["frames"].append(frame_data)
    
    clip_path = LIBRARY / "clips" / f"{name}.json"
    clip_path.write_text(json.dumps(clip_data, indent=2), encoding="utf-8")
    
    manifest = json.loads((LIBRARY / "manifest.json").read_text(encoding="utf-8"))
    manifest["clips"][name] = {
        "file": str(clip_path),
        "frames": len(clip_data["frames"]),
        "start": start_frame,
        "end": end_frame,
    }
    (LIBRARY / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    return {"status": "ok", "clip": name, "frames": len(clip_data["frames"])}


def apply_pose(name: str, project_slug: str, frame: int, armature_name: str = "BodyMocap") -> dict:
    import bpy
    pose_path = LIBRARY / "poses" / f"{name}.json"
    if not pose_path.exists():
        return {"status": "error", "message": f"Pose {name} not found"}
    
    pose_data = json.loads(pose_path.read_text(encoding="utf-8"))
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    bpy.ops.wm.open_mainfile(filepath=str(layout_path))
    
    arm_obj = None
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE" and obj.name == armature_name:
            arm_obj = obj
            break
    
    if not arm_obj:
        return {"status": "error", "message": f"Armature not found"}
    
    bpy.context.scene.frame_set(frame)
    
    for bone_name, data in pose_data.items():
        if bone_name in arm_obj.pose.bones:
            bone = arm_obj.pose.bones[bone_name]
            bone.location = data["location"]
            bone.rotation_euler = data["rotation_euler"]
            bone.scale = data["scale"]
            bone.keyframe_insert(data_path="location", frame=frame)
            bone.keyframe_insert(data_path="rotation_euler", frame=frame)
            bone.keyframe_insert(data_path="scale", frame=frame)
    
    bpy.ops.wm.save_as_mainfile(filepath=str(layout_path))
    return {"status": "ok", "pose": name, "frame": frame, "bones": len(pose_data)}


def apply_clip(name: str, project_slug: str, start_frame: int, armature_name: str = "BodyMocap") -> dict:
    import bpy
    clip_path = LIBRARY / "clips" / f"{name}.json"
    if not clip_path.exists():
        return {"status": "error", "message": f"Clip {name} not found"}
    
    clip_data = json.loads(clip_path.read_text(encoding="utf-8"))
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    bpy.ops.wm.open_mainfile(filepath=str(layout_path))
    
    arm_obj = None
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE" and obj.name == armature_name:
            arm_obj = obj
            break
    
    if not arm_obj:
        return {"status": "error", "message": f"Armature not found"}
    
    for frame_data in clip_data["frames"]:
        frame = start_frame + (frame_data["frame"] - clip_data["frames"][0]["frame"])
        bpy.context.scene.frame_set(frame)
        
        for bone_name, data in frame_data["bones"].items():
            if bone_name in arm_obj.pose.bones:
                bone = arm_obj.pose.bones[bone_name]
                bone.location = data["location"]
                bone.rotation_euler = data["rotation_euler"]
                bone.scale = data["scale"]
                bone.keyframe_insert(data_path="location", frame=frame)
                bone.keyframe_insert(data_path="rotation_euler", frame=frame)
                bone.keyframe_insert(data_path="scale", frame=frame)
    
    bpy.ops.wm.save_as_mainfile(filepath=str(layout_path))
    return {"status": "ok", "clip": name, "start_frame": start_frame, "frames": len(clip_data["frames"])}


def list_library() -> dict:
    manifest_path = LIBRARY / "manifest.json"
    if not manifest_path.exists():
        return {"status": "error", "message": "Library not initialized"}
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "status": "ok",
        "poses": list(manifest.get("poses", {}).keys()),
        "clips": list(manifest.get("clips", {}).keys()),
    }


def main():
    parser = argparse.ArgumentParser(description="Motion Library")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize library")
    sub.add_parser("list", help="List poses and clips")

    p_save_pose = sub.add_parser("save-pose", help="Save current pose")
    p_save_pose.add_argument("name")
    p_save_pose.add_argument("--project", required=True)
    p_save_pose.add_argument("--armature", default="BodyMocap")

    p_save_clip = sub.add_parser("save-clip", help="Save animation clip")
    p_save_clip.add_argument("name")
    p_save_clip.add_argument("--project", required=True)
    p_save_clip.add_argument("--start", type=int, required=True)
    p_save_clip.add_argument("--end", type=int, required=True)
    p_save_clip.add_argument("--armature", default="BodyMocap")

    p_apply = sub.add_parser("apply", help="Apply pose/clip")
    p_apply.add_argument("name")
    p_apply.add_argument("--project", required=True)
    p_apply.add_argument("--frame", type=int, default=1)
    p_apply.add_argument("--armature", default="BodyMocap")

    args = parser.parse_args()

    if args.command == "init":
        print(json.dumps(init_library(), indent=2))
    elif args.command == "list":
        print(json.dumps(list_library(), indent=2))
    elif args.command == "save-pose":
        print(json.dumps(save_pose(args.name, args.project, args.armature), indent=2))
    elif args.command == "save-clip":
        print(json.dumps(save_clip(args.name, args.project, args.start, args.end, args.armature), indent=2))
    elif args.command == "apply":
        pose_path = LIBRARY / "poses" / f"{args.name}.json"
        clip_path = LIBRARY / "clips" / f"{args.name}.json"
        if pose_path.exists():
            print(json.dumps(apply_pose(args.name, args.project, args.frame, args.armature), indent=2))
        elif clip_path.exists():
            print(json.dumps(apply_clip(args.name, args.project, args.frame, args.armature), indent=2))
        else:
            print(json.dumps({"status": "error", "message": f"{args.name} not found"}))


if __name__ == "__main__":
    main()
