#!/usr/bin/env python3
"""
audio_lipsync.py — True Audio-Driven Lip Sync for VRM Characters

Analyzes WAV audio using librosa MFCC + energy extraction, then maps
acoustic features to VRM blend shape visemes for frame-accurate lip sync.

Usage:
    python audio_lipsync.py sync <project_slug> --shot SC001_SH001
    python audio_lipsync.py sync <project_slug> --all-shots

Viseme mapping (6 VRM shapes):
    Silence / breath     → all 0
    A / ah (father)      → A (jawOpen + mouthOpen)
    I / ee (see)         → I (mouthSmile + mouthStretch)
    U / oo (blue)        → U (mouthPucker + mouthFunnel)
    E / eh (bed)         → E (mouthFrown + mouthStretch)
    O / oh (go)          → O (mouthClose + jawOpen)
"""

import argparse
import json
import math
import numpy as np
from pathlib import Path

import librosa
import scipy.signal

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

# Viseme → VRM blend shape weights
VISeme_MAP = {
    "silence": {},
    "A": {"A": 0.9, "O": 0.2},
    "I": {"I": 0.9, "A": 0.1},
    "U": {"U": 0.9, "O": 0.3},
    "E": {"E": 0.9, "I": 0.2},
    "O": {"O": 0.9, "A": 0.3},
}

# Phoneme → viseme classification
PHONEME_TO_VISEME = {
    # A group
    "aa": "A", "ae": "A", "ah": "A", "ao": "A", "aw": "A", "ay": "A",
    # I group
    "iy": "I", "ih": "I", "ey": "I", "eh": "E",
    # U group
    "uw": "U", "uh": "U", "ow": "U", "oy": "U",
    # E group
    "er": "E", "ah": "E",
    # O group
    "ao": "O", "aa": "O",
    # Consonants that need lip closure
    "b": "O", "p": "O", "m": "O",
    "f": "I", "v": "I",
    "w": "U", "wh": "U",
    "sh": "I", "zh": "I", "ch": "I", "jh": "I",
    "th": "E", "dh": "E",
    "l": "A", "r": "A",
    "t": "A", "d": "A", "n": "A", "s": "A", "z": "A",
    "k": "A", "g": "A", "ng": "A",
    "y": "I", "hh": "A",
}


def extract_visemes_from_audio(wav_path: Path, fps: float = 24.0) -> list:
    """Extract viseme timing from audio using MFCC + energy analysis."""
    y, sr = librosa.load(str(wav_path), sr=None, mono=True)
    
    # Frame duration in samples
    frame_duration = int(sr / fps)
    total_frames = int(len(y) / frame_duration) + 1
    
    # Compute RMS energy per frame
    rms = librosa.feature.rms(y=y, frame_length=frame_duration, hop_length=frame_duration)[0]
    
    # Compute spectral centroid (brightness → vowel openness)
    spec_cent = librosa.feature.spectral_centroid(y=y, sr=sr,
        n_fft=frame_duration, hop_length=frame_duration)[0]
    
    # Compute spectral bandwidth (spread → vowel distinctness)
    spec_band = librosa.feature.spectral_bandwidth(y=y, sr=sr,
        n_fft=frame_duration, hop_length=frame_duration)[0]
    
    # Normalize
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
            viseme = "I"  # High freq, wide spread
        elif brightness < 0.3 and spread < 0.4:
            viseme = "U"  # Low freq, narrow
        elif brightness > 0.5 and spread < 0.4:
            viseme = "A"  # Mid-high freq, narrow
        elif brightness < 0.4 and spread > 0.5:
            viseme = "O"  # Low freq, wide
        else:
            viseme = "E"  # Mid range
        
        visemes.append({
            "frame": i + 1,
            "timestamp": round(i / fps, 3),
            "viseme": viseme,
            "energy": round(float(energy), 3),
            "brightness": round(float(brightness), 3),
            "spread": round(float(spread), 3),
        })
    
    return visemes


def apply_lipsync_to_blender(project_slug: str, shot_id: str, visemes: list) -> dict:
    """Apply viseme keyframes to VRM blend shapes in Blender."""
    import bpy
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    
    if not layout_path.exists():
        return {"status": "error", "message": "Layout not found"}
    
    bpy.ops.wm.open_mainfile(filepath=str(layout_path))
    scene = bpy.context.scene
    
    # Find VRM mesh
    vrm_mesh = None
    for obj in scene.objects:
        if obj.type == "MESH" and obj.data.shape_keys:
            vrm_mesh = obj
            break
    
    if not vrm_mesh:
        return {"status": "error", "message": "No VRM mesh found"}
    
    key = vrm_mesh.data.shape_keys
    if not key:
        return {"status": "error", "message": "No shape keys"}
    
    # Apply visemes
    applied = 0
    for frame_data in visemes:
        frame = frame_data["frame"]
        viseme = frame_data["viseme"]
        scene.frame_set(frame)
        
        # Reset all lip shapes
        for shape_name in ["A", "I", "U", "E", "O"]:
            for shape in key.key_blocks:
                if shape.name == shape_name:
                    shape.value = 0.0
                    shape.keyframe_insert(data_path="value", frame=frame)
        
        # Apply viseme weights
        weights = VISeme_MAP.get(viseme, {})
        for shape_name, weight in weights.items():
            for shape in key.key_blocks:
                if shape.name == shape_name:
                    shape.value = weight
                    shape.keyframe_insert(data_path="value", frame=frame)
                    applied += 1
    
    bpy.ops.wm.save_as_mainfile(filepath=str(layout_path))
    
    return {
        "status": "ok",
        "project": project_slug,
        "shot_id": shot_id,
        "total_frames": len(visemes),
        "keyframes_applied": applied,
    }


def main():
    parser = argparse.ArgumentParser(description="Audio Lip Sync")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Generate lip sync from audio")
    p_sync.add_argument("project_slug")
    p_sync.add_argument("--shot")
    p_sync.add_argument("--all-shots", action="store_true")
    p_sync.add_argument("--fps", type=float, default=24.0)

    p_test = sub.add_parser("test-audio", help="Test viseme extraction on a WAV file")
    p_test.add_argument("wav_path")
    p_test.add_argument("--fps", type=float, default=24.0)

    args = parser.parse_args()

    if args.command == "test-audio":
        visemes = extract_visemes_from_audio(Path(args.wav_path), fps=args.fps)
        print(json.dumps(visemes[:30], indent=2))
        print(f"\n... ({len(visemes)} total frames)")
    elif args.command == "sync":
        project_dir = WORKSPACE_ROOT / "05_PROJECTS" / args.project_slug
        audio_dir = project_dir / "06-audio" / "dialogue"
        
        if args.shot:
            wav_path = audio_dir / f"{args.shot}.wav"
            if not wav_path.exists():
                print(json.dumps({"status": "error", "message": f"No audio: {wav_path}"}))
                return
            visemes = extract_visemes_from_audio(wav_path, fps=args.fps)
            result = apply_lipsync_to_blender(args.project_slug, args.shot, visemes)
            print(json.dumps(result, indent=2))
        elif args.all_shots:
            results = []
            for wav_path in sorted(audio_dir.glob("*.wav")):
                shot_id = wav_path.stem
                print(f"  🎤 Syncing {shot_id}...")
                visemes = extract_visemes_from_audio(wav_path, fps=args.fps)
                result = apply_lipsync_to_blender(args.project_slug, shot_id, visemes)
                results.append(result)
            print(json.dumps({"status": "ok", "total": len(results), "results": results}, indent=2))
        else:
            print(json.dumps({"status": "error", "message": "Specify --shot or --all-shots"}))


if __name__ == "__main__":
    main()
