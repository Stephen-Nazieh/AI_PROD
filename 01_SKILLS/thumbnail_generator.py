#!/usr/bin/env python3
"""
thumbnail_generator.py — Episode Thumbnail & Poster Generation

Generates eye-catching thumbnails for YouTube, TikTok, and social media
using rendered frames + text overlays.

Usage:
    python thumbnail_generator.py generate <project_slug> --episode EP01
    python thumbnail_generator.py generate <project_slug> --shot SC001_SH001 --text "Stats 101"
"""

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def generate_thumbnail(project_slug: str, episode_id: str = None, shot_id: str = None,
                       text: str = "", width: int = 1280, height: int = 720) -> dict:
    """Generate a thumbnail from a rendered frame."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    
    # Find source frame
    if shot_id:
        frame_dir = project_dir / "04-raw_renders" / shot_id / "2d_frames"
    elif episode_id:
        frame_dir = project_dir / "episodes" / episode_id / "04-raw_renders"
        if not frame_dir.exists():
            frame_dir = project_dir / "04-raw_renders"
    else:
        frame_dir = project_dir / "04-raw_renders"
    
    source = None
    if frame_dir.exists():
        frames = sorted(frame_dir.rglob("*.png"))
        if frames:
            source = frames[len(frames) // 2]  # Middle frame
    
    if not source:
        # Create gradient fallback
        img = Image.new("RGB", (width, height))
        pixels = img.load()
        for y in range(height):
            t = y / height
            r = int(30 + t * 100)
            g = int(40 + t * 80)
            b = int(80 + t * 60)
            for x in range(width):
                pixels[x, y] = (r, g, b)
    else:
        img = Image.open(source).convert("RGB")
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    
    # Add text overlay
    draw = ImageDraw.Draw(img)
    
    # Title text
    title = text or f"Episode 1"
    
    # Draw dark overlay at bottom
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([0, height - 120, width, height], fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    
    # Draw title
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
    except Exception:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), title, font=font)
    text_w = bbox[2] - bbox[0]
    text_x = (width - text_w) // 2
    text_y = height - 90
    
    draw.text((text_x + 2, text_y + 2), title, fill=(0, 0, 0), font=font)
    draw.text((text_x, text_y), title, fill=(255, 255, 255), font=font)
    
    # Save
    thumb_dir = project_dir / "09-deliver" / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    
    name = f"{episode_id or shot_id or 'default'}_thumbnail.png"
    thumb_path = thumb_dir / name
    img.save(thumb_path)
    
    return {
        "status": "ok",
        "project": project_slug,
        "thumbnail": str(thumb_path),
        "resolution": f"{width}x{height}",
        "source": str(source) if source else "generated",
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("generate")
    p.add_argument("project_slug")
    p.add_argument("--episode")
    p.add_argument("--shot")
    p.add_argument("--text", default="")
    args = parser.parse_args()
    
    if args.cmd == "generate":
        print(json.dumps(generate_thumbnail(args.project_slug, args.episode, args.shot, args.text), indent=2))

if __name__ == "__main__":
    main()
