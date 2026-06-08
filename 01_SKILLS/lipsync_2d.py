#!/usr/bin/env python3
"""
lipsync_2d.py — 2D Mouth Shape Animation

Generates per-frame mouth shape overlays for 2D characters based on
audio analysis. Creates a mouth sprite sheet and applies the correct
shape per frame.

Usage:
    python lipsync_2d.py generate-sheet --style anime
    python lipsync_2d.py animate <project_slug> --shot SC001_SH001
    python lipsync_2d.py animate <project_slug> --all-shots
"""

import argparse
import json
import math
from pathlib import Path

import librosa
import numpy as np
from PIL import Image, ImageDraw

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
FPS = 24

MOUTH_SHAPES = ["silence", "A", "I", "U", "E", "O"]


def generate_mouth_sheet(style: str = "anime", size: int = 64) -> Path:
    """Generate a sprite sheet of mouth shapes."""
    sheet_w = size * len(MOUTH_SHAPES)
    sheet_h = size
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    
    colors = {
        "anime": {"skin": (255, 200, 180), "lip": (180, 100, 100), "inside": (60, 30, 30)},
        "cartoon": {"skin": (255, 220, 177), "lip": (200, 80, 80), "inside": (50, 20, 20)},
        "realistic": {"skin": (255, 200, 180), "lip": (160, 80, 80), "inside": (70, 35, 35)},
    }
    c = colors.get(style, colors["anime"])
    
    for i, shape in enumerate(MOUTH_SHAPES):
        mouth = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(mouth)
        
        cx, cy = size // 2, size // 2
        
        if shape == "silence":
            # Closed line
            draw.line([cx-12, cy, cx+12, cy], fill=c["lip"], width=2)
        elif shape == "A":
            # Wide open
            draw.ellipse([cx-14, cy-10, cx+14, cy+16], fill=c["inside"])
            draw.arc([cx-14, cy-10, cx+14, cy+16], 0, 180, fill=c["lip"], width=2)
            draw.arc([cx-14, cy-10, cx+14, cy+16], 180, 360, fill=c["lip"], width=2)
        elif shape == "I":
            # Wide smile/teeth
            draw.arc([cx-14, cy-4, cx+14, cy+12], 0, 180, fill=c["inside"])
            draw.line([cx-14, cy+2, cx+14, cy+2], fill=(240, 240, 240), width=3)
            draw.arc([cx-14, cy-4, cx+14, cy+12], 0, 180, fill=c["lip"], width=2)
        elif shape == "U":
            # Puckered
            draw.ellipse([cx-8, cy-4, cx+8, cy+10], fill=c["inside"])
            draw.ellipse([cx-8, cy-4, cx+8, cy+10], outline=c["lip"], width=2)
        elif shape == "E":
            # Wide grin
            draw.arc([cx-14, cy-2, cx+14, cy+10], 0, 180, fill=c["inside"])
            draw.arc([cx-14, cy-2, cx+14, cy+10], 0, 180, fill=c["lip"], width=2)
        elif shape == "O":
            # Round open
            draw.ellipse([cx-10, cy-6, cx+10, cy+12], fill=c["inside"])
            draw.ellipse([cx-10, cy-6, cx+10, cy+12], outline=c["lip"], width=2)
        
        sheet.paste(mouth, (i * size, 0))
    
    sheet_path = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "mouth_sheets" / f"mouth_sheet_{style}.png"
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sheet_path)
    
    return sheet_path


def extract_visemes(wav_path: Path, fps: float = 24.0) -> list:
    """Extract viseme timing from audio."""
    y, sr = librosa.load(str(wav_path), sr=None, mono=True)
    frame_duration = int(sr / fps)
    total_frames = int(len(y) / frame_duration) + 1
    
    rms = librosa.feature.rms(y=y, frame_length=frame_duration, hop_length=frame_duration)[0]
    spec_cent = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=frame_duration, hop_length=frame_duration)[0]
    spec_band = librosa.feature.spectral_bandwidth(y=y, sr=sr, n_fft=frame_duration, hop_length=frame_duration)[0]
    
    rms_norm = (rms - rms.min()) / (rms.max() - rms.min() + 1e-8)
    cent_norm = (spec_cent - spec_cent.min()) / (spec_cent.max() - spec_cent.min() + 1e-8)
    band_norm = (spec_band - spec_band.min()) / (spec_band.max() - spec_band.min() + 1e-8)
    
    visemes = []
    for i in range(min(total_frames, len(rms))):
        energy = rms_norm[i]
        brightness = cent_norm[i]
        spread = band_norm[i]
        
        if energy < 0.15:
            viseme = "silence"
        elif brightness > 0.6 and spread > 0.5:
            viseme = "I"
        elif brightness < 0.3 and spread < 0.4:
            viseme = "U"
        elif brightness > 0.5 and spread < 0.4:
            viseme = "A"
        elif brightness < 0.4 and spread > 0.5:
            viseme = "O"
        else:
            viseme = "E"
        
        visemes.append({"frame": i + 1, "viseme": viseme})
    
    return visemes


def animate_shot(project_slug: str, shot_id: str, style: str = "anime") -> dict:
    """Generate per-frame mouth overlays for a shot."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    audio_dir = project_dir / "06-audio" / "dialogue"
    wav_path = audio_dir / f"{shot_id}.wav"
    
    if not wav_path.exists():
        return {"status": "error", "message": f"No audio for {shot_id}"}
    
    # Get mouth sheet
    sheet_path = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "mouth_sheets" / f"mouth_sheet_{style}.png"
    if not sheet_path.exists():
        sheet_path = generate_mouth_sheet(style)
    
    sheet = Image.open(sheet_path)
    mouth_size = sheet.height
    
    # Extract visemes
    visemes = extract_visemes(wav_path)
    
    # Generate mouth frames
    mouth_dir = project_dir / "04-raw_renders" / shot_id / "mouth_overlays"
    mouth_dir.mkdir(parents=True, exist_ok=True)
    
    viseme_map = {"silence": 0, "A": 1, "I": 2, "U": 3, "E": 4, "O": 5}
    
    for v in visemes:
        frame = v["frame"]
        viseme = v["viseme"]
        idx = viseme_map.get(viseme, 0)
        
        mouth = sheet.crop((idx * mouth_size, 0, (idx + 1) * mouth_size, mouth_size))
        mouth_path = mouth_dir / f"mouth_{frame:04d}.png"
        mouth.save(mouth_path)
    
    return {
        "status": "ok",
        "shot_id": shot_id,
        "frames": len(visemes),
        "mouth_dir": str(mouth_dir),
        "sheet": str(sheet_path),
    }


def main():
    parser = argparse.ArgumentParser(description="2D Lip Sync")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sheet = sub.add_parser("generate-sheet", help="Generate mouth sprite sheet")
    p_sheet.add_argument("--style", default="anime", choices=["anime", "cartoon", "realistic"])

    p_anim = sub.add_parser("animate", help="Animate mouths for shot(s)")
    p_anim.add_argument("project_slug")
    p_anim.add_argument("--shot")
    p_anim.add_argument("--all-shots", action="store_true")
    p_anim.add_argument("--style", default="anime")

    args = parser.parse_args()

    if args.command == "generate-sheet":
        path = generate_mouth_sheet(args.style)
        print(json.dumps({"status": "ok", "sheet": str(path)}, indent=2))
    elif args.command == "animate":
        if args.shot:
            result = animate_shot(args.project_slug, args.shot, args.style)
            print(json.dumps(result, indent=2))
        elif args.all_shots:
            project_dir = WORKSPACE_ROOT / "05_PROJECTS" / args.project_slug
            audio_dir = project_dir / "06-audio" / "dialogue"
            results = []
            for wav in sorted(audio_dir.glob("*.wav")):
                result = animate_shot(args.project_slug, wav.stem, args.style)
                results.append(result)
            print(json.dumps({"status": "ok", "total": len(results), "results": results}, indent=2))
        else:
            print(json.dumps({"status": "error", "message": "Specify --shot or --all-shots"}))


if __name__ == "__main__":
    main()
