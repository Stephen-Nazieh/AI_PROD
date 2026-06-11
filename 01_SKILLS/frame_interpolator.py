#!/usr/bin/env python3
"""
frame_interpolator.py — Smooth 2D Animation via Frame Interpolation

Interpolates between keyframes to create smooth motion. Takes sparse keyframes
(e.g. 8fps) and outputs smooth 24fps+ animation.

Usage:
    python frame_interpolator.py interpolate <input_dir> --output <output_dir> --factor 3
    python frame_interpolator.py smooth <project_slug> --shot SC001_SH001 --factor 3

Interpolation methods:
    minterpolate — ffmpeg motion-compensated interpolation (DEFAULT; true smooth
                   motion via bidirectional motion estimation — no ghosting)
    blend        — alpha crossfade between frames (fast, but ghosts on motion)
    dup          — duplicate frames (fallback, no new motion)

`minterpolate` synthesizes genuinely new in-between frames from estimated motion
vectors; `blend` just cross-dissolves, which double-images anything that moves.
"""

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
# Nominal input rate; only the in:out ratio (= factor) matters for frame count.
BASE_FPS = 24


def blend_frames(img1: Image.Image, img2: Image.Image, alpha: float) -> Image.Image:
    """Blend two images with alpha weighting."""
    arr1 = np.array(img1).astype(np.float32)
    arr2 = np.array(img2).astype(np.float32)
    blended = arr1 * (1 - alpha) + arr2 * alpha
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


def _minterpolate_directory(frames: list[Path], output_dir: Path, factor: int) -> dict:
    """Motion-compensated interpolation via ffmpeg minterpolate.

    Frames are staged as a zero-padded sequence (robust to arbitrary input
    numbering), interpolated from BASE_FPS to BASE_FPS*factor with bidirectional
    motion estimation + adaptive overlapped block motion compensation, then
    written back out as frame_%04d.png. Raises CalledProcessError on ffmpeg
    failure so the caller can fall back to blend.
    """
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td)
        for i, f in enumerate(frames):
            # symlink avoids copying potentially-large PNGs
            (stage / f"in_{i:06d}.png").symlink_to(f.resolve())
        vf = (f"minterpolate=fps={BASE_FPS * factor}:mi_mode=mci:"
              f"mc_mode=aobmc:me_mode=bidir:vsbmc=1")
        cmd = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(BASE_FPS), "-i", str(stage / "in_%06d.png"),
            "-vf", vf, "-start_number", "0", str(output_dir / "frame_%04d.png"),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    return {"generated": len(list(output_dir.glob("frame_*.png")))}


def _blend_directory(frames: list[Path], output_dir: Path, factor: int,
                     method: str) -> int:
    """Legacy PIL alpha-crossfade / duplicate interpolation. Returns frame count."""
    out_frame = generated = 0
    for i in range(len(frames) - 1):
        img1 = Image.open(frames[i]).convert("RGB")
        img2 = Image.open(frames[i + 1]).convert("RGB")
        img1.save(output_dir / f"frame_{out_frame:04d}.png")
        out_frame += 1; generated += 1
        for j in range(1, factor):
            alpha = j / factor
            interp = img1.copy() if method == "dup" else blend_frames(img1, img2, alpha)
            interp.save(output_dir / f"frame_{out_frame:04d}.png")
            out_frame += 1; generated += 1
    Image.open(frames[-1]).convert("RGB").save(output_dir / f"frame_{out_frame:04d}.png")
    return generated + 1


def interpolate_directory(input_dir: Path, output_dir: Path, factor: int = 3,
                          method: str = "minterpolate") -> dict:
    """Interpolate frames in a directory. Defaults to motion-compensated ffmpeg.

    `optical`/`mci` are aliases for `minterpolate`. If ffmpeg interpolation fails,
    transparently falls back to alpha-blend so the stage never hard-blocks a run.
    """
    frames = sorted(input_dir.glob("frame_*.png"))
    if len(frames) < 2:
        return {"status": "error", "message": "Need at least 2 frames"}

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("frame_*.png"):  # avoid mixing old/new counts
        stale.unlink()

    used = method
    if method in ("minterpolate", "optical", "mci"):
        try:
            r = _minterpolate_directory(frames, output_dir, factor)
            generated, used = r["generated"], "minterpolate"
        except (subprocess.CalledProcessError, OSError) as e:
            for stale in output_dir.glob("frame_*.png"):
                stale.unlink()
            generated = _blend_directory(frames, output_dir, factor, "blend")
            used = "blend (minterpolate failed: "\
                   f"{getattr(e, 'stderr', str(e))[:120].strip()})"
    else:
        generated = _blend_directory(frames, output_dir, factor, method)

    return {
        "status": "ok",
        "input_frames": len(frames),
        "output_frames": generated,
        "factor": factor,
        "method": used,
        "output_dir": str(output_dir),
    }


def smooth_shot(project_slug: str, shot_id: str, factor: int = 3,
                method: str = "minterpolate") -> dict:
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
    p_interp.add_argument("--method", default="minterpolate",
                          choices=["minterpolate", "optical", "mci", "blend", "dup"])

    p_smooth = sub.add_parser("smooth", help="Smooth a shot's frames")
    p_smooth.add_argument("project_slug")
    p_smooth.add_argument("--shot", default="")
    p_smooth.add_argument("--all-shots", action="store_true")
    p_smooth.add_argument("--factor", type=int, default=3)
    p_smooth.add_argument("--method", default="minterpolate",
                          choices=["minterpolate", "optical", "mci", "blend", "dup"])

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
