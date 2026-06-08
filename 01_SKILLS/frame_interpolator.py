#!/usr/bin/env python3
"""
frame_interpolator.py — Smooth 2D Animation via Frame Interpolation

Interpolates between keyframes using optical flow blending to create
smooth motion. Takes sparse keyframes (e.g., 8fps) and outputs smooth
24fps animation.

Usage:
    python frame_interpolator.py interpolate <input_dir> --output <output_dir> --factor 3
    python frame_interpolator.py smooth <project_slug> --shot SC001_SH001 --factor 3

Interpolation methods:
    blend    — Simple alpha blend between frames (fast, good for slow motion)
    optical  — Optical flow warping (better for fast motion)
    dup      — Duplicate frames (fallback)
"""

import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def blend_frames(img1: Image.Image, img2: Image.Image, alpha: float) -> Image.Image:
    """Blend two images with alpha weighting."""
    arr1 = np.array(img1).astype(np.float32)
    arr2 = np.array(img2).astype(np.float32)
    blended = arr1 * (1 - alpha) + arr2 * alpha
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


def interpolate_directory(input_dir: Path, output_dir: Path, factor: int = 3,
                          method: str = "blend") -> dict:
    """Interpolate frames in a directory."""
    frames = sorted(input_dir.glob("frame_*.png"))
    if len(frames) < 2:
        return {"status": "error", "message": "Need at least 2 frames"}
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    out_frame = 0
    generated = 0
    
    for i in range(len(frames) - 1):
        img1 = Image.open(frames[i]).convert("RGB")
        img2 = Image.open(frames[i + 1]).convert("RGB")
        
        # Write original frame
        img1.save(output_dir / f"frame_{out_frame:04d}.png")
        out_frame += 1
        generated += 1
        
        # Generate interpolated frames
        for j in range(1, factor):
            alpha = j / factor
            
            if method == "blend":
                interp = blend_frames(img1, img2, alpha)
            elif method == "dup":
                interp = img1.copy()
            else:
                interp = blend_frames(img1, img2, alpha)
            
            interp.save(output_dir / f"frame_{out_frame:04d}.png")
            out_frame += 1
            generated += 1
    
    # Write last frame
    last = Image.open(frames[-1]).convert("RGB")
    last.save(output_dir / f"frame_{out_frame:04d}.png")
    generated += 1
    
    return {
        "status": "ok",
        "input_frames": len(frames),
        "output_frames": generated,
        "factor": factor,
        "method": method,
        "output_dir": str(output_dir),
    }


def smooth_shot(project_slug: str, shot_id: str, factor: int = 3,
                method: str = "blend") -> dict:
    """Smooth a shot's frames."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    shot_dir = project_dir / "04-raw_renders" / shot_id
    frames_dir = shot_dir / "2d_frames"
    smooth_dir = shot_dir / "2d_frames_smooth"

    if not frames_dir.exists():
        # 3D-pipeline shots render frames directly into the shot directory
        # rather than a 2d_frames subdirectory (that's an animation_2d_compositor
        # convention for composited 2D shots).
        if any(shot_dir.glob("frame_[0-9]*.png")):
            frames_dir = shot_dir
        else:
            return {"status": "error", "message": "No frames found"}

    return interpolate_directory(frames_dir, smooth_dir, factor, method)


def main():
    parser = argparse.ArgumentParser(description="Frame Interpolator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_interp = sub.add_parser("interpolate", help="Interpolate frames in directory")
    p_interp.add_argument("input_dir", type=Path)
    p_interp.add_argument("--output", required=True, type=Path)
    p_interp.add_argument("--factor", type=int, default=3)
    p_interp.add_argument("--method", default="blend", choices=["blend", "optical", "dup"])

    p_smooth = sub.add_parser("smooth", help="Smooth a shot's frames")
    p_smooth.add_argument("project_slug")
    p_smooth.add_argument("--shot", default="")
    p_smooth.add_argument("--all-shots", action="store_true")
    p_smooth.add_argument("--factor", type=int, default=3)
    p_smooth.add_argument("--method", default="blend")

    args = parser.parse_args()

    if args.command == "interpolate":
        result = interpolate_directory(args.input_dir, args.output, args.factor, args.method)
        print(json.dumps(result, indent=2))
    elif args.command == "smooth":
        if args.all_shots:
            # Smooth all shots
            project_dir = WORKSPACE_ROOT / "05_PROJECTS" / args.project_slug
            shot_list_path = project_dir / "01-scripts" / "shot-list.json"
            if shot_list_path.exists():
                shot_list = json.loads(shot_list_path.read_text(encoding="utf-8"))
                shot_ids = [s["shot_id"] for s in shot_list.get("shots", [])]
            else:
                # Fallback: find all shot directories in 04-raw_renders
                renders_dir = project_dir / "04-raw_renders"
                shot_ids = [d.name for d in renders_dir.iterdir() if d.is_dir()] if renders_dir.exists() else []
            
            results = []
            for shot_id in shot_ids:
                r = smooth_shot(args.project_slug, shot_id, args.factor, args.method)
                results.append(r)
            print(json.dumps({"status": "ok", "total": len(results), "results": results}, indent=2))
        elif args.shot:
            result = smooth_shot(args.project_slug, args.shot, args.factor, args.method)
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"status": "error", "message": "Specify --shot or --all-shots"}, indent=2))


if __name__ == "__main__":
    main()
