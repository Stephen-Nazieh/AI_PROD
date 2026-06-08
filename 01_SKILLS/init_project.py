#!/usr/bin/env python3
"""
init_project.py — Project Scaffolding & Template Generator

Creates a complete project directory structure with templates,
boilerplate configs, and example shot-list.json.

Usage:
    python init_project.py create <project_slug> --title "My Movie"
    python init_project.py template <project_slug> --type educational
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

PROJECT_TEMPLATE = {
    "01-scripts": ["shot-list.json", "screenplay.md", "director_notes.json"],
    "02-storyboards": [],
    "03-layout": [],
    "04-raw_renders": [],
    "05-assets": {
        "characters": [],
        "characters_2d": [],
        "environments": [],
        "environments_2d": [],
        "props": [],
        "textures": [],
    },
    "06-audio": {
        "dialogue": [],
        "music": [],
        "sound_design": [],
    },
    "07-editing": [],
    "08-subtitles": [],
    "09-deliver": {
        "masters": [],
        "web": [],
        "thumbnails": [],
    },
    "episodes": [],
}

EXAMPLE_SHOT_LIST = {
    "project": "",
    "scenes": [
        {
            "scene_id": "SC001",
            "heading": "INT. CLASSROOM - DAY",
            "description": "A typical statistics classroom with 20 students",
            "mood": "academic",
            "time_of_day": "day",
        }
    ],
    "shots": [
        {
            "shot_id": "SC001_SH001",
            "scene_id": "SC001",
            "shot_type": "wide",
            "camera_movement": "static",
            "duration_seconds": 5.0,
            "action": "Teacher writes on whiteboard",
            "dialogue": "",
            "characters": ["teacher"],
        },
        {
            "shot_id": "SC001_SH002",
            "scene_id": "SC001",
            "shot_type": "medium",
            "camera_movement": "static",
            "duration_seconds": 4.0,
            "action": "Student raises hand",
            "dialogue": "Can you explain the difference between mean and median?",
            "characters": ["student_01", "teacher"],
        },
        {
            "shot_id": "SC001_SH003",
            "scene_id": "SC001",
            "shot_type": "close_up",
            "camera_movement": "static",
            "duration_seconds": 3.0,
            "action": "Teacher smiles warmly",
            "dialogue": "Great question. Let's look at an example.",
            "characters": ["teacher"],
        },
    ],
}


def _resolve_run_dir(project_slug: str, unit: str | None) -> tuple[Path, str | None]:
    """
    Resolve where a production run is scaffolded.

    With a business unit, the run lives inside that unit's production/ folder
    (the canonical location, validated against 00_CORE/business_units.yaml).
    Without a unit, fall back to the legacy 05_PROJECTS/<run>/ location.
    """
    if unit:
        reg = WORKSPACE_ROOT / "00_CORE" / "business_units.yaml"
        try:
            import yaml
            units = (yaml.safe_load(reg.read_text(encoding="utf-8")) or {}).get("units", {})
        except Exception:
            units = {}
        if unit not in units:
            known = ", ".join(units) or "(registry unavailable)"
            return WORKSPACE_ROOT, f"Unknown business unit '{unit}'. Known units: {known}"
        folder = units[unit].get("folder", f"business_units/{unit}")
        return WORKSPACE_ROOT / folder / "production" / project_slug, None
    return WORKSPACE_ROOT / "05_PROJECTS" / project_slug, None  # legacy fallback


def create_project(project_slug: str, title: str, description: str = "",
                   unit: str | None = None) -> dict:
    project_dir, err = _resolve_run_dir(project_slug, unit)
    if err:
        return {"status": "error", "message": err}

    if project_dir.exists():
        return {"status": "error", "message": f"Run already exists: {project_dir}"}
    
    # Create directories
    for path_str, contents in PROJECT_TEMPLATE.items():
        p = project_dir / path_str
        if isinstance(contents, list):
            p.mkdir(parents=True, exist_ok=True)
        else:
            for sub in contents:
                (p / sub).mkdir(parents=True, exist_ok=True)
    
    # Create shot-list template
    shot_list = EXAMPLE_SHOT_LIST.copy()
    shot_list["project"] = project_slug
    (project_dir / "01-scripts" / "shot-list.json").write_text(
        json.dumps(shot_list, indent=2), encoding="utf-8")
    
    # Create screenplay template
    screenplay = f"""# {title}

## FADE IN:

### SCENE 1: INT. CLASSROOM - DAY

A bright, modern classroom. STUDENTS sit at desks arranged in a U-shape. The TEACHER stands at the whiteboard.

TEACHER
Welcome to AP Statistics. Today we're going to understand why the median sometimes tells a better story than the mean.

A STUDENT raises their hand.

STUDENT
Can you explain the difference?

TEACHER
(smiling)
Great question. Let's look at an example...

## FADE OUT.
"""
    (project_dir / "01-scripts" / "screenplay.md").write_text(screenplay, encoding="utf-8")
    
    # Create character manifest template
    char_manifest = {
        "characters": [
            {"name": "teacher", "type": "main", "voice": "af_sarah", "format": "vrm"},
            {"name": "student_01", "type": "supporting", "voice": "af_bella", "format": "vrm"},
        ]
    }
    (project_dir / "05-assets" / "character_manifest.json").write_text(
        json.dumps(char_manifest, indent=2), encoding="utf-8")
    
    # Create project config
    config = {
        "project": project_slug,
        "business_unit": unit,
        "title": title,
        "description": description,
        "fps": 24,
        "resolution": {"width": 1920, "height": 1080},
        "style": "anime",
        "pipeline": "2d",
        "created": str(datetime.now()),
    }
    (project_dir / "project_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8")
    
    return {
        "status": "ok",
        "project": project_slug,
        "title": title,
        "directory": str(project_dir),
        "message": f"Project '{title}' created. Edit 01-scripts/shot-list.json to customize.",
    }


def main():
    from datetime import datetime
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create")
    p.add_argument("project_slug", help="Run/episode slug")
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--unit", default=None,
                   help="Business unit slug (see 00_CORE/business_units.yaml). "
                        "Places the run in business_units/<unit>/production/<slug>/. "
                        "Omit only for legacy 05_PROJECTS/ placement.")
    args = parser.parse_args()
    if args.cmd == "create":
        print(json.dumps(create_project(args.project_slug, args.title, args.description, args.unit), indent=2))

if __name__ == "__main__":
    main()
