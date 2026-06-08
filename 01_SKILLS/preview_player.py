#!/usr/bin/env python3
"""
preview_player.py — Quick Render Preview & Shot Browser

Opens rendered frames/videos in the default viewer or generates
an HTML preview page with all shots for review.

Usage:
    python preview_player.py preview <project_slug> --shot SC001_SH001
    python preview_player.py browser <project_slug>
    python preview_player.py video <project_slug> --shot SC001_SH001
"""

import argparse
import json
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def preview_shot(project_slug: str, shot_id: str) -> dict:
    """Open a shot's rendered frames in default image viewer."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    frames_dir = project_dir / "04-raw_renders" / shot_id / "2d_frames"
    
    if not frames_dir.exists():
        return {"status": "error", "message": "No rendered frames found"}
    
    frames = sorted(frames_dir.glob("*.png"))
    if not frames:
        return {"status": "error", "message": "No frames in directory"}
    
    # Open middle frame
    mid_frame = frames[len(frames) // 2]
    subprocess.run(["open", str(mid_frame)])
    
    return {
        "status": "ok",
        "shot_id": shot_id,
        "opened": str(mid_frame),
        "total_frames": len(frames),
    }


def preview_video(project_slug: str, shot_id: str = None) -> dict:
    """Open a rendered video in default player."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    
    if shot_id:
        video_path = project_dir / "04-raw_renders" / shot_id / "2d_render.mp4"
    else:
        # Find any video
        videos = list(project_dir.rglob("*.mp4"))
        video_path = videos[0] if videos else None
    
    if not video_path or not video_path.exists():
        return {"status": "error", "message": "No video found"}
    
    subprocess.run(["open", str(video_path)])
    
    return {
        "status": "ok",
        "video": str(video_path),
    }


def generate_browser(project_slug: str) -> dict:
    """Generate an HTML preview page of all rendered shots."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    renders_dir = project_dir / "04-raw_renders"
    
    if not renders_dir.exists():
        return {"status": "error", "message": "No renders directory"}
    
    shot_dirs = [d for d in sorted(renders_dir.iterdir()) if d.is_dir()]
    
    html_parts = [
        "<!DOCTYPE html><html><head>",
        "<meta charset='utf-8'><title>Preview</title>",
        "<style>body{font-family:sans-serif;background:#1a1a2e;color:#eee;padding:20px}",
        ".shot{display:inline-block;margin:10px;text-align:center}",
        ".shot img{width:320px;height:180px;object-fit:cover;border-radius:8px}",
        ".shot-name{color:#e94560;font-size:14px;margin-top:8px}</style></head><body>",
        f"<h1>{project_slug} — Rendered Shots</h1>",
    ]
    
    for shot_dir in shot_dirs:
        frames = sorted((shot_dir / "2d_frames").glob("*.png")) if (shot_dir / "2d_frames").exists() else []
        if frames:
            mid = frames[len(frames) // 2]
            rel_path = mid.relative_to(project_dir)
            html_parts.append(f'<div class="shot"><img src="{rel_path}"><div class="shot-name">{shot_dir.name}</div></div>')
    
    html_parts.append("</body></html>")
    
    html_path = project_dir / "preview.html"
    html_path.write_text("\n".join(html_parts), encoding="utf-8")
    
    subprocess.run(["open", str(html_path)])
    
    return {
        "status": "ok",
        "shots": len(shot_dirs),
        "html": str(html_path),
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    p_prev = sub.add_parser("preview")
    p_prev.add_argument("project_slug")
    p_prev.add_argument("--shot", required=True)
    
    p_vid = sub.add_parser("video")
    p_vid.add_argument("project_slug")
    p_vid.add_argument("--shot")
    
    p_browse = sub.add_parser("browser")
    p_browse.add_argument("project_slug")
    
    args = parser.parse_args()
    
    if args.cmd == "preview":
        print(json.dumps(preview_shot(args.project_slug, args.shot), indent=2))
    elif args.cmd == "video":
        print(json.dumps(preview_video(args.project_slug, args.shot), indent=2))
    elif args.cmd == "browser":
        print(json.dumps(generate_browser(args.project_slug), indent=2))

if __name__ == "__main__":
    main()
