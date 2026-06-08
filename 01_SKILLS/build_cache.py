#!/usr/bin/env python3
"""
build_cache.py — Incremental Build Cache System

Tracks shot hashes to avoid re-rendering unchanged shots.
Detects changes to: shot-list, layout, characters, dialogue, audio.

Usage:
    python build_cache.py init <project_slug>
    python build_cache.py check <project_slug> --shot SC001_SH001
    python build_cache.py update <project_slug> --shot SC001_SH001
    python build_cache.py stale <project_slug>
"""

import argparse
import hashlib
import json
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def compute_shot_hash(project_slug: str, shot_id: str) -> str:
    """Compute comprehensive hash of all inputs affecting a shot."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    
    hasher = hashlib.sha256()
    
    # Hash shot-list.json
    shot_list_path = project_dir / "01-scripts" / "shot-list.json"
    if shot_list_path.exists():
        hasher.update(shot_list_path.read_bytes())
    
    # Hash layout file
    layout_path = project_dir / "03-layout" / "layout.blend"
    if layout_path.exists():
        hasher.update(layout_path.read_bytes())
    
    # Hash character manifests
    char_manifest = project_dir / "05-assets" / "character_manifest.json"
    if char_manifest.exists():
        hasher.update(char_manifest.read_bytes())
    
    # Hash dialogue audio
    audio_path = project_dir / "06-audio" / "dialogue" / f"{shot_id}.wav"
    if audio_path.exists():
        hasher.update(audio_path.read_bytes())
    
    # Hash director notes
    notes_path = project_dir / "01-scripts" / "director_notes.json"
    if notes_path.exists():
        hasher.update(notes_path.read_bytes())
    
    return hasher.hexdigest()[:32]


def get_cache_path(project_slug: str) -> Path:
    return WORKSPACE_ROOT / "05_PROJECTS" / project_slug / ".build_cache.json"


def load_cache(project_slug: str) -> dict:
    cache_path = get_cache_path(project_slug)
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    return {"version": 1, "shots": {}}


def save_cache(project_slug: str, cache: dict):
    cache_path = get_cache_path(project_slug)
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def init_cache(project_slug: str) -> dict:
    cache = {"version": 1, "shots": {}}
    save_cache(project_slug, cache)
    return {"status": "ok", "message": "Cache initialized"}


def check_shot(project_slug: str, shot_id: str) -> dict:
    cache = load_cache(project_slug)
    current_hash = compute_shot_hash(project_slug, shot_id)
    cached = cache["shots"].get(shot_id, {})
    
    if not cached:
        return {"status": "stale", "shot_id": shot_id, "reason": "not_cached"}
    
    if cached.get("hash") != current_hash:
        return {
            "status": "stale",
            "shot_id": shot_id,
            "reason": "inputs_changed",
            "old_hash": cached.get("hash"),
            "new_hash": current_hash,
        }
    
    # Check if output exists
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    output_dir = project_dir / "04-raw_renders" / shot_id
    has_output = output_dir.exists() and any(output_dir.rglob("*.png"))
    
    if not has_output:
        return {"status": "stale", "shot_id": shot_id, "reason": "output_missing"}
    
    return {
        "status": "fresh",
        "shot_id": shot_id,
        "hash": current_hash,
        "last_rendered": cached.get("timestamp"),
    }


def update_shot(project_slug: str, shot_id: str) -> dict:
    cache = load_cache(project_slug)
    current_hash = compute_shot_hash(project_slug, shot_id)
    
    from datetime import datetime
    cache["shots"][shot_id] = {
        "hash": current_hash,
        "timestamp": datetime.now().isoformat(),
    }
    save_cache(project_slug, cache)
    
    return {"status": "ok", "shot_id": shot_id, "hash": current_hash}


def list_stale(project_slug: str) -> dict:
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    shot_list = json.loads((project_dir / "01-scripts" / "shot-list.json").read_text(encoding="utf-8"))
    
    stale = []
    fresh = []
    
    for shot in shot_list.get("shots", []):
        result = check_shot(project_slug, shot["shot_id"])
        if result["status"] == "stale":
            stale.append(result)
        else:
            fresh.append(result)
    
    return {
        "status": "ok",
        "total_shots": len(shot_list.get("shots", [])),
        "stale": len(stale),
        "fresh": len(fresh),
        "stale_shots": [s["shot_id"] for s in stale],
        "fresh_shots": [f["shot_id"] for f in fresh],
    }


def main():
    parser = argparse.ArgumentParser(description="Build Cache")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize cache")
    p_init.add_argument("project_slug")

    p_check = sub.add_parser("check", help="Check if shot is up to date")
    p_check.add_argument("project_slug")
    p_check.add_argument("--shot", required=True)

    p_update = sub.add_parser("update", help="Update cache after render")
    p_update.add_argument("project_slug")
    p_update.add_argument("--shot", required=True)

    p_stale = sub.add_parser("stale", help="List all stale shots")
    p_stale.add_argument("project_slug")

    args = parser.parse_args()

    if args.command == "init":
        print(json.dumps(init_cache(args.project_slug), indent=2))
    elif args.command == "check":
        print(json.dumps(check_shot(args.project_slug, args.shot), indent=2))
    elif args.command == "update":
        print(json.dumps(update_shot(args.project_slug, args.shot), indent=2))
    elif args.command == "stale":
        print(json.dumps(list_stale(args.project_slug), indent=2))


if __name__ == "__main__":
    main()
