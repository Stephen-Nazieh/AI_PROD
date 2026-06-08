#!/usr/bin/env python3
"""
auto_color_grader.py — Mood-Based Auto Color Grading via ffmpeg LUTs

Maps scene headings to emotional color grades, applies pre-built or
generated LUTs (Look-Up Tables) to rendered frames via ffmpeg.

Usage:
    python auto_color_grader.py init-luts
    python auto_color_grader.py grade <project_slug> [--shot SC001_SH001]
    python auto_color_grader.py grade <project_slug> --all-shots

Mood → LUT mapping:
    calm, peaceful     → soft_warm.cube
    academic, neutral  → clean_neutral.cube
    tense, suspense    → teal_orange.cube
    dark, urban        → cool_blue.cube
    upbeat, energetic  → vibrant_saturated.cube
    warm, intimate     → golden_hour.cube
"""

import argparse
import json
import os
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
LUT_LIBRARY = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "color-luts"
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# Scene heading → LUT mapping
LUT_RULES = {
    "night": ["dark", "cool_blue", "teal_orange"],
    "day": ["clean_neutral", "golden_hour", "soft_warm"],
    "classroom": ["clean_neutral", "soft_warm"],
    "office": ["cool_blue", "teal_orange"],
    "park": ["soft_warm", "golden_hour"],
    "city": ["cool_blue", "vibrant_saturated"],
    "home": ["soft_warm", "golden_hour"],
}


def detect_luts(heading: str) -> list[str]:
    """Select LUTs based on scene heading."""
    heading = heading.lower()
    luts = set()
    for keyword, lut_list in LUT_RULES.items():
        if keyword in heading:
            luts.update(lut_list)
    if not luts:
        luts = ["clean_neutral"]
    return list(luts)


def generate_lut(name: str, style: str) -> Path:
    """Generate a simple 3D LUT as a .cube file."""
    lut_path = LUT_LIBRARY / f"{name}.cube"
    lut_path.parent.mkdir(parents=True, exist_ok=True)
    
    size = 33  # 33x33x33 is standard
    
    # Pre-defined color transformations
    transforms = {
        "soft_warm": lambda r, g, b: (r**0.95, g**0.98, b**1.05),
        "cool_blue": lambda r, g, b: (r*0.95, g*0.98, b*1.08),
        "teal_orange": lambda r, g, b: (r*1.05 + 0.02, g*0.98, b*0.92),
        "vibrant_saturated": lambda r, g, b: (r**0.9, g**0.9, b**0.9),
        "golden_hour": lambda r, g, b: (r*1.08, g*1.02, b*0.92),
        "clean_neutral": lambda r, g, b: (r, g, b),
    }
    
    transform = transforms.get(style, transforms["clean_neutral"])
    
    lines = [
        f"TITLE \"{name}\"",
        f"LUT_3D_SIZE {size}",
        "",
    ]
    
    for b in range(size):
        for g in range(size):
            for r in range(size):
                rf, gf, bf = r / (size - 1), g / (size - 1), b / (size - 1)
                ro, go, bo = transform(rf, gf, bf)
                lines.append(f"{max(0, min(1, ro)):.6f} {max(0, min(1, go)):.6f} {max(0, min(1, bo)):.6f}")
    
    lut_path.write_text("\n".join(lines), encoding="utf-8")
    return lut_path


def init_luts() -> dict:
    """Create the LUT library with generated presets."""
    LUT_LIBRARY.mkdir(parents=True, exist_ok=True)
    
    moods = ["soft_warm", "cool_blue", "teal_orange", "vibrant_saturated", "golden_hour", "clean_neutral"]
    created = []
    for mood in moods:
        path = generate_lut(mood, mood)
        created.append(str(path))
    
    manifest = {
        "version": 1,
        "luts": {mood: str(LUT_LIBRARY / f"{mood}.cube") for mood in moods},
        "note": "Generated procedural LUTs. Replace with professional LUTs for production.",
    }
    manifest_path = LUT_LIBRARY / "lut_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    return {
        "status": "ok",
        "library_dir": str(LUT_LIBRARY),
        "luts_created": len(created),
        "luts": created,
    }


class ColorGrader:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.shot_list = _load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.renders_dir = self.project_dir / "04-raw_renders"
        self.graded_dir = self.project_dir / "04-raw_renders_graded"
        self.graded_dir.mkdir(parents=True, exist_ok=True)

    def grade(self, shot_id: str | None = None, all_shots: bool = False) -> dict:
        if not self.renders_dir.exists():
            return {"status": "error", "message": "No renders found"}
        
        shots = self.shot_list.get("shots", [])
        if shot_id:
            shots = [s for s in shots if s["shot_id"] == shot_id]
        if not all_shots and not shot_id:
            return {"status": "error", "message": "Specify --shot or --all-shots"}

        # Build lookup: shot_id → scene_heading
        scene_lookup = {s["scene_id"]: s.get("heading", "") for s in self.shot_list.get("scenes", [])}
        
        results = []
        for shot in shots:
            sid = shot["shot_id"]
            scene_id = shot.get("scene_id", "")
            heading = scene_lookup.get(scene_id, "")
            lut_names = detect_luts(heading)
            
            shot_render_dir = self.renders_dir / sid
            if not shot_render_dir.exists():
                continue
            
            pngs = sorted(shot_render_dir.glob("*.png"))
            if not pngs:
                continue
            
            # Apply first matching LUT
            applied = None
            for lut_name in lut_names:
                lut_path = LUT_LIBRARY / f"{lut_name}.cube"
                if lut_path.exists():
                    out_dir = self.graded_dir / sid
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / pngs[0].name
                    
                    try:
                        subprocess.run([
                            FFMPEG, "-y", "-i", str(pngs[0]),
                            "-vf", f"lut3d='{lut_path}'",
                            str(out_path),
                        ], check=True, capture_output=True, timeout=30)
                        applied = lut_name
                        break
                    except Exception as e:
                        pass
            
            if applied:
                results.append({
                    "shot_id": sid,
                    "status": "ok",
                    "heading": heading,
                    "lut": applied,
                    "input": str(pngs[0]),
                    "output": str(out_path),
                })
            else:
                results.append({
                    "shot_id": sid,
                    "status": "skipped",
                    "reason": "No matching LUT found",
                    "heading": heading,
                })

        return {
            "status": "ok",
            "project": self.project_slug,
            "graded_dir": str(self.graded_dir),
            "results": results,
        }


def main():
    parser = argparse.ArgumentParser(description="Auto Color Grader")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-luts", help="Generate default LUT library")
    p_grade = sub.add_parser("grade", help="Grade rendered frames")
    p_grade.add_argument("project_slug")
    p_grade.add_argument("--shot")
    p_grade.add_argument("--all-shots", action="store_true")

    args = parser.parse_args()

    if args.command == "init-luts":
        result = init_luts()
        print(json.dumps(result, indent=2))
    elif args.command == "grade":
        grader = ColorGrader(args.project_slug)
        result = grader.grade(shot_id=args.shot, all_shots=args.all_shots)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
