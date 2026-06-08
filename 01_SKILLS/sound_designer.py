#!/usr/bin/env python3
"""
sound_designer.py — Automated Sound Design & Foley Synthesis

Generates sound effects from scene descriptions using:
1. Synthesized foley (scipy signal generation)
2. Sample library matching from 06_SHARED_ASSETS/sfx-stems/
3. ffmpeg mixing into final sound design tracks

Usage:
    python sound_designer.py init-library
    python sound_designer.py design <project_slug> --scene SC001
    python sound_designer.py design <project_slug> --all-scenes
    python sound_designer.py synthesize <type> --output path.wav

Sound types:
    footstep, door, wind, rain, thunder, city, classroom,
    typing, paper, chair, clock, phone, heartbeat, fire
"""

import argparse
import json
import math
import os
import subprocess
from pathlib import Path

import numpy as np
import scipy.signal
import soundfile as sf

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SFX_LIBRARY = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "sfx-stems"
SAMPLE_RATE = 48000

# Scene heading → SFX category mapping
SCENE_SFX = {
    "classroom": ["typing", "paper", "chair", "clock", "footstep"],
    "office": ["typing", "phone", "footstep", "door", "chair"],
    "park": ["wind", "bird", "footstep", "leaf"],
    "city": ["city", "car", "footstep", "horn"],
    "night": ["cricket", "wind", "owl", "footstep"],
    "home": ["door", "clock", "footstep", "phone"],
    "rain": ["rain", "thunder", "footstep"],
    "forest": ["wind", "bird", "leaf", "footstep"],
}


def init_library() -> dict:
    """Create SFX library folder structure."""
    SFX_LIBRARY.mkdir(parents=True, exist_ok=True)
    categories = [
        "footstep", "door", "wind", "rain", "thunder", "city", "classroom",
        "typing", "paper", "chair", "clock", "phone", "heartbeat", "fire",
        "bird", "car", "horn", "cricket", "owl", "leaf",
    ]
    created = []
    for cat in categories:
        cat_dir = SFX_LIBRARY / cat
        cat_dir.mkdir(exist_ok=True)
        created.append(str(cat_dir))
    
    manifest = {
        "version": 1,
        "categories": categories,
        "note": "Place WAV files in each category folder. Empty folders use synthesized fallback.",
    }
    (SFX_LIBRARY / "sfx_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    return {"status": "ok", "library_dir": str(SFX_LIBRARY), "categories": len(created)}


def synthesize(type_name: str, duration: float = 2.0) -> np.ndarray:
    """Synthesize a basic sound effect."""
    samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, samples)
    
    if type_name == "footstep":
        # Thud + noise burst
        env = np.exp(-t * 15)
        noise = np.random.randn(samples) * 0.3
        thud = np.sin(2 * np.pi * 80 * t) * env * 0.7
        return (noise + thud) * 0.5
    
    elif type_name == "wind":
        # Pink noise + slow amplitude modulation
        noise = np.random.randn(samples)
        # Simple pink noise approximation
        pink = np.cumsum(noise)
        pink = pink / np.max(np.abs(pink) + 1e-8)
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.3 * t)
        return pink * lfo * 0.3
    
    elif type_name == "rain":
        # White noise with envelope
        noise = np.random.randn(samples) * 0.15
        return noise
    
    elif type_name == "thunder":
        # Low rumble + crack
        rumble = np.sin(2 * np.pi * 40 * t) * np.exp(-t * 2)
        crack = np.random.randn(samples) * np.exp(-t * 8) * 0.5
        return (rumble + crack) * 0.6
    
    elif type_name == "typing":
        # Short clicks
        audio = np.zeros(samples)
        click_interval = int(SAMPLE_RATE * 0.15)
        for i in range(0, samples, click_interval):
            if i + 100 < samples:
                click = np.exp(-np.linspace(0, 5, 100)) * np.random.randn(100) * 0.3
                audio[i:i+100] += click
        return audio * 0.5
    
    elif type_name == "clock":
        # Tick tock
        audio = np.zeros(samples)
        tick_interval = int(SAMPLE_RATE * 1.0)
        for i in range(0, samples, tick_interval):
            if i + 200 < samples:
                tick = np.sin(2 * np.pi * 1000 * np.linspace(0, 0.02, 200)) * np.exp(-np.linspace(0, 10, 200))
                audio[i:i+200] += tick * 0.3
        return audio
    
    elif type_name == "heartbeat":
        # Lub-dub
        audio = np.zeros(samples)
        beat_interval = int(SAMPLE_RATE * 0.8)
        for i in range(0, samples, beat_interval):
            if i + 400 < samples:
                lub = np.sin(2 * np.pi * 30 * np.linspace(0, 0.15, 150)) * np.exp(-np.linspace(0, 5, 150))
                dub = np.sin(2 * np.pi * 25 * np.linspace(0, 0.15, 150)) * np.exp(-np.linspace(0, 5, 150))
                audio[i:i+150] += lub * 0.5
                if i + 300 < samples:
                    audio[i+150:i+300] += dub * 0.4
        return audio
    
    elif type_name == "door":
        # Creak + thud
        creak = np.sin(2 * np.pi * (200 + 100 * np.sin(2 * np.pi * 0.5 * t)) * t) * 0.2
        thud = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 10) * 0.5
        return creak + thud
    
    elif type_name == "phone":
        # Ring tone
        audio = np.zeros(samples)
        ring_interval = int(SAMPLE_RATE * 3.0)
        for i in range(0, samples, ring_interval):
            if i + int(SAMPLE_RATE * 2) < samples:
                ring = np.sin(2 * np.pi * 440 * t[:int(SAMPLE_RATE*2)]) * 0.15
                ring *= (np.sin(2 * np.pi * 2 * t[:int(SAMPLE_RATE*2)]) > 0).astype(float)
                audio[i:i+int(SAMPLE_RATE*2)] += ring
        return audio
    
    elif type_name == "fire":
        # Crackling noise
        noise = np.random.randn(samples) * 0.1
        crackles = np.random.rand(samples) < 0.001
        crackle_env = np.exp(-np.linspace(0, 10, 500))
        for idx in np.where(crackles)[0]:
            if idx + 500 < samples:
                crack = np.random.randn(500) * crackle_env * 0.5
                noise[idx:idx+500] += crack
        return noise
    
    elif type_name == "city":
        # Distant traffic rumble
        noise = np.random.randn(samples) * 0.05
        rumble = np.sin(2 * np.pi * 50 * t) * 0.05
        return noise + rumble
    
    else:
        # Default: white noise burst
        return np.random.randn(samples) * 0.1


def find_or_synthesize(type_name: str, duration: float = 2.0) -> Path:
    """Find a sample in the library, or synthesize one."""
    cat_dir = SFX_LIBRARY / type_name
    if cat_dir.exists():
        samples = list(cat_dir.glob("*.wav"))
        if samples:
            return samples[0]  # Return first sample
    
    # Synthesize fallback
    audio = synthesize(type_name, duration)
    out_path = SFX_LIBRARY / f"_synth_{type_name}.wav"
    sf.write(str(out_path), audio, SAMPLE_RATE)
    return out_path


def design_scene_sfx(project_slug: str, scene_id: str, shot_list: dict) -> dict:
    """Generate sound design for a scene."""
    scene = None
    for s in shot_list.get("scenes", []):
        if s["scene_id"] == scene_id:
            scene = s
            break
    
    if not scene:
        return {"status": "error", "message": f"Scene {scene_id} not found"}
    
    heading = scene.get("heading", "").lower()
    sfx_types = []
    for keyword, types in SCENE_SFX.items():
        if keyword in heading:
            sfx_types.extend(types)
    
    if not sfx_types:
        sfx_types = ["wind", "footstep"]
    
    # Deduplicate
    sfx_types = list(dict.fromkeys(sfx_types))
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    sfx_out_dir = project_dir / "06-audio" / "sound_design"
    sfx_out_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    for sfx_type in sfx_types[:5]:  # Max 5 layers
        sample = find_or_synthesize(sfx_type, duration=5.0)
        out_path = sfx_out_dir / f"{scene_id}_{sfx_type}.wav"
        
        # Copy or synthesize to scene folder
        if sample.parent == SFX_LIBRARY and sample.name.startswith("_synth_"):
            # Already synthesized, just copy
            import shutil
            shutil.copy(str(sample), str(out_path))
        else:
            import shutil
            shutil.copy(str(sample), str(out_path))
        
        results.append({"type": sfx_type, "path": str(out_path)})
    
    return {
        "status": "ok",
        "scene_id": scene_id,
        "heading": scene.get("heading", ""),
        "sfx_layers": results,
        "output_dir": str(sfx_out_dir),
    }


def mix_scene_sfx(project_slug: str, scene_id: str) -> dict:
    """Mix all SFX layers for a scene into a single track."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    sfx_dir = project_dir / "06-audio" / "sound_design"
    
    scene_files = sorted(sfx_dir.glob(f"{scene_id}_*.wav"))
    if not scene_files:
        return {"status": "error", "message": "No SFX layers to mix"}
    
    out_path = sfx_dir / f"{scene_id}_sfx_mix.wav"
    
    # Build ffmpeg amix filter
    inputs = []
    for f in scene_files:
        inputs.extend(["-i", str(f)])
    
    filter_complex = f"amix=inputs={len(scene_files)}:duration=longest:dropout_transition=2,volume={len(scene_files)}"
    
    subprocess.run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        str(out_path),
    ], capture_output=True, check=True)
    
    return {
        "status": "ok",
        "scene_id": scene_id,
        "layers": len(scene_files),
        "output": str(out_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Sound Designer")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-library", help="Create SFX library folders")

    p_design = sub.add_parser("design", help="Design SFX for scenes")
    p_design.add_argument("project_slug")
    p_design.add_argument("--scene")
    p_design.add_argument("--all-scenes", action="store_true")

    p_mix = sub.add_parser("mix", help="Mix SFX layers into scene tracks")
    p_mix.add_argument("project_slug")
    p_mix.add_argument("--scene")

    p_synth = sub.add_parser("synthesize", help="Synthesize a single sound")
    p_synth.add_argument("type")
    p_synth.add_argument("--duration", type=float, default=2.0)
    p_synth.add_argument("--output", required=True)

    args = parser.parse_args()

    if args.command == "init-library":
        result = init_library()
        print(json.dumps(result, indent=2))
    elif args.command == "synthesize":
        audio = synthesize(args.type, args.duration)
        sf.write(args.output, audio, SAMPLE_RATE)
        print(json.dumps({"status": "ok", "type": args.type, "output": args.output}, indent=2))
    elif args.command == "design":
        project_dir = WORKSPACE_ROOT / "05_PROJECTS" / args.project_slug
        shot_list = json.loads((project_dir / "01-scripts" / "shot-list.json").read_text(encoding="utf-8"))
        
        if args.scene:
            result = design_scene_sfx(args.project_slug, args.scene, shot_list)
            print(json.dumps(result, indent=2))
        elif args.all_scenes:
            results = []
            for scene in shot_list.get("scenes", []):
                result = design_scene_sfx(args.project_slug, scene["scene_id"], shot_list)
                results.append(result)
            print(json.dumps({"status": "ok", "total": len(results), "results": results}, indent=2))
        else:
            print(json.dumps({"status": "error", "message": "Specify --scene or --all-scenes"}))
    elif args.command == "mix":
        if args.scene:
            result = mix_scene_sfx(args.project_slug, args.scene)
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"status": "error", "message": "Specify --scene"}))


if __name__ == "__main__":
    main()
