#!/usr/bin/env python3
"""
mocap_to_2d.py — Convert Body Mocap to 2D Character Pose Instructions

Reads MediaPipe mocap JSON and generates per-frame character positioning
instructions for the 2D compositor: x, y, scale, rotation.

Usage:
    python mocap_to_2d.py convert <mocap.json> --output poses.json
    python mocap_to_2d.py apply <project_slug> --shot SC001_SH001 --poses poses.json

Maps 33 MediaPipe landmarks to 2D character transforms:
- Body center → character position
- Body width → character scale
- Shoulder angle → character rotation
"""

import argparse
import json
import math
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def mocap_to_2d_poses(mocap_data: dict, canvas_w: int = 1920, canvas_h: int = 1080) -> list:
    """Convert mocap frames to 2D character pose instructions."""
    poses = []
    
    for frame_data in mocap_data.get("frames", []):
        frame = frame_data["frame"]
        landmarks = frame_data.get("landmarks")
        
        if not landmarks:
            # No pose detected - use neutral
            poses.append({
                "frame": frame,
                "x": canvas_w // 2,
                "y": int(canvas_h * 0.7),
                "scale": 1.0,
                "rotation": 0.0,
                "detected": False,
            })
            continue
        
        # Get key landmarks
        nose = landmarks[0]
        left_shoulder = landmarks[11]
        right_shoulder = landmarks[12]
        left_hip = landmarks[23]
        right_hip = landmarks[24]
        
        # Body center (average of hips and shoulders)
        center_x = (left_shoulder["x"] + right_shoulder["x"] +
                   left_hip["x"] + right_hip["x"]) / 4
        center_y = (left_shoulder["y"] + right_shoulder["y"] +
                   left_hip["y"] + right_hip["y"]) / 4
        
        # Map normalized coordinates to canvas
        char_x = int(center_x * canvas_w)
        char_y = int(center_y * canvas_h)
        
        # Scale based on body height (shoulder to hip)
        body_height = math.sqrt(
            (left_shoulder["x"] - left_hip["x"])**2 +
            (left_shoulder["y"] - left_hip["y"])**2
        )
        char_scale = max(0.5, min(2.0, body_height * 3.0))
        
        # Rotation from shoulder line
        shoulder_dx = right_shoulder["x"] - left_shoulder["x"]
        shoulder_dy = right_shoulder["y"] - left_shoulder["y"]
        rotation = math.degrees(math.atan2(shoulder_dy, shoulder_dx))
        
        poses.append({
            "frame": frame,
            "x": char_x,
            "y": char_y,
            "scale": round(char_scale, 3),
            "rotation": round(rotation, 2),
            "detected": True,
        })
    
    return poses


def apply_2d_poses(project_slug: str, shot_id: str, poses: list) -> dict:
    """Save 2D pose instructions for the compositor."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    poses_dir = project_dir / "08-2d_poses"
    poses_dir.mkdir(parents=True, exist_ok=True)
    
    poses_path = poses_dir / f"{shot_id}_2d_poses.json"
    poses_path.write_text(json.dumps(poses, indent=2), encoding="utf-8")
    
    return {
        "status": "ok",
        "shot_id": shot_id,
        "poses": len(poses),
        "path": str(poses_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Mocap to 2D")
    sub = parser.add_subparsers(dest="command", required=True)

    p_conv = sub.add_parser("convert", help="Convert mocap to 2D poses")
    p_conv.add_argument("mocap_path", type=Path)
    p_conv.add_argument("--output", required=True, type=Path)
    p_conv.add_argument("--width", type=int, default=1920)
    p_conv.add_argument("--height", type=int, default=1080)

    p_apply = sub.add_parser("apply", help="Apply 2D poses to shot")
    p_apply.add_argument("project_slug")
    p_apply.add_argument("--shot", required=True)
    p_apply.add_argument("--poses", required=True, type=Path)

    args = parser.parse_args()

    if args.command == "convert":
        mocap_data = json.loads(args.mocap_path.read_text(encoding="utf-8"))
        poses = mocap_to_2d_poses(mocap_data, args.width, args.height)
        args.output.write_text(json.dumps(poses, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "poses": len(poses), "output": str(args.output)}, indent=2))
    elif args.command == "apply":
        poses = json.loads(args.poses.read_text(encoding="utf-8"))
        result = apply_2d_poses(args.project_slug, args.shot, poses)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
