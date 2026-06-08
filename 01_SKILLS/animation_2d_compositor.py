#!/usr/bin/env python3
"""
animation_2d_compositor.py — 2D Animation Frame Compositor

Composites 2D animation frames from layers:
- Background (per scene)
- Character (posed, scaled, positioned)
- Mouth (lip-sync overlay)
- Effects (text, particles, motion blur)

Outputs frame sequences ready for ffmpeg encoding.

Usage:
    python animation_2d_compositor.py composite <project_slug> --shot SC001_SH001
    python animation_2d_compositor.py composite <project_slug> --all-shots
    python animation_2d_compositor.py render <project_slug> --episode EP01

Layer order (bottom to top):
    1. Background
    2. Character body
    3. Character mouth
    4. Effects overlay
"""

import argparse
import json
import math
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
FPS = 24

# Mouth shape library (simple shapes for 2D)
MOUTH_SHAPES = {
    "silence": lambda draw, box: None,
    "A": lambda draw, box: draw.ellipse([box[0]+5, box[1]+10, box[2]-5, box[3]-5], fill=(60, 30, 30)),
    "I": lambda draw, box: draw.line([box[0]+8, box[1]+15, box[2]-8, box[1]+15], fill=(60, 30, 30), width=3),
    "U": lambda draw, box: draw.ellipse([box[0]+8, box[1]+12, box[2]-8, box[3]-8], fill=(60, 30, 30)),
    "E": lambda draw, box: draw.arc([box[0]+5, box[1]+8, box[2]-5, box[3]-8], 0, 180, fill=(60, 30, 30), width=3),
    "O": lambda draw, box: draw.ellipse([box[0]+6, box[1]+8, box[2]-6, box[3]-8], fill=(60, 30, 30)),
}


def load_shot_data(project_slug: str, shot_id: str) -> dict:
    """Load all data needed for a shot."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    
    shot_list = json.loads((project_dir / "01-scripts" / "shot-list.json").read_text(encoding="utf-8"))
    shot = next((s for s in shot_list.get("shots", []) if s["shot_id"] == shot_id), None)
    
    if not shot:
        return None
    
    scene_id = shot.get("scene_id", "")
    scene = next((s for s in shot_list.get("scenes", []) if s["scene_id"] == scene_id), None)
    
    return {
        "shot": shot,
        "scene": scene,
        "project_dir": project_dir,
    }


def get_background(project_dir: Path, scene_id: str) -> Image.Image:
    """Load or generate background for scene."""
    bg_path = project_dir / "05-assets" / "backgrounds_2d" / f"{scene_id}_bg.png"
    if bg_path.exists():
        return Image.open(bg_path).convert("RGBA")
    
    # Generate procedural background
    heading = ""
    shot_list = json.loads((project_dir / "01-scripts" / "shot-list.json").read_text(encoding="utf-8"))
    scene = next((s for s in shot_list.get("scenes", []) if s["scene_id"] == scene_id), None)
    if scene:
        heading = scene.get("heading", "").lower()
    
    img = Image.new("RGBA", (1920, 1080))
    pixels = img.load()
    
    if "night" in heading or "dark" in heading:
        base, accent = (20, 25, 40), (60, 40, 80)
    elif "classroom" in heading or "office" in heading:
        base, accent = (200, 190, 170), (180, 170, 150)
    elif "park" in heading or "forest" in heading:
        base, accent = (100, 140, 80), (60, 100, 50)
    elif "home" in heading:
        base, accent = (230, 210, 180), (200, 180, 150)
    else:
        base, accent = (180, 190, 200), (150, 160, 170)
    
    for y in range(1080):
        t = y / 1080
        r = int(base[0] * (1 - t) + accent[0] * t)
        g = int(base[1] * (1 - t) + accent[1] * t)
        b = int(base[2] * (1 - t) + accent[2] * t)
        for x in range(1920):
            noise = random.randint(-5, 5)
            pixels[x, y] = (max(0, min(255, r + noise)),
                            max(0, min(255, g + noise)),
                            max(0, min(255, b + noise)), 255)
    
    return img


def get_character(project_dir: Path, character_name: str, pose: str = "standing") -> Image.Image:
    """Load character image."""
    char_dir = project_dir / "05-assets" / "characters_2d" / character_name
    
    # Try posed image first
    pose_path = char_dir / f"{pose}.png"
    if pose_path.exists():
        return Image.open(pose_path).convert("RGBA")
    
    # Try base image
    base_path = char_dir / "base.png"
    if base_path.exists():
        return Image.open(base_path).convert("RGBA")
    
    # Create stickman placeholder
    img = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Stickman body
    color = (50, 50, 50, 255)
    width = 4
    
    # Head
    draw.ellipse([150, 20, 250, 120], outline=color, width=width)
    # Body
    draw.line([200, 120, 200, 300], fill=color, width=width)
    # Arms
    draw.line([200, 150, 120, 250], fill=color, width=width)
    draw.line([200, 150, 280, 250], fill=color, width=width)
    # Legs
    draw.line([200, 300, 140, 500], fill=color, width=width)
    draw.line([200, 300, 260, 500], fill=color, width=width)
    
    return img


def composite_shot(project_slug: str, shot_id: str, duration_sec: float = 3.0,
                   width: int = 1920, height: int = 1080) -> dict:
    """Composite a single shot into frame sequence."""
    data = load_shot_data(project_slug, shot_id)
    if not data:
        return {"status": "error", "message": f"Shot {shot_id} not found"}
    
    shot = data["shot"]
    scene = data["scene"]
    project_dir = data["project_dir"]
    
    scene_id = shot.get("scene_id", "")
    shot_type = shot.get("shot_type", "medium")
    
    # Output directory
    frames_dir = project_dir / "04-raw_renders" / shot_id / "2d_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    
    # Load layers
    bg = get_background(project_dir, scene_id)
    bg = bg.resize((width, height), Image.Resampling.LANCZOS)
    
    # Character sizing based on shot type
    if shot_type == "close_up":
        char_scale = 2.5
        char_x = width // 2 - 200
        char_y = height // 2 - 300
    elif shot_type == "medium":
        char_scale = 1.5
        char_x = width // 2 - 150
        char_y = height - 450
    elif shot_type == "wide":
        char_scale = 0.8
        char_x = width // 2 - 100
        char_y = height - 350
    else:
        char_scale = 1.0
        char_x = width // 2 - 150
        char_y = height - 400
    
    # Get character (use first character or default)
    char_name = "protagonist"  # Could be derived from shot metadata
    char = get_character(project_dir, char_name)
    
    # Resize character
    char_w = int(char.width * char_scale)
    char_h = int(char.height * char_scale)
    char = char.resize((char_w, char_h), Image.Resampling.LANCZOS)
    
    # Generate frames
    total_frames = int(duration_sec * FPS)
    generated = []
    
    for frame in range(total_frames):
        # Start with background
        composite = bg.copy()
        
        # Simple animation: subtle breathing/sway
        sway_x = int(math.sin(frame * 0.1) * 3)
        sway_y = int(math.sin(frame * 0.15) * 2)
        
        # Paste character
        char_pos = (char_x + sway_x, char_y + sway_y)
        composite.paste(char, char_pos, char)
        
        # Add subtle mouth animation if dialogue
        if shot.get("dialogue"):
            # Simple mouth open/close cycle
            mouth_open = int((math.sin(frame * 0.3) + 1) * 5)
            draw = ImageDraw.Draw(composite)
            mouth_x = char_pos[0] + char_w // 2 - 10
            mouth_y = char_pos[1] + int(char_h * 0.22)
            draw.ellipse([mouth_x, mouth_y, mouth_x + 20, mouth_y + 5 + mouth_open],
                        fill=(60, 30, 30, 200))
        
        # Save frame
        frame_path = frames_dir / f"frame_{frame:04d}.png"
        composite.convert("RGB").save(frame_path)
        generated.append(str(frame_path))
    
    return {
        "status": "ok",
        "shot_id": shot_id,
        "frames": len(generated),
        "duration_sec": duration_sec,
        "fps": FPS,
        "output_dir": str(frames_dir),
    }


def encode_shot_video(project_slug: str, shot_id: str) -> dict:
    """Encode frame sequence to MP4."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    frames_dir = project_dir / "04-raw_renders" / shot_id / "2d_frames"
    output_dir = project_dir / "04-raw_renders" / shot_id
    output_path = output_dir / "2d_render.mp4"
    
    if not any(frames_dir.glob("*.png")):
        return {"status": "error", "message": "No frames to encode"}
    
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "medium", "-crf", "18",
        str(output_path),
    ], capture_output=True, check=True)
    
    return {
        "status": "ok",
        "shot_id": shot_id,
        "video": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser(description="2D Animation Compositor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_comp = sub.add_parser("composite", help="Composite frames for shot(s)")
    p_comp.add_argument("project_slug")
    p_comp.add_argument("--shot")
    p_comp.add_argument("--all-shots", action="store_true")
    p_comp.add_argument("--duration", type=float, default=3.0)

    p_enc = sub.add_parser("encode", help="Encode frames to video")
    p_enc.add_argument("project_slug")
    p_enc.add_argument("--shot")
    p_enc.add_argument("--all-shots", action="store_true")

    args = parser.parse_args()

    if args.command == "composite":
        project_dir = WORKSPACE_ROOT / "05_PROJECTS" / args.project_slug
        shot_list = json.loads((project_dir / "01-scripts" / "shot-list.json").read_text(encoding="utf-8"))
        
        if args.shot:
            result = composite_shot(args.project_slug, args.shot, args.duration)
            print(json.dumps(result, indent=2))
        elif args.all_shots:
            results = []
            for shot in shot_list.get("shots", []):
                result = composite_shot(args.project_slug, shot["shot_id"],
                                       shot.get("duration_seconds", args.duration))
                results.append(result)
            print(json.dumps({"status": "ok", "total": len(results), "results": results}, indent=2))
        else:
            print(json.dumps({"status": "error", "message": "Specify --shot or --all-shots"}))
    
    elif args.command == "encode":
        project_dir = WORKSPACE_ROOT / "05_PROJECTS" / args.project_slug
        shot_list = json.loads((project_dir / "01-scripts" / "shot-list.json").read_text(encoding="utf-8"))
        
        if args.shot:
            result = encode_shot_video(args.project_slug, args.shot)
            print(json.dumps(result, indent=2))
        elif args.all_shots:
            results = []
            for shot in shot_list.get("shots", []):
                result = encode_shot_video(args.project_slug, shot["shot_id"])
                results.append(result)
            print(json.dumps({"status": "ok", "total": len(results), "results": results}, indent=2))
        else:
            print(json.dumps({"status": "error", "message": "Specify --shot or --all-shots"}))


if __name__ == "__main__":
    main()
