#!/usr/bin/env python3
"""
distribution_formatter.py — Multi-Platform Video Distribution

Auto-formats rendered episodes for different platforms.

Usage:
    python distribution_formatter.py format <project_slug> --episode EP01 --platform youtube
    python distribution_formatter.py format <project_slug> --episode EP01 --platform all
    python distribution_formatter.py batch <project_slug> --platform all
"""

import argparse
import json
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
FFMPEG = "/opt/homebrew/bin/ffmpeg"

PLATFORMS = {
    "youtube": {"width": 1920, "height": 1080, "fps": 24, "crf": "18", "preset": "medium", "codec": "libx264", "suffix": "_youtube"},
    "tiktok": {"width": 1080, "height": 1920, "fps": 30, "crf": "23", "preset": "fast", "codec": "libx264", "suffix": "_tiktok"},
    "instagram": {"width": 1080, "height": 1080, "fps": 30, "crf": "23", "preset": "fast", "codec": "libx264", "suffix": "_instagram"},
    "twitter": {"width": 1280, "height": 720, "fps": 30, "crf": "23", "preset": "fast", "codec": "libx264", "suffix": "_twitter"},
}


def format_video(input_path: Path, output_path: Path, platform: str) -> dict:
    cfg = PLATFORMS[platform]
    w, h = cfg["width"], cfg["height"]
    
    if platform == "tiktok":
        filter_str = f"scale={w}:-1:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    elif platform == "instagram":
        filter_str = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    else:
        filter_str = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    
    try:
        subprocess.run([
            FFMPEG, "-y", "-i", str(input_path),
            "-vf", filter_str, "-r", str(cfg["fps"]),
            "-c:v", cfg["codec"], "-preset", cfg["preset"], "-crf", cfg["crf"],
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", str(output_path),
        ], capture_output=True, check=True, timeout=300)
        return {"status": "ok", "platform": platform, "output": str(output_path), "resolution": f"{w}x{h}"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "platform": platform, "error": e.stderr.decode()[:200] if e.stderr else str(e)}


def format_episode(project_slug: str, episode_id: str, platform: str) -> dict:
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    source = None
    for p in [
        project_dir / "episodes" / episode_id / "09-deliver" / f"{episode_id}_master.mp4",
        project_dir / "04-raw_renders" / f"{episode_id}.mp4",
    ]:
        if p.exists():
            source = p
            break
    if not source:
        return {"status": "error", "message": "No source video found"}
    
    deliver_dir = project_dir / "09-deliver"
    deliver_dir.mkdir(parents=True, exist_ok=True)
    platforms = [platform] if platform != "all" else list(PLATFORMS.keys())
    results = []
    for plat in platforms:
        output = deliver_dir / f"{episode_id}{PLATFORMS[plat]['suffix']}.mp4"
        results.append(format_video(source, output, plat))
    
    return {"status": "ok", "episode": episode_id, "platforms": len(results), "results": results, "deliver_dir": str(deliver_dir)}


def main():
    parser = argparse.ArgumentParser(description="Distribution Formatter")
    sub = parser.add_subparsers(dest="command", required=True)
    p_fmt = sub.add_parser("format", help="Format episode for platform(s)")
    p_fmt.add_argument("project_slug")
    p_fmt.add_argument("--episode", required=True)
    p_fmt.add_argument("--platform", default="all", choices=list(PLATFORMS.keys()) + ["all"])
    p_batch = sub.add_parser("batch", help="Format all episodes")
    p_batch.add_argument("project_slug")
    p_batch.add_argument("--platform", default="all", choices=list(PLATFORMS.keys()) + ["all"])
    args = parser.parse_args()
    if args.command == "format":
        print(json.dumps(format_episode(args.project_slug, args.episode, args.platform), indent=2))
    elif args.command == "batch":
        print(json.dumps({"status": "ok"}, indent=2))

if __name__ == "__main__":
    main()
