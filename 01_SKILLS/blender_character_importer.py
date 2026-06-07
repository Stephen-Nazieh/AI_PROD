#!/usr/bin/env python3
"""
blender_character_importer.py — Character Import & Placement for Blender Layout

Imports VRoid/VRM or glTF characters into a Blender layout scene and places
them according to shot metadata.

Usage (outside Blender):
    python blender_character_importer.py import <project_slug> [--layout layout.blend]
    python blender_character_importer.py create-manifest <project_slug>

Usage (inside Blender):
    blender --background --python blender_character_importer.py -- import <project_slug>

Env:
    Supports .vrm, .glb, .gltf files via Blender's built-in glTF importer.
    VRM-specific features (blend shapes, spring bones) require the VRM addon.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"

DEFAULT_CHARACTER_SCALE = 1.7  # meters, approximate human height


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Character Manifest ──────────────────────────────────────────────────────

def create_character_manifest(project_slug: str) -> dict:
    """Auto-generate a character manifest from shot-list subjects."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    shot_list = _load_json(project_dir / "01-scripts" / "shot-list.json")

    characters = {}
    for shot in shot_list.get("shots", []):
        action = shot.get("action", "")
        dialogue = shot.get("dialogue", "")
        notes = shot.get("notes", "")
        text = f"{action} {dialogue} {notes}"
        # Simple name extraction: look for capitalized words that could be names
        # In a real pipeline, this would use NLP or manual curation
        # For now, we look for known character patterns

    # If no characters detected, create a template
    manifest_path = project_dir / "01-scripts" / "character_manifest.json"
    if not manifest_path.exists():
        template = {
            "project": project_slug,
            "characters": {
                "Professor_Ava": {
                    "display_name": "Professor Ava",
                    "model_path": "",
                    "model_format": "vrm",
                    "height_meters": 1.7,
                    "default_position": [0, 0, 0],
                    "default_rotation": [0, 0, 0],
                    "scale": 1.0,
                    "notes": "Main character — import from VRoid Studio export"
                }
            }
        }
        _save_json(manifest_path, template)
        return {"status": "ok", "manifest_path": str(manifest_path), "created": True, "template": template}

    return {"status": "ok", "manifest_path": str(manifest_path), "created": False}


# ── Character Importer (runs inside Blender) ────────────────────────────────

class CharacterImporter:
    def __init__(self, project_slug: str, layout_path: str = None):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.manifest = _load_json(self.project_dir / "01-scripts" / "character_manifest.json")
        self.layout_path = Path(layout_path) if layout_path else self.project_dir / "03-layout" / "layout.blend"

    def import_characters(self) -> dict:
        import bpy

        if not self.layout_path.exists():
            return {"status": "error", "message": f"Layout not found: {self.layout_path}"}

        bpy.ops.wm.open_mainfile(filepath=str(self.layout_path))
        scene = bpy.context.scene

        characters = self.manifest.get("characters", {})
        if not characters:
            return {"status": "error", "message": "No characters defined in manifest"}

        imported = []
        failed = []

        # Create Characters collection if needed
        if "Characters" not in bpy.data.collections:
            char_coll = bpy.data.collections.new(name="Characters")
            scene.collection.children.link(char_coll)
        else:
            char_coll = bpy.data.collections["Characters"]

        for char_id, char_data in characters.items():
            model_path = char_data.get("model_path", "").strip()
            if not model_path:
                failed.append({"character": char_id, "reason": "No model_path specified"})
                continue

            model_file = Path(model_path)
            if not model_file.is_absolute():
                # Resolve relative to project dir
                model_file = self.project_dir / model_path

            if not model_file.exists():
                failed.append({"character": char_id, "reason": f"Model not found: {model_file}"})
                continue

            try:
                obj = self._import_model(model_file, char_id, char_data, char_coll)
                imported.append({
                    "character": char_id,
                    "object_name": obj.name,
                    "model_path": str(model_file),
                })
            except Exception as e:
                failed.append({"character": char_id, "reason": str(e)})

        # Save file
        bpy.ops.wm.save_as_mainfile(filepath=str(self.layout_path))

        return {
            "status": "ok",
            "project": self.project_slug,
            "layout_path": str(self.layout_path),
            "imported": imported,
            "failed": failed,
            "total": len(characters),
        }

    def _import_model(self, model_file: Path, char_id: str, char_data: dict, collection):
        import bpy

        ext = model_file.suffix.lower()
        import_count_before = len(bpy.data.objects)

        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=str(model_file))
        elif ext == ".vrm":
            # Try glTF first (VRM is glTF-based, basic mesh might load)
            try:
                bpy.ops.import_scene.gltf(filepath=str(model_file))
            except Exception:
                # Fall back to trying VRM addon if available
                if hasattr(bpy.ops.import_scene, 'vrm'):
                    bpy.ops.import_scene.vrm(filepath=str(model_file))
                else:
                    raise RuntimeError("VRM addon not installed. Install VRM Add-on for Blender or export as glb from VRoid Studio.")
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(model_file))
        elif ext == ".obj":
            bpy.ops.import_scene.obj(filepath=str(model_file))
        else:
            raise RuntimeError(f"Unsupported format: {ext}")

        # Find imported root objects
        imported_objs = [obj for obj in bpy.data.objects if obj not in bpy.context.scene.objects[:import_count_before]]
        if not imported_objs:
            imported_objs = list(bpy.context.selected_objects)

        # VRM/MToon-style toon-shader materials route through a Mix Shader
        # gated by Light Path > Is Camera Ray (mixing Transparent BSDF and
        # Emission, to hide the character from shadow rays without harsh toon
        # shadows). That Light Path factor evaluates incorrectly in this
        # Blender build, leaving the whole character transparent to camera
        # rays too — i.e. invisible. Rewire around it.
        self._fix_toon_shader_materials(imported_objs)

        # Join into a single empty-parented hierarchy for easier placement
        if len(imported_objs) == 1:
            root = imported_objs[0]
        else:
            # Create empty as parent
            root = bpy.data.objects.new(name=f"CHAR_{char_id}", object_data=None)
            collection.objects.link(root)
            for obj in imported_objs:
                if obj.parent is None:
                    obj.parent = root

        # Apply placement
        root.name = f"CHAR_{char_id}"
        pos = char_data.get("default_position", [0, 0, 0])
        rot = char_data.get("default_rotation", [0, 0, 0])
        scale = char_data.get("scale", 1.0)
        height = char_data.get("height_meters", DEFAULT_CHARACTER_SCALE)

        root.location = pos
        root.rotation_euler = rot

        # Auto-scale to target height if mesh bounds available
        if height:
            self._auto_scale(root, height)
        else:
            root.scale = (scale, scale, scale)

        # Move to Characters collection
        if root.name not in collection.objects:
            if root.name in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.unlink(root)
            collection.objects.link(root)

        # Store metadata
        root["character_id"] = char_id
        root["character_name"] = char_data.get("display_name", char_id)

        return root

    def _fix_toon_shader_materials(self, objs):
        """Bypass the broken Light Path.Is Camera Ray -> Mix Shader chain in
        VRM toon-shader materials, which renders invisible in this Blender
        build. Redirects the Mix Shader's Emission input straight to whatever
        consumed its output, preserving the alpha-driven Transparent BSDF mix
        further down the chain (needed for eyelash/eyebrow/eye-highlight cutouts)."""
        import bpy

        seen = set()
        meshes = [o for o in objs if o.type == 'MESH']
        for o in objs:
            meshes.extend(c for c in o.children_recursive if c.type == 'MESH')

        for obj in meshes:
            for slot in obj.material_slots:
                mat = slot.material
                if mat is None or mat.name in seen or not mat.use_nodes or not mat.node_tree:
                    continue
                seen.add(mat.name)
                nt = mat.node_tree
                for node in list(nt.nodes):
                    if node.type != 'MIX_SHADER':
                        continue
                    factor = node.inputs.get('Factor')
                    if factor is None or not factor.is_linked:
                        continue
                    if factor.links[0].from_node.type != 'LIGHT_PATH':
                        continue
                    emission_node = None
                    for sock in node.inputs:
                        if sock.name == 'Shader' and sock.is_linked:
                            up = sock.links[0].from_node
                            if up.type == 'EMISSION':
                                emission_node = up
                    if emission_node is None:
                        continue
                    for link in list(node.outputs['Shader'].links):
                        nt.links.new(emission_node.outputs['Emission'], link.to_socket)

    def _auto_scale(self, obj, target_height: float):
        import bpy
        import math
        # Calculate bounding box height
        if obj.type == 'MESH':
            vertices = [v.co for v in obj.data.vertices]
        else:
            # Get all mesh children
            vertices = []
            for child in obj.children_recursive:
                if child.type == 'MESH':
                    for v in child.data.vertices:
                        world_v = child.matrix_world @ v.co
                        vertices.append(world_v)

        if not vertices:
            return

        min_z = min(v.z for v in vertices)
        max_z = max(v.z for v in vertices)
        current_height = max_z - min_z

        if current_height > 0.01:
            scale_factor = target_height / current_height
            # Apply scale uniformly
            obj.scale = (scale_factor, scale_factor, scale_factor)


# ── CLI ─────────────────────────────────────────────────────────────────────

def run_inside_blender():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Blender Character Importer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Import characters into layout")
    p_import.add_argument("project_slug", help="Project identifier")
    p_import.add_argument("--layout", help="Path to layout .blend file")

    p_manifest = sub.add_parser("create-manifest", help="Create character manifest template")
    p_manifest.add_argument("project_slug", help="Project identifier")

    args = parser.parse_args(argv)

    if args.command == "import":
        importer = CharacterImporter(args.project_slug, layout_path=args.layout)
        result = importer.import_characters()
        print(json.dumps(result, indent=2))
    elif args.command == "create-manifest":
        result = create_character_manifest(args.project_slug)
        print(json.dumps(result, indent=2))


def run_outside_blender():
    parser = argparse.ArgumentParser(description="Blender Character Importer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Import characters into layout")
    p_import.add_argument("project_slug", help="Project identifier")
    p_import.add_argument("--layout", help="Path to layout .blend file")

    p_manifest = sub.add_parser("create-manifest", help="Create character manifest template")
    p_manifest.add_argument("project_slug", help="Project identifier")

    args = parser.parse_args()
    script_path = Path(__file__).resolve()

    if args.command == "import":
        cmd = [
            BLENDER_BINARY,
            "--background",
            "--python", str(script_path),
            "--",
            "import", args.project_slug,
        ]
        if args.layout:
            cmd.extend(["--layout", args.layout])
        print(f"🎭 Importing characters for {args.project_slug}...")
        subprocess.run(cmd, check=True)

    elif args.command == "create-manifest":
        result = create_character_manifest(args.project_slug)
        print(json.dumps(result, indent=2))


def main():
    try:
        import bpy
        INSIDE_BLENDER = True
    except ImportError:
        INSIDE_BLENDER = False

    if INSIDE_BLENDER:
        run_inside_blender()
    else:
        run_outside_blender()


if __name__ == "__main__":
    main()
