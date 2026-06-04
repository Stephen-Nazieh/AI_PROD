#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Master Host Workspace Context Mapping
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = WORKSPACE_ROOT / "01_SKILLS"

print("🎙️ Solocorn Script-to-Manifest Compiler Core Online.")

def compile_markdown_script_to_manifests(markdown_file_path: str, track_name: str):
    """
    Reads a structured pedagogical lesson script from your curriculum vault,
    parses out metadata blocks, and programmatically exports execution 
    manifests for the headless media bridge.
    """
    md_path = Path(markdown_file_path)
    if not md_path.exists():
        print(f"❌ Error: Script file not found at {md_path}")
        return False

    print(f"📖 Reading raw script layout: {md_path.name}")
    
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    scenes = []
    current_scene = {}
    is_parsing_scene = False

    # High-speed tokenization loop parsing custom script layouts
    for line in lines:
        cleaned = line.strip()
        
        # Identify Scene Initialization Bounds
        if cleaned.startswith("## SCENE:"):
            if current_scene:
                scenes.append(current_scene)
            current_scene = {
                "track_name": track_name,
                "asset_name": cleaned.split("## SCENE:")[1].strip().lower().replace(" ", "_"),
                "stage": "manim_render", # Default rendering plane
                "quality_flag": "-ql"
            }
            is_parsing_scene = True
            continue
            
        if is_parsing_scene and ":" in cleaned:
            # Parse localized key-value parameters inside the scene block
            key, val = cleaned.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            
            if key in ["scene_name", "stage", "quality_flag"]:
                current_scene[key] = val
            elif key == "output_movie":
                current_scene["output_movie"] = str(WORKSPACE_ROOT / val)

    # Append trailing structural node
    if current_scene:
        scenes.append(current_scene)

    print(f"📊 Extracted {len(scenes)} automation scenes from script file.")

    # Write independent structural task manifests to disk
    generated_manifests = []
    for i, scene in enumerate(scenes, 1):
        manifest_filename = f"task_{track_name}_scene_{i}_{scene['asset_name']}.json"
        manifest_path = SKILLS_DIR / manifest_filename
        
        # Dynamically set target media export destination paths if not explicitly stated
        if "output_movie" not in scene:
            scene["output_movie"] = str(WORKSPACE_ROOT / "03_ASSETS" / f"{scene['asset_name']}.mp4")

        with open(manifest_path, 'w', encoding='utf-8') as mf:
            json.dump(scene, mf, indent=2)
            
        print(f"   -> Successfully generated manifest: {manifest_filename}")
        generated_manifests.append(str(manifest_path))

    return generated_manifests

if __name__ == "__main__":
    # Internal CLI capability wrapper for orchestration daemons
    if len(sys.argv) > 2:
        script_file = sys.argv[1]
        target_track = sys.argv[2]
        compile_markdown_script_to_manifests(script_file, target_track)
    else:
        print("💡 Usage: python script_processor.py <path_to_markdown> <track_name>")