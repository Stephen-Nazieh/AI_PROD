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


def _audio_envelope(wav_path: Path, total_frames: int, fps: int = FPS) -> list[float] | None:
    """Per-frame loudness (0..1) from a dialogue WAV, for audio-driven lip-sync.

    RMS of the audio window under each frame, gained so speech clearly opens the
    mouth and silence closes it. Returns None if the WAV is missing/unreadable so
    the caller falls back to a generic flap.
    """
    if not wav_path.exists():
        return None
    try:
        import wave
        with wave.open(str(wav_path), "rb") as w:
            sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
        a = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        if a.size == 0:
            return None
        a /= (np.abs(a).max() + 1e-9)
        env = []
        for f in range(total_frames):
            i0, i1 = int(f / fps * sr), int((f + 1) / fps * sr)
            seg = a[i0:i1] if i1 > i0 else a[i0:i0 + 1]
            rms = float(np.sqrt(np.mean(seg ** 2))) if seg.size else 0.0
            env.append(min(1.0, rms * 3.2))
        return env
    except Exception:
        return None


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

    # Audio-driven lip-sync envelope (per-frame loudness), if dialogue audio exists.
    env = _audio_envelope(project_dir / "06-audio" / "dialogue" / f"{shot_id}.wav",
                          total_frames) if shot.get("dialogue") else None

    # Ken Burns camera move on the background — the WHOLE frame drifts/zooms, and a
    # steady character in front of a moving background reads as parallax depth.
    ZOOM_A, ZOOM_B = 1.06, 1.13  # slow zoom-in across the shot
    denom = max(1, total_frames - 1)

    for frame in range(total_frames):
        p = frame / denom  # 0..1 progress

        # --- background camera move (zoom + eased diagonal pan, no black edges) ---
        z = ZOOM_A + (ZOOM_B - ZOOM_A) * p
        bw, bh = int(width * z), int(height * z)
        big = bg.resize((bw, bh), Image.Resampling.LANCZOS)
        cam_dx = int((bw - width) * (0.12 + 0.76 * p))
        cam_dy = int((bh - height) * (0.5 + 0.4 * math.sin(p * math.pi)))
        composite = big.crop((cam_dx, cam_dy, cam_dx + width, cam_dy + height)).copy()

        # --- character idle: breathing bob + sway (steady in frame → parallax) ---
        sway = int(math.sin(frame * 0.11) * 9)
        bob = int(math.sin(frame * 0.18) * 7)
        char_pos = (char_x + sway, char_y + bob)
        composite.paste(char, char_pos, char)

        # --- audio-driven mouth (opens with speech loudness; generic flap if no wav) ---
        if shot.get("dialogue"):
            openness = env[frame] if env else (math.sin(frame * 0.5) + 1) / 2
            mh = int(2 + openness * 17)
            draw = ImageDraw.Draw(composite)
            mx = char_pos[0] + char_w // 2 - 12
            my = char_pos[1] + int(char_h * 0.20)
            draw.ellipse([mx, my, mx + 24, my + mh], fill=(70, 35, 35))

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
