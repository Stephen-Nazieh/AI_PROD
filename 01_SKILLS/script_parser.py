#!/usr/bin/env python3
"""
script_parser.py — Screenplay Parser: Fountain + Markdown → Structured Scene Manifests

Supports two input formats:
  1. Fountain (.fountain) — Industry-standard plain text screenplay format
  2. Markdown (.md) — Custom Solocorn pedagogical script format

Outputs:
  - shot-list.json: Structured scene/shot breakdown with camera directions
  - scene-manifests/: Individual JSON manifests per scene for render dispatch

Usage:
    python script_parser.py parse --input screenplay.fountain --output-dir 05_PROJECTS/my-film/01-scripts/
    python script_parser.py parse --input lesson.md --format markdown --track ap_stats --output-dir 05_PROJECTS/my-film/01-scripts/
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class Shot:
    shot_id: str           # SC001_SH001
    scene_id: str          # SC001
    shot_number: int       # 1
    shot_type: str         # wide, medium, close_up, insert, aerial
    camera_movement: str   # static, pan, tilt, dolly, crane, handheld
    subject: str
    action: str
    dialogue: str
    duration_seconds: float
    notes: str


@dataclass
class Scene:
    scene_id: str
    scene_number: int
    heading: str           # INT. CLASSROOM - DAY
    description: str
    shots: list[Shot]


@dataclass
class TitlePage:
    title: str
    author: str
    date: str
    contact: str


@dataclass
class Screenplay:
    title_page: TitlePage
    scenes: list[Scene]


# ── Fountain Parser ─────────────────────────────────────────────────────────

class FountainParser:
    """Parse Fountain format screenplays into structured scenes and shots."""

    SCENE_HEADING_PATTERN = re.compile(r"^(INT|EXT|INT\.\/EXT|EST|I\/E)\.\s+", re.IGNORECASE)
    TRANSITION_PATTERN = re.compile(r"^>\s*(.+)$")
    CHARACTER_PATTERN = re.compile(r"^([A-Z][A-Z\s\.]+)\s*$")
    PARENTHETICAL_PATTERN = re.compile(r"^\((.+)\)$")
    CENTERED_PATTERN = re.compile(r"^>\s*(.+?)\s*<$")
    SHOT_NOTE_PATTERN = re.compile(r"\[shot:\s*(\w+)(?:\s+movement=(\w+))?\s*\]", re.IGNORECASE)

    def parse(self, text: str) -> Screenplay:
        lines = text.splitlines()

        # Parse title page (first block before first blank line)
        title_page = self._parse_title_page(lines)

        # Parse body
        scenes = self._parse_scenes(lines)

        return Screenplay(title_page=title_page, scenes=scenes)

    def _parse_title_page(self, lines: list[str]) -> TitlePage:
        title, author, date, contact = "", "", "", ""
        in_title_page = True

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if title:
                    break
                continue

            if ":" in stripped:
                key, val = stripped.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key in ("title", "title:"):
                    title = val
                elif key in ("author", "author:", "credit", "credit:"):
                    author = val
                elif key in ("date", "date:", "draft date", "draft date:"):
                    date = val
                elif key in ("contact", "contact:"):
                    contact = val

        return TitlePage(title=title, author=author, date=date, contact=contact)

    def _parse_scenes(self, lines: list[str]) -> list[Scene]:
        scenes = []
        current_scene = None
        current_shot = None
        in_dialogue = False
        dialogue_buffer = []
        action_buffer = []
        scene_number = 0

        for line in lines:
            stripped = line.strip()

            # Skip title page and blank lines
            if not stripped:
                if in_dialogue and dialogue_buffer:
                    if current_shot:
                        current_shot.dialogue = " ".join(dialogue_buffer)
                    dialogue_buffer = []
                    in_dialogue = False
                continue

            # Scene heading
            if self.SCENE_HEADING_PATTERN.match(stripped) or stripped.startswith("."):
                # Save previous scene
                if current_scene:
                    if current_shot:
                        current_scene.shots.append(current_shot)
                    scenes.append(current_scene)

                scene_number += 1
                heading = stripped.lstrip(".").strip()
                current_scene = Scene(
                    scene_id=f"SC{scene_number:03d}",
                    scene_number=scene_number,
                    heading=heading,
                    description="",
                    shots=[],
                )
                current_shot = None
                action_buffer = []
                continue

            if not current_scene:
                continue

            # Character name (dialogue)
            if self.CHARACTER_PATTERN.match(stripped) and not in_dialogue:
                in_dialogue = True
                dialogue_buffer = []
                continue

            # Parenthetical
            if self.PARENTHETICAL_PATTERN.match(stripped) and in_dialogue:
                continue

            # Transition
            if self.TRANSITION_PATTERN.match(stripped):
                continue

            # Dialogue line
            if in_dialogue:
                dialogue_buffer.append(stripped)
                continue

            # Action / shot notes
            action_buffer.append(stripped)

            # Detect shot notes in action
            shot_match = self.SHOT_NOTE_PATTERN.search(stripped)
            if shot_match:
                # Save previous shot
                if current_shot:
                    current_scene.shots.append(current_shot)

                shot_type = shot_match.group(1).lower()
                movement = (shot_match.group(2) or "static").lower()
                action_text = " ".join(action_buffer[:action_buffer.index(stripped) + 1])
                action_text = action_text.replace(shot_match.group(0), "").strip()

                current_shot = Shot(
                    shot_id=f"{current_scene.scene_id}_SH{len(current_scene.shots) + 1:03d}",
                    scene_id=current_scene.scene_id,
                    shot_number=len(current_scene.shots) + 1,
                    shot_type=shot_type,
                    camera_movement=movement,
                    subject="",
                    action=action_text,
                    dialogue="",
                    duration_seconds=0.0,
                    notes=stripped,
                )
                action_buffer = []

        # Save final scene
        if current_scene:
            if current_shot:
                current_scene.shots.append(current_shot)
            scenes.append(current_scene)

        # Auto-generate shots for scenes without explicit shot notes
        for scene in scenes:
            if not scene.shots:
                scene.shots.append(Shot(
                    shot_id=f"{scene.scene_id}_SH001",
                    scene_id=scene.scene_id,
                    shot_number=1,
                    shot_type="wide",
                    camera_movement="static",
                    subject="",
                    action=scene.heading,
                    dialogue="",
                    duration_seconds=0.0,
                    notes="Auto-generated wide shot",
                ))

        return scenes


# ── Markdown Parser (Legacy Solocorn Format) ────────────────────────────────

class MarkdownParser:
    """Parse custom Solocorn markdown scripts into scene manifests."""

    def parse(self, text: str, track_name: str = "default") -> list[dict]:
        lines = text.splitlines()
        scenes = []
        current_scene = {}
        is_parsing = False

        for line in lines:
            cleaned = line.strip()

            if cleaned.startswith("## SCENE:"):
                if current_scene:
                    scenes.append(current_scene)
                current_scene = {
                    "track_name": track_name,
                    "asset_name": cleaned.split("## SCENE:")[1].strip().lower().replace(" ", "_"),
                    "stage": "manim_render",
                    "quality_flag": "-pqh",  # upgraded from -ql to high quality
                }
                is_parsing = True
                continue

            if is_parsing and ":" in cleaned:
                key, val = cleaned.split(":", 1)
                key = key.strip().lower()
                val = val.strip()

                if key in ["scene_name", "stage", "quality_flag"]:
                    current_scene[key] = val
                elif key == "output_movie":
                    current_scene["output_movie"] = str(PROJECT_ROOT / val)
                elif key == "duration":
                    try:
                        current_scene["duration_seconds"] = float(val)
                    except ValueError:
                        current_scene["duration_seconds"] = 0.0

        if current_scene:
            scenes.append(current_scene)

        # Set default output paths
        for scene in scenes:
            if "output_movie" not in scene:
                scene["output_movie"] = str(
                    PROJECT_ROOT / "05_PROJECTS" / track_name / "05-renders" / "3d" / f"{scene['asset_name']}.mp4"
                )

        return scenes


# ── Shot List Generator ─────────────────────────────────────────────────────

class ShotListGenerator:
    """Generate shot-list.json from parsed screenplay."""

    def from_screenplay(self, screenplay: Screenplay, project_slug: str) -> dict:
        shots = []
        for scene in screenplay.scenes:
            for shot in scene.shots:
                shots.append({
                    "shot_id": shot.shot_id,
                    "scene_id": shot.scene_id,
                    "scene_heading": scene.heading,
                    "shot_number": shot.shot_number,
                    "shot_type": shot.shot_type,
                    "camera_movement": shot.camera_movement,
                    "subject": shot.subject,
                    "action": shot.action,
                    "dialogue": shot.dialogue,
                    "duration_seconds": shot.duration_seconds,
                    "notes": shot.notes,
                })

        return {
            "project_slug": project_slug,
            "title": screenplay.title_page.title,
            "author": screenplay.title_page.author,
            "scene_count": len(screenplay.scenes),
            "shot_count": len(shots),
            "scenes": [
                {
                    "scene_id": s.scene_id,
                    "scene_number": s.scene_number,
                    "heading": s.heading,
                    "description": s.description,
                    "shot_count": len(s.shots),
                }
                for s in screenplay.scenes
            ],
            "shots": shots,
        }


# ── Main Interface ──────────────────────────────────────────────────────────

class ScriptParser:
    def __init__(self):
        self.fountain = FountainParser()
        self.markdown = MarkdownParser()
        self.shot_list = ShotListGenerator()

    def parse_file(self, input_path: str, output_dir: str,
                   format_hint: str | None = None,
                   track_name: str = "default",
                   project_slug: str = "") -> dict:
        """
        Parse a script file and generate outputs.

        Returns:
            {
                "status": "ok",
                "format": "fountain" | "markdown",
                "shot_list_path": "...",
                "manifests_dir": "...",
                "scene_count": N,
                "shot_count": N,
            }
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not input_path.exists():
            return {"status": "error", "error": f"File not found: {input_path}"}

        text = input_path.read_text(encoding="utf-8")
        ext = input_path.suffix.lower()

        # Auto-detect format
        if format_hint:
            fmt = format_hint
        elif ext == ".fountain":
            fmt = "fountain"
        elif ext == ".md":
            fmt = "markdown"
        elif "INT." in text[:2000] or "EXT." in text[:2000]:
            fmt = "fountain"
        else:
            fmt = "markdown"

        if fmt == "fountain":
            screenplay = self.fountain.parse(text)
            shot_list = self.shot_list.from_screenplay(screenplay, project_slug or "untitled")

            # Write shot-list.json
            shot_list_path = output_dir / "shot-list.json"
            shot_list_path.write_text(json.dumps(shot_list, indent=2, ensure_ascii=False), encoding="utf-8")

            # Write scene manifests
            manifests_dir = output_dir / "scene-manifests"
            manifests_dir.mkdir(exist_ok=True)
            manifest_paths = []
            for scene in screenplay.scenes:
                manifest = {
                    "project_slug": project_slug,
                    "scene_id": scene.scene_id,
                    "scene_number": scene.scene_number,
                    "heading": scene.heading,
                    "shots": [asdict(s) for s in scene.shots],
                    "stage": "previs",  # default stage
                }
                path = manifests_dir / f"{scene.scene_id}.json"
                path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
                manifest_paths.append(str(path))

            return {
                "status": "ok",
                "format": "fountain",
                "shot_list_path": str(shot_list_path),
                "manifests_dir": str(manifests_dir),
                "manifest_paths": manifest_paths,
                "scene_count": len(screenplay.scenes),
                "shot_count": shot_list["shot_count"],
                "title": screenplay.title_page.title,
            }

        else:  # markdown
            scenes = self.markdown.parse(text, track_name)

            # Write legacy manifests
            manifests_dir = output_dir / "scene-manifests"
            manifests_dir.mkdir(exist_ok=True)
            manifest_paths = []
            for i, scene in enumerate(scenes, 1):
                manifest_path = manifests_dir / f"task_{track_name}_scene_{i}_{scene['asset_name']}.json"
                manifest_path.write_text(json.dumps(scene, indent=2), encoding="utf-8")
                manifest_paths.append(str(manifest_path))

            return {
                "status": "ok",
                "format": "markdown",
                "manifests_dir": str(manifests_dir),
                "manifest_paths": manifest_paths,
                "scene_count": len(scenes),
            }


def main() -> int:
    parser = argparse.ArgumentParser(description="Script Parser: Fountain / Markdown → Scene Manifests")
    parser.add_argument("--input", required=True, help="Input script file")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--format", choices=["fountain", "markdown", "auto"], default="auto",
                        help="Input format (auto-detect if omitted)")
    parser.add_argument("--track", default="default", help="Track name (for markdown format)")
    parser.add_argument("--project-slug", default="", help="Project slug (for fountain format)")
    args = parser.parse_args()

    fmt = None if args.format == "auto" else args.format
    parser_obj = ScriptParser()
    result = parser_obj.parse_file(
        args.input, args.output_dir, fmt, args.track, args.project_slug
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
