#!/usr/bin/env python3
"""
asset_cleanup.py — Purge Temporary and Cache Files

Cleans up render caches, temporary frames, and old log files
to reclaim disk space without touching source assets or deliverables.

Usage:
    python3 asset_cleanup.py <project_slug> --dry-run
    python3 asset_cleanup.py <project_slug> --confirm
    python3 asset_cleanup.py all --confirm
"""

import argparse
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
LOG_RETENTION_DAYS = 7


def get_size(path: Path) -> int:
    """Return total size in bytes for a file or directory."""
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def format_size(bytes_val: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def cleanup_project(project_slug: str, dry_run: bool = True) -> dict:
    """Clean up temporary files for a project."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    if not project_dir.exists():
        return {"status": "error", "message": f"Project not found: {project_slug}"}
    
    targets = []
    total_reclaimable = 0
    
    # 1. Raw render frames (keep smooth/graded, delete raw if smooth exists)
    renders_dir = project_dir / "04-raw_renders"
    if renders_dir.exists():
        for shot_dir in renders_dir.iterdir():
            if not shot_dir.is_dir():
                continue
            raw_frames = shot_dir / "2d_frames"
            smooth_frames = shot_dir / "2d_frames_smooth"
            if raw_frames.exists() and smooth_frames.exists():
                size = get_size(raw_frames)
                targets.append({"path": raw_frames, "reason": "raw frames (smooth exists)", "size": size})
                total_reclaimable += size
    
    # 2. Old pipeline logs
    logs_dir = WORKSPACE_ROOT / "logs"
    if logs_dir.exists():
        cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        for log_file in logs_dir.glob("pipeline_*.jsonl"):
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                size = log_file.stat().st_size
                targets.append({"path": log_file, "reason": f"old log ({mtime.date()})", "size": size})
                total_reclaimable += size
    
    # 3. ComfyUI temp outputs in project (not registered assets)
    comfy_temp = project_dir / "02-storyboards" / "temp"
    if comfy_temp.exists():
        size = get_size(comfy_temp)
        targets.append({"path": comfy_temp, "reason": "ComfyUI temp files", "size": size})
        total_reclaimable += size
    
    # 4. __pycache__ in project
    for pycache in project_dir.rglob("__pycache__"):
        size = get_size(pycache)
        targets.append({"path": pycache, "reason": "Python cache", "size": size})
        total_reclaimable += size
    
    if not targets:
        return {"status": "ok", "project": project_slug, "reclaimed": "0 B", "items": 0}
    
    if dry_run:
        return {
            "status": "dry_run",
            "project": project_slug,
            "reclaimable": format_size(total_reclaimable),
            "items": len(targets),
            "targets": [{"path": str(t["path"]), "reason": t["reason"], "size": format_size(t["size"])} for t in targets],
        }
    
    # Execute cleanup
    deleted = 0
    errors = []
    for t in targets:
        try:
            if t["path"].is_file():
                t["path"].unlink()
            else:
                shutil.rmtree(t["path"])
            deleted += 1
        except Exception as e:
            errors.append(f"{t['path']}: {e}")
    
    return {
        "status": "ok",
        "project": project_slug,
        "reclaimed": format_size(total_reclaimable),
        "deleted": deleted,
        "errors": errors,
    }


def cleanup_all_projects(dry_run: bool = True) -> dict:
    """Clean up all projects."""
    projects_dir = WORKSPACE_ROOT / "05_PROJECTS"
    if not projects_dir.exists():
        return {"status": "error", "message": "No projects directory"}
    
    results = []
    total_reclaimed = 0
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            r = cleanup_project(project_dir.name, dry_run)
            results.append(r)
            if r["status"] == "ok":
                # Parse reclaimed size
                val = r.get("reclaimed", "0 B").replace(" B", "").replace(" KB", "").replace(" MB", "").replace(" GB", "")
                try:
                    total_reclaimed += float(val)
                except ValueError:
                    pass
    
    return {
        "status": "ok" if not dry_run else "dry_run",
        "projects": len(results),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Asset Cleanup")
    parser.add_argument("project_slug", help="Project to clean, or 'all'")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be deleted")
    parser.add_argument("--confirm", action="store_true", help="Actually delete files")
    args = parser.parse_args()
    
    dry_run = not args.confirm
    
    if args.project_slug.lower() == "all":
        result = cleanup_all_projects(dry_run)
    else:
        result = cleanup_project(args.project_slug, dry_run)
    
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
