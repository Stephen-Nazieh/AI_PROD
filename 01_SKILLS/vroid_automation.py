#!/usr/bin/env python3
"""
vroid_automation.py — VRoid Studio Automation & Character Template Library

Manages a library of base VRM character presets and automates VRoid Studio
via AppleScript for export. Supports template cloning and auto-import into
Blender.

Usage:
    python vroid_automation.py init-library
    python vroid_automation.py list
    python vroid_automation.py clone <template_name> <new_name> --project <slug>
    python vroid_automation.py export --project <slug> --character <name>
    python vroid_automation.py auto-import <project_slug> --character <name>
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "character-presets"
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"


def _load_manifest() -> dict:
    manifest_path = LIBRARY_DIR / "library_manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"templates": {}, "version": 1}


def _save_manifest(manifest: dict):
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = LIBRARY_DIR / "library_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ── Library Management ──────────────────────────────────────────────────────

def init_library() -> dict:
    """Create the character preset library structure."""
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "templates": {
            "default_human": {
                "name": "Default Human Base",
                "vrm_path": "",
                "description": "Base humanoid template. Create in VRoid Studio and export as VRM to this folder.",
                "traits": {"gender": "neutral", "age": "adult", "style": "realistic"},
            },
            "anime_student": {
                "name": "Anime Student",
                "vrm_path": "",
                "description": "Young anime-style student character. Export from VRoid Studio.",
                "traits": {"gender": "neutral", "age": "teen", "style": "anime"},
            },
            "professor": {
                "name": "Professor",
                "vrm_path": "",
                "description": "Adult professional/educator character. Export from VRoid Studio.",
                "traits": {"gender": "neutral", "age": "adult", "style": "semi-realistic"},
            },
        },
        "note": "To populate: Open VRoid Studio, design character, File > Export as VRM, save to this folder with matching template name.",
    }
    _save_manifest(manifest)

    # Create placeholder folders
    for key in manifest["templates"]:
        (LIBRARY_DIR / key).mkdir(exist_ok=True)

    return {
        "status": "ok",
        "library_dir": str(LIBRARY_DIR),
        "templates_created": len(manifest["templates"]),
        "message": "Library initialized. Design characters in VRoid Studio and export VRMs to populate templates.",
    }


def list_templates() -> dict:
    manifest = _load_manifest()
    templates = []
    for key, data in manifest.get("templates", {}).items():
        vrm_path = LIBRARY_DIR / key / f"{key}.vrm"
        glb_path = LIBRARY_DIR / key / f"{key}.glb"
        available = vrm_path.exists() or glb_path.exists()
        templates.append({
            "id": key,
            "name": data.get("name", key),
            "available": available,
            "vrm_path": str(vrm_path) if vrm_path.exists() else None,
            "glb_path": str(glb_path) if glb_path.exists() else None,
            "traits": data.get("traits", {}),
        })
    return {"status": "ok", "templates": templates, "count": len(templates)}


def clone_template(template_name: str, new_name: str, project_slug: str) -> dict:
    """Clone a template VRM into a project."""
    manifest = _load_manifest()
    if template_name not in manifest.get("templates", {}):
        return {"status": "error", "message": f"Template '{template_name}' not found"}

    template_dir = LIBRARY_DIR / template_name
    vrm_src = template_dir / f"{template_name}.vrm"
    glb_src = template_dir / f"{template_name}.glb"

    if not vrm_src.exists() and not glb_src.exists():
        return {
            "status": "error",
            "message": f"Template '{template_name}' has no VRM/glb file. Design it in VRoid Studio first.",
        }

    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    chars_dir = project_dir / "05-assets" / "characters"
    chars_dir.mkdir(parents=True, exist_ok=True)

    src = vrm_src if vrm_src.exists() else glb_src
    dst = chars_dir / f"{new_name}{src.suffix}"
    shutil.copy2(str(src), str(dst))

    # Update character manifest
    char_manifest_path = project_dir / "01-scripts" / "character_manifest.json"
    char_manifest = {}
    if char_manifest_path.exists():
        char_manifest = json.loads(char_manifest_path.read_text(encoding="utf-8"))

    char_manifest.setdefault("characters", {})[new_name] = {
        "display_name": new_name.replace("_", " ").title(),
        "model_path": str(Path("05-assets") / "characters" / f"{new_name}{src.suffix}"),
        "model_format": src.suffix.lstrip("."),
        "height_meters": 1.7,
        "default_position": [0, 0, 0],
        "default_rotation": [0, 0, 0],
        "scale": 1.0,
        "source_template": template_name,
    }
    char_manifest_path.write_text(json.dumps(char_manifest, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "template": template_name,
        "new_character": new_name,
        "output_path": str(dst),
        "project": project_slug,
    }


# ── VRoid Studio AppleScript Automation ─────────────────────────────────────

def launch_vroid_for_edit(vrm_path: str) -> dict:
    """Launch VRoid Studio with a specific VRM file for editing."""
    vrm_file = Path(vrm_path)
    if not vrm_file.exists():
        return {"status": "error", "message": f"VRM not found: {vrm_path}"}

    script = f'''
    tell application "VRoidStudio"
        activate
    end tell
    '''
    # Note: VRoid Studio doesn't have rich AppleScript support.
    # We can only launch it. The user must manually open the file.
    subprocess.run(["osascript", "-e", script], check=False)

    return {
        "status": "ok",
        "message": "VRoid Studio launched. Manually open the VRM file for editing.",
        "vrm_path": vrm_path,
    }


def auto_import_to_blender(project_slug: str, character_name: str) -> dict:
    """Trigger blender_character_importer for a project character."""
    script_path = WORKSPACE_ROOT / "01_SKILLS" / "blender_character_importer.py"
    python = WORKSPACE_ROOT / "env" / "bin" / "python3"

    cmd = [
        str(python),
        str(script_path),
        "import",
        project_slug,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))

    return {
        "status": "ok",
        "project": project_slug,
        "character": character_name,
        "import_output": result.stdout,
        "import_errors": result.stderr if result.returncode != 0 else "",
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VRoid Studio Automation")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-library", help="Create character preset library")

    p_list = sub.add_parser("list", help="List available templates")

    p_clone = sub.add_parser("clone", help="Clone template to project")
    p_clone.add_argument("template_name", help="Source template ID")
    p_clone.add_argument("new_name", help="New character name")
    p_clone.add_argument("--project", required=True, help="Project slug")

    p_export = sub.add_parser("export", help="Launch VRoid Studio for export")
    p_export.add_argument("--project", required=True, help="Project slug")
    p_export.add_argument("--character", required=True, help="Character name")

    p_import = sub.add_parser("auto-import", help="Import character VRM to Blender")
    p_import.add_argument("project_slug", help="Project identifier")
    p_import.add_argument("--character", required=True, help="Character name")

    args = parser.parse_args()

    if args.command == "init-library":
        result = init_library()
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        result = list_templates()
        print(json.dumps(result, indent=2))

    elif args.command == "clone":
        result = clone_template(args.template_name, args.new_name, args.project)
        print(json.dumps(result, indent=2))

    elif args.command == "export":
        project_dir = WORKSPACE_ROOT / "05_PROJECTS" / args.project
        chars_dir = project_dir / "05-assets" / "characters"
        vrm_path = chars_dir / f"{args.character}.vrm"
        result = launch_vroid_for_edit(str(vrm_path))
        print(json.dumps(result, indent=2))

    elif args.command == "auto-import":
        result = auto_import_to_blender(args.project_slug, args.character)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
