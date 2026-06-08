#!/usr/bin/env python3
"""
storyboard_to_2d.py — Storyboard Frames → Full 2D Animation Pipeline

Orchestrates the full 2D animation pipeline from storyboard to final frames:
1. Generate character references
2. Generate backgrounds
3. Composite characters onto backgrounds with animation
4. Add lip-sync mouths
5. Encode to video

Usage:
    python storyboard_to_2d.py full-pipeline <project_slug>
    python storyboard_to_2d.py generate-characters <project_slug>
    python storyboard_to_2d.py generate-backgrounds <project_slug>
    python storyboard_to_2d.py composite-all <project_slug>
    python storyboard_to_2d.py encode-all <project_slug>
"""

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def generate_characters(project_slug: str) -> dict:
    """Generate 2D characters for all characters in shot list."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    shot_list = json.loads((project_dir / "01-scripts" / "shot-list.json").read_text(encoding="utf-8"))
    
    # Extract unique characters from shot actions/dialogue
    # For now, use hardcoded defaults
    characters = [
        {"name": "teacher", "prompt": "a friendly statistics teacher, glasses, professional attire, warm smile"},
        {"name": "student_01", "prompt": "a curious teenage student, casual clothes, eager expression"},
        {"name": "student_02", "prompt": "a thoughtful teenage student, hoodie, contemplative look"},
        {"name": "narrator", "prompt": "a wise narrator figure, distinguished appearance, calm demeanor"},
    ]
    
    results = []
    for char in characters:
        cmd = [
            "python3", str(WORKSPACE_ROOT / "01_SKILLS" / "character_2d_generator.py"),
            "create", project_slug, char["name"],
            "--prompt", char["prompt"],
            "--style", "anime",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKSPACE_ROOT)
        try:
            data = json.loads(result.stdout.split("\n")[-2] if result.stdout else "{}")
            results.append(data)
        except Exception:
            results.append({"name": char["name"], "status": "unknown"})
    
    return {"status": "ok", "characters": len(results), "results": results}


def generate_backgrounds(project_slug: str) -> dict:
    """Generate 2D backgrounds for all scenes."""
    cmd = [
        "python3", str(WORKSPACE_ROOT / "01_SKILLS" / "background_2d_generator.py"),
        "generate", project_slug, "--all-scenes", "--style", "anime",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKSPACE_ROOT)
    try:
        return json.loads(result.stdout.split("\n")[-2] if result.stdout else "{}")
    except Exception:
        return {"status": "error", "message": "Background generation failed"}


def composite_all(project_slug: str) -> dict:
    """Composite all shots."""
    cmd = [
        "python3", str(WORKSPACE_ROOT / "01_SKILLS" / "animation_2d_compositor.py"),
        "composite", project_slug, "--all-shots",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKSPACE_ROOT)
    try:
        return json.loads(result.stdout.split("\n")[-2] if result.stdout else "{}")
    except Exception:
        return {"status": "error", "message": "Composition failed"}


def encode_all(project_slug: str) -> dict:
    """Encode all shots to video."""
    cmd = [
        "python3", str(WORKSPACE_ROOT / "01_SKILLS" / "animation_2d_compositor.py"),
        "encode", project_slug, "--all-shots",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=WORKSPACE_ROOT)
    try:
        return json.loads(result.stdout.split("\n")[-2] if result.stdout else "{}")
    except Exception:
        return {"status": "error", "message": "Encoding failed"}


def full_pipeline(project_slug: str) -> dict:
    """Run the complete 2D animation pipeline."""
    print("🎬 Starting 2D Animation Pipeline...")
    print("=" * 50)
    
    print("\n📋 Step 1: Generating characters...")
    char_result = generate_characters(project_slug)
    print(json.dumps(char_result, indent=2))
    
    print("\n🏞️  Step 2: Generating backgrounds...")
    bg_result = generate_backgrounds(project_slug)
    print(json.dumps(bg_result, indent=2))
    
    print("\n🎨 Step 3: Generating mouth sheets...")
    subprocess.run([
        "python3", str(WORKSPACE_ROOT / "01_SKILLS" / "lipsync_2d.py"),
        "generate-sheet", "--style", "anime",
    ], capture_output=True, cwd=WORKSPACE_ROOT)
    
    print("\n🎭 Step 4: Compositing all shots...")
    comp_result = composite_all(project_slug)
    print(json.dumps(comp_result, indent=2))
    
    print("\n🎬 Step 5: Encoding to video...")
    enc_result = encode_all(project_slug)
    print(json.dumps(enc_result, indent=2))
    
    print("\n✅ 2D Animation Pipeline Complete!")
    
    return {
        "status": "ok",
        "project": project_slug,
        "pipeline": "2d_full",
        "steps_completed": 5,
    }


def main():
    parser = argparse.ArgumentParser(description="Storyboard to 2D Animation")
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd in ["full-pipeline", "generate-characters", "generate-backgrounds", "composite-all", "encode-all"]:
        p = sub.add_parser(cmd, help=cmd.replace("-", " "))
        p.add_argument("project_slug")

    args = parser.parse_args()
    project_slug = args.project_slug
    
    if args.command == "full-pipeline":
        result = full_pipeline(project_slug)
        print(json.dumps(result, indent=2))
    elif args.command == "generate-characters":
        result = generate_characters(project_slug)
        print(json.dumps(result, indent=2))
    elif args.command == "generate-backgrounds":
        result = generate_backgrounds(project_slug)
        print(json.dumps(result, indent=2))
    elif args.command == "composite-all":
        result = composite_all(project_slug)
        print(json.dumps(result, indent=2))
    elif args.command == "encode-all":
        result = encode_all(project_slug)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
