#!/usr/bin/env python3
"""
asset_acquisition.py — External Asset Import & Organization

Helps non-artists acquire and organize 3D assets from external sources.
Creates a structured asset library with auto-import manifests.

Usage:
    python asset_acquisition.py init-library
    python asset_acquisition.py register <category> <name> --path /path/to/file.vrm
    python asset_acquisition.py list
    python asset_acquisition.py import <project_slug> --category characters --name protagonist

Supported formats: vrm, fbx, glb, gltf, obj, blend, dae
"""

import argparse
import json
import shutil
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
ASSET_LIBRARY = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "external-assets"
SUPPORTED_FORMATS = {".vrm", ".fbx", ".glb", ".gltf", ".obj", ".blend", ".dae"}

CATEGORIES = ["characters", "environments", "props", "vehicles", "furniture", "nature", "architecture"]


def init_library() -> dict:
    ASSET_LIBRARY.mkdir(parents=True, exist_ok=True)
    for cat in CATEGORIES:
        (ASSET_LIBRARY / cat).mkdir(exist_ok=True)
    
    manifest = {
        "version": 1,
        "categories": {cat: {} for cat in CATEGORIES},
        "sources": {
            "VRoid Hub": "https://hub.vroid.com/ (free VRM characters)",
            "Mixamo": "https://www.mixamo.com/ (free rigged characters + animations)",
            "Sketchfab": "https://sketchfab.com/ (free/paid 3D models)",
            "BlenderKit": "https://www.blenderkit.com/ (Blender add-on with free assets)",
            "Poly Haven": "https://polyhaven.com/ (free HDRIs + 3D models + textures)",
            "Free3D": "https://free3d.com/ (free 3D models)",
            "CGTrader": "https://www.cgtrader.com/ (paid high-quality models)",
            "Quixel Megascans": "https://quixel.com/megascans (free with Unreal)",
            "NASA 3D": "https://nasa3d.arc.nasa.gov/ (free space/science assets)",
            "Smithsonian 3D": "https://3d.si.edu/ (free museum objects)",
        },
        "note": "Place downloaded files in category folders, then register them.",
    }
    (ASSET_LIBRARY / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "ok", "library_dir": str(ASSET_LIBRARY), "categories": CATEGORIES}


def register_asset(category: str, name: str, file_path: Path) -> dict:
    if category not in CATEGORIES:
        return {"status": "error", "message": f"Unknown category: {category}. Use: {CATEGORIES}"}
    
    if not file_path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}
    
    if file_path.suffix.lower() not in SUPPORTED_FORMATS:
        return {"status": "error", "message": f"Unsupported format: {file_path.suffix}. Use: {SUPPORTED_FORMATS}"}
    
    target_dir = ASSET_LIBRARY / category
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy with standardized name
    target_path = target_dir / f"{name}{file_path.suffix.lower()}"
    shutil.copy(str(file_path), str(target_path))
    
    # Update manifest
    manifest_path = ASSET_LIBRARY / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["categories"][category][name] = {
        "file": str(target_path),
        "format": file_path.suffix.lower(),
        "original_path": str(file_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    return {"status": "ok", "category": category, "name": name, "path": str(target_path)}


def list_assets() -> dict:
    manifest_path = ASSET_LIBRARY / "manifest.json"
    if not manifest_path.exists():
        return {"status": "error", "message": "Library not initialized. Run: init-library"}
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "status": "ok",
        "categories": {cat: list(items.keys()) for cat, items in manifest["categories"].items()},
        "sources": manifest.get("sources", {}),
    }


def import_to_project(project_slug: str, category: str, name: str) -> dict:
    manifest_path = ASSET_LIBRARY / "manifest.json"
    if not manifest_path.exists():
        return {"status": "error", "message": "Library not initialized"}
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asset = manifest["categories"].get(category, {}).get(name)
    if not asset:
        return {"status": "error", "message": f"Asset not found: {category}/{name}"}
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    asset_dir = project_dir / "05-assets" / category
    asset_dir.mkdir(parents=True, exist_ok=True)
    
    source = Path(asset["file"])
    target = asset_dir / f"{name}{source.suffix}"
    shutil.copy(str(source), str(target))
    
    # Update project manifest
    project_manifest_path = project_dir / "05-assets" / "asset_manifest.json"
    project_manifest = json.loads(project_manifest_path.read_text(encoding="utf-8")) if project_manifest_path.exists() else {"assets": {}}
    project_manifest["assets"][f"{category}/{name}"] = str(target)
    project_manifest_path.write_text(json.dumps(project_manifest, indent=2), encoding="utf-8")
    
    return {"status": "ok", "project": project_slug, "asset": f"{category}/{name}", "path": str(target)}


def main():
    parser = argparse.ArgumentParser(description="Asset Acquisition")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-library", help="Create asset library structure")

    p_reg = sub.add_parser("register", help="Register an external asset")
    p_reg.add_argument("category", choices=CATEGORIES)
    p_reg.add_argument("name")
    p_reg.add_argument("--path", required=True, type=Path)

    sub.add_parser("list", help="List all registered assets")

    p_imp = sub.add_parser("import", help="Import asset into project")
    p_imp.add_argument("project_slug")
    p_imp.add_argument("--category", required=True, choices=CATEGORIES)
    p_imp.add_argument("--name", required=True)

    args = parser.parse_args()

    if args.command == "init-library":
        print(json.dumps(init_library(), indent=2))
    elif args.command == "register":
        print(json.dumps(register_asset(args.category, args.name, args.path), indent=2))
    elif args.command == "list":
        print(json.dumps(list_assets(), indent=2))
    elif args.command == "import":
        print(json.dumps(import_to_project(args.project_slug, args.category, args.name), indent=2))


if __name__ == "__main__":
    main()
