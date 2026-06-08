#!/usr/bin/env python3
"""
asset_manager.py — Asset Dependency Graph, Versioning & Cross-Project Reuse

Tracks assets across projects with:
  - Dependency graphs (shot A needs render from shot B)
  - Versioning (scene_01_v001.blend → scene_01_v002.blend)
  - Missing asset detection before render dispatch
  - Checksum validation
  - Cross-project asset reuse via symlinks

Usage:
    from asset_manager import AssetManager
    am = AssetManager()
    am.register_asset("ap-stats-movie", "SC001", "/path/to/scene.blend", "blender_scene")
    am.add_dependency("ap-stats-movie", "SC002", "SC001")  # SC002 needs SC001
    am.check_ready("ap-stats-movie", "SC002")  # Returns True if all deps exist
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "08_RENDER_FARM" / "asset_registry.db"
SHARED_ASSETS = PROJECT_ROOT / "06_SHARED_ASSETS"


class AssetManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    checksum TEXT,
                    size_bytes INTEGER,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(project_id, shot_id, asset_type, version)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dependencies (
                    dependency_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    depends_on_shot_id TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(project_id, shot_id, depends_on_shot_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    title TEXT,
                    status TEXT DEFAULT 'active',
                    config_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    def register_project(self, project_id: str, title: str,
                         config: dict | None = None) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO projects (project_id, title, config_json)
                VALUES (?, ?, ?)
            """, (project_id, title, json.dumps(config or {})))
            conn.commit()

    def register_asset(self, project_id: str, shot_id: str, file_path: str,
                       asset_type: str, version: int | None = None) -> dict:
        """Register or update an asset. Auto-increments version if not specified."""
        p = Path(file_path)
        if not p.exists():
            return {"status": "error", "error": f"File not found: {p}"}

        checksum = self._compute_checksum(p)
        size = p.stat().st_size

        with self._connect() as conn:
            if version is None:
                row = conn.execute("""
                    SELECT MAX(version) as max_ver FROM assets
                    WHERE project_id = ? AND shot_id = ? AND asset_type = ?
                """, (project_id, shot_id, asset_type)).fetchone()
                version = (row["max_ver"] or 0) + 1

            conn.execute("""
                INSERT INTO assets
                (project_id, shot_id, asset_type, file_path, version, checksum, size_bytes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(project_id, shot_id, asset_type, version) DO UPDATE SET
                    file_path = excluded.file_path,
                    checksum = excluded.checksum,
                    size_bytes = excluded.size_bytes,
                    updated_at = datetime('now')
            """, (project_id, shot_id, asset_type, str(p.resolve()), version, checksum, size))
            conn.commit()

            return {
                "status": "ok",
                "project_id": project_id,
                "shot_id": shot_id,
                "asset_type": asset_type,
                "version": version,
                "checksum": checksum,
                "size_bytes": size,
            }

    def add_dependency(self, project_id: str, shot_id: str,
                       depends_on_shot_id: str) -> dict:
        """Record that shot_id depends on depends_on_shot_id."""
        with self._connect() as conn:
            try:
                conn.execute("""
                    INSERT INTO dependencies (project_id, shot_id, depends_on_shot_id)
                    VALUES (?, ?, ?)
                """, (project_id, shot_id, depends_on_shot_id))
                conn.commit()
                return {"status": "ok", "message": f"{shot_id} now depends on {depends_on_shot_id}"}
            except sqlite3.IntegrityError:
                return {"status": "ok", "message": "Dependency already exists"}

    def check_ready(self, project_id: str, shot_id: str) -> dict:
        """Check if all dependencies for a shot are satisfied (assets exist and valid)."""
        with self._connect() as conn:
            deps = conn.execute("""
                SELECT depends_on_shot_id FROM dependencies
                WHERE project_id = ? AND shot_id = ?
            """, (project_id, shot_id)).fetchall()

            if not deps:
                return {"status": "ok", "ready": True, "missing": []}

            missing = []
            for dep in deps:
                dep_shot = dep["depends_on_shot_id"]
                asset = conn.execute("""
                    SELECT file_path, checksum FROM assets
                    WHERE project_id = ? AND shot_id = ?
                    ORDER BY version DESC LIMIT 1
                """, (project_id, dep_shot)).fetchone()

                if not asset:
                    missing.append({"shot": dep_shot, "reason": "no_asset_registered"})
                    continue

                p = Path(asset["file_path"])
                if not p.exists():
                    missing.append({"shot": dep_shot, "reason": "file_missing"})
                    continue

                current_checksum = self._compute_checksum(p)
                if current_checksum != asset["checksum"]:
                    missing.append({"shot": dep_shot, "reason": "checksum_mismatch"})

            return {
                "status": "ok",
                "ready": len(missing) == 0,
                "missing": missing,
            }

    def get_asset(self, project_id: str, shot_id: str,
                  asset_type: str | None = None) -> dict | None:
        """Get the latest version of an asset."""
        with self._connect() as conn:
            if asset_type:
                row = conn.execute("""
                    SELECT * FROM assets
                    WHERE project_id = ? AND shot_id = ? AND asset_type = ?
                    ORDER BY version DESC LIMIT 1
                """, (project_id, shot_id, asset_type)).fetchone()
            else:
                row = conn.execute("""
                    SELECT * FROM assets
                    WHERE project_id = ? AND shot_id = ?
                    ORDER BY version DESC LIMIT 1
                """, (project_id, shot_id)).fetchone()

            if not row:
                return None
            return dict(row)

    def link_shared_asset(self, project_id: str, shot_id: str,
                          shared_asset_name: str, asset_type: str) -> dict:
        """Create a symlink from a shared asset into a project."""
        source = SHARED_ASSETS / shared_asset_name
        if not source.exists():
            return {"status": "error", "error": f"Shared asset not found: {source}"}

        project_dir = PROJECT_ROOT / "05_PROJECTS" / project_id / "04-assets"
        target_dir = project_dir / asset_type
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name

        if target.exists() or target.is_symlink():
            target.unlink()

        try:
            target.symlink_to(source.resolve())
            return self.register_asset(project_id, shot_id, str(target), asset_type, version=0)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def list_assets(self, project_id: str | None = None,
                    shot_id: str | None = None) -> list[dict]:
        with self._connect() as conn:
            query = "SELECT * FROM assets WHERE 1=1"
            params = []
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            if shot_id:
                query += " AND shot_id = ?"
                params.append(shot_id)
            query += " ORDER BY project_id, shot_id, asset_type, version DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def _compute_checksum(self, path: Path) -> str:
        """Compute SHA-256 checksum of a file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]


if __name__ == "__main__":
    import sys
    am = AssetManager()
    am.register_project("test-project", "Test Project")
    result = am.register_asset("test-project", "SC001", "/tmp/test_blender_cube.blend", "blender_scene")
    print(json.dumps(result, indent=2))
