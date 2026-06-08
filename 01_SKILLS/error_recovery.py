#!/usr/bin/env python3
"""
error_recovery.py — Resume Failed Pipeline Steps

Tracks pipeline execution state and allows resuming from failures.
Prevents re-running successful steps while retrying failed ones.

Usage:
    python error_recovery.py init <project_slug>
    python error_recovery.py run <project_slug> --step render
    python error_recovery.py status <project_slug>
    python error_recovery.py retry <project_slug> --step render
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

PIPELINE_STEPS = [
    "ingest",
    "generate_storyboard",
    "generate_characters",
    "generate_backgrounds",
    "generate_layout",
    "generate_dubbing",
    "generate_music",
    "generate_sound_design",
    "render",
    "composite",
    "color_grade",
    "generate_edl",
    "assemble",
    "distribute",
]


def get_state_path(project_slug: str) -> Path:
    return WORKSPACE_ROOT / "05_PROJECTS" / project_slug / ".pipeline_state.json"


def load_state(project_slug: str) -> dict:
    path = get_state_path(project_slug)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "steps": {}}


def save_state(project_slug: str, state: dict):
    get_state_path(project_slug).write_text(json.dumps(state, indent=2), encoding="utf-8")


def init_state(project_slug: str) -> dict:
    state = {"version": 1, "steps": {}}
    for step in PIPELINE_STEPS:
        state["steps"][step] = {"status": "pending", "timestamp": None, "attempts": 0, "error": None}
    save_state(project_slug, state)
    return {"status": "ok", "steps": len(PIPELINE_STEPS)}


def mark_step(project_slug: str, step: str, status: str, error: str = None) -> dict:
    state = load_state(project_slug)
    if step not in state["steps"]:
        return {"status": "error", "message": f"Unknown step: {step}"}
    
    state["steps"][step] = {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "attempts": state["steps"][step].get("attempts", 0) + 1,
        "error": error,
    }
    save_state(project_slug, state)
    return {"status": "ok", "step": step, "status": status}


def get_status(project_slug: str) -> dict:
    state = load_state(project_slug)
    steps = state.get("steps", {})
    
    pending = [s for s, d in steps.items() if d.get("status") == "pending"]
    running = [s for s, d in steps.items() if d.get("status") == "running"]
    completed = [s for s, d in steps.items() if d.get("status") == "completed"]
    failed = [s for s, d in steps.items() if d.get("status") == "failed"]
    
    total = len(steps)
    done = len(completed)
    
    return {
        "status": "ok",
        "project": project_slug,
        "total_steps": total,
        "completed": done,
        "failed": len(failed),
        "running": len(running),
        "pending": len(pending),
        "percent": round(done / max(total, 1) * 100),
        "next_steps": pending[:3] if pending else [],
        "failed_steps": failed,
        "steps": steps,
    }


def resume(project_slug: str) -> dict:
    """Get list of steps that need to be run."""
    state = load_state(project_slug)
    steps = state.get("steps", {})
    
    to_run = []
    for step in PIPELINE_STEPS:
        data = steps.get(step, {})
        if data.get("status") in ["pending", "failed"]:
            to_run.append(step)
    
    return {
        "status": "ok",
        "project": project_slug,
        "steps_to_run": to_run,
        "count": len(to_run),
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    p_init = sub.add_parser("init")
    p_init.add_argument("project_slug")
    
    p_run = sub.add_parser("run")
    p_run.add_argument("project_slug")
    p_run.add_argument("--step", required=True)
    
    p_status = sub.add_parser("status")
    p_status.add_argument("project_slug")
    
    p_resume = sub.add_parser("resume")
    p_resume.add_argument("project_slug")
    
    args = parser.parse_args()
    
    if args.cmd == "init":
        print(json.dumps(init_state(args.project_slug), indent=2))
    elif args.cmd == "run":
        print(json.dumps(mark_step(args.project_slug, args.step, "running"), indent=2))
    elif args.cmd == "status":
        print(json.dumps(get_status(args.project_slug), indent=2))
    elif args.cmd == "resume":
        print(json.dumps(resume(args.project_slug), indent=2))

if __name__ == "__main__":
    main()
