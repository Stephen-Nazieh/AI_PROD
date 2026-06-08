#!/usr/bin/env python3
"""
demo_project.py — Scaffold a Minimal Demo Project for Integration Testing

Creates a 2-shot AP Statistics mini-episode with realistic screenplay,
shot list, and character definitions. Useful for quick end-to-end
pipeline validation without waiting for a full 60-minute movie.

Usage:
    python3 demo_project.py create
    python3 demo_project.py create --run-pipeline --mode 2d
    python3 demo_project.py create --run-pipeline --mode 2d --parallel
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(WORKSPACE_ROOT / "env" / "bin" / "python3")
DEMO_SLUG = "ap_stats_demo"

SCREENPLAY = """# AP Statistics Demo — Understanding the Squeeze Theorem

## Scene 1: The Classroom

INT. CLASSROOM - DAY

PROFESSOR AVA stands at the whiteboard, marker in hand. The classroom is bright, morning light streaming through tall windows.

PROFESSOR AVA
Today we're going to understand one of the most elegant ideas in calculus: the Squeeze Theorem.

She draws three curves on the board — two outer curves squeezing a middle curve toward a single point.

PROFESSOR AVA (CONT'D)
Imagine you're at a concert, squeezed between two very enthusiastic fans. Wherever they go, you go. If they both end up at the front row... guess where you end up?

STUDENT (O.S.)
The front row?

PROFESSOR AVA
Exactly. And that's precisely what the Squeeze Theorem says about functions.

She writes the formal statement on the board, then turns back to the class with a warm smile.

PROFESSOR AVA (CONT'D)
If g(x) ≤ f(x) ≤ h(x) near a point a, and both g and h approach L as x approaches a... then f must also approach L.

The students nod, beginning to understand.

FADE OUT.
"""

SHOT_LIST = {
    "project_slug": DEMO_SLUG,
    "title": "AP Statistics Demo — The Squeeze Theorem",
    "total_scenes": 1,
    "total_shots": 2,
    "shots": [
        {
            "shot_id": "S01_SH01",
            "scene_number": 1,
            "scene_heading": "INT. CLASSROOM - DAY",
            "shot_number": 1,
            "shot_type": "wide",
            "camera_movement": "static",
            "subject": "Professor Ava",
            "action": "stands at the whiteboard drawing three curves",
            "dialogue": "Today we're going to understand one of the most elegant ideas in calculus: the Squeeze Theorem.",
            "notes": "Bright morning light, tall windows visible. Establishing shot showing the full classroom.",
            "duration_sec": 8
        },
        {
            "shot_id": "S01_SH02",
            "scene_number": 1,
            "scene_heading": "INT. CLASSROOM - DAY",
            "shot_number": 2,
            "shot_type": "close_up",
            "camera_movement": "static",
            "subject": "Professor Ava",
            "action": "writes the formal Squeeze Theorem statement on the board",
            "dialogue": "If g(x) ≤ f(x) ≤ h(x) near a point a, and both g and h approach L as x approaches a... then f must also approach L.",
            "notes": "Tight framing on the whiteboard and Professor Ava's face. Warm, encouraging expression.",
            "duration_sec": 12
        }
    ]
}

CHARACTER_LOOKS = {
    "Professor Ava": {
        "description": "Warm, approachable female professor in her 40s with shoulder-length dark hair, wearing a navy blazer over a cream blouse. Expressive eyes, kind smile. Professional but not formal.",
        "age": "40s",
        "gender": "female",
        "style_reference": "anime"
    }
}


def scaffold_demo() -> dict:
    """Create the demo project with all necessary files."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / DEMO_SLUG
    scripts_dir = project_dir / "01-scripts"
    
    # Init project first
    init_script = WORKSPACE_ROOT / "01_SKILLS" / "init_project.py"
    result = subprocess.run(
        [PYTHON, str(init_script), "create", DEMO_SLUG, "--title", "AP Stats Demo"],
        capture_output=True, text=True, timeout=30, cwd=WORKSPACE_ROOT,
    )
    if result.returncode != 0 and "already exists" not in result.stderr:
        return {"status": "error", "message": f"init_project failed: {result.stderr[:200]}"}
    
    # Write screenplay
    (scripts_dir / "screenplay.md").write_text(SCREENPLAY, encoding="utf-8")
    
    # Write shot list
    (scripts_dir / "shot-list.json").write_text(json.dumps(SHOT_LIST, indent=2), encoding="utf-8")
    
    # Write character looks
    (scripts_dir / "character_looks.json").write_text(json.dumps(CHARACTER_LOOKS, indent=2), encoding="utf-8")
    
    return {
        "status": "ok",
        "project": DEMO_SLUG,
        "project_dir": str(project_dir),
        "shots": len(SHOT_LIST["shots"]),
        "message": "Demo project scaffolded with 2 shots and 1 character.",
    }


def run_pipeline(mode: str = "2d", parallel: bool = False, dry_run: bool = False) -> dict:
    """Run the pipeline on the demo project."""
    orch = WORKSPACE_ROOT / "01_SKILLS" / "pipeline_orchestrator.py"
    cmd = [PYTHON, str(orch), "run", DEMO_SLUG, "--mode", mode]
    if parallel:
        cmd.append("--parallel")
    if dry_run:
        cmd.append("--dry-run")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=WORKSPACE_ROOT)
    return {
        "status": "ok" if result.returncode == 0 else "error",
        "returncode": result.returncode,
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-200:] if result.stderr else "",
    }


def main():
    parser = argparse.ArgumentParser(description="Demo Project Scaffolder")
    parser.add_argument("create")
    parser.add_argument("--run-pipeline", action="store_true")
    parser.add_argument("--mode", default="2d")
    parser.add_argument("--parallel", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    print("🎬 Scaffolding demo project...")
    result = scaffold_demo()
    print(json.dumps(result, indent=2))
    
    if args.run_pipeline and result["status"] == "ok":
        print(f"\n🚀 Running pipeline (mode={args.mode}, parallel={args.parallel}, dry_run={args.dry_run})...")
        pipeline_result = run_pipeline(args.mode, args.parallel, args.dry_run)
        print(json.dumps({k: v for k, v in pipeline_result.items() if k not in ("stdout", "stderr")}, indent=2))
        if pipeline_result.get("stdout"):
            print("\n--- stdout tail ---")
            print(pipeline_result["stdout"])
        if pipeline_result.get("stderr"):
            print("\n--- stderr ---")
            print(pipeline_result["stderr"])


if __name__ == "__main__":
    main()
