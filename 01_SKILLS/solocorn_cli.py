#!/usr/bin/env python3
"""
solocorn_cli.py — Unified CLI Entry Point

One command for everything. Instead of remembering 52 script names,
just use: solocorn <action> <project> [options]

Usage:
    solocorn init my_movie --title "My Title"
    solocorn render my_movie --all-shots
    solocorn pipeline my_movie --mode 2d
    solocorn status my_movie
    solocorn dashboard my_movie --port 8888
    solocorn test
    solocorn list-actions

This is a thin wrapper around the gateway actions.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(WORKSPACE_ROOT / "env" / "bin" / "python3")

# Action → (script, subcommand pattern)
QUICK_ACTIONS = {
    "init": ("init_project.py", "create {project} --title '{title}'"),
    "render": ("animation_2d_compositor.py", "composite {project} --all-shots"),
    "render-3d": ("blender_render_dispatcher.py", "render {project} --all-shots"),
    "dub": ("auto_dubbing_pipeline.py", "dub {project} --all-shots"),
    "music": ("logic_pro_scorer.py", "score {project} --all-scenes"),
    "sfx": ("sound_designer.py", "design {project} --all-scenes"),
    "storyboard": ("storyboard_generator.py", "generate {project}"),
    "characters": ("character_2d_generator.py", "create {project} protagonist --prompt 'student' --style anime"),
    "backgrounds": ("background_2d_generator.py", "generate {project} --all-scenes"),
    "color": ("advanced_color_grader.py", "grade {project} --all-shots"),
    "edit": ("creative_editor.py", "edit {project}"),
    "subtitles": ("subtitle_generator.py", "generate {project}"),
    "thumbnail": ("thumbnail_generator.py", "generate {project}"),
    "distribute": ("distribution_formatter.py", "batch {project}"),
    "pipeline": ("pipeline_orchestrator.py", "run {project} --mode {mode}"),
    "test": ("test_suite.py", "run"),
    "cache": ("build_cache.py", "stale {project}"),
    "dashboard": ("project_dashboard.py", "serve {project}"),
    "status": ("project_dashboard.py", "snapshot {project}"),
    "mocap": ("body_mocap.py", "batch {project} --video {video}"),
    "interpolate": ("frame_interpolator.py", "smooth {project} --all-shots"),
    "upscale": ("neural_upscaler.py", "upscale {project} --all-shots"),
    "quality": ("quality_gate.py", "check {project} --all-shots"),
    "episodes": ("episode_manager.py", "split {project}"),
    "recover": ("error_recovery.py", "status {project}"),
    "health": ("health_check.py", ""),
    "start": ("start_services.py", ""),
    "cleanup": ("asset_cleanup.py", "{project}"),
}


def run_action(action: str, project: str = "", **kwargs) -> dict:
    """Run a quick action."""
    if action not in QUICK_ACTIONS:
        return {"status": "error", "message": f"Unknown action: {action}. Run 'solocorn list-actions'"}
    
    script, pattern = QUICK_ACTIONS[action]
    script_path = WORKSPACE_ROOT / "01_SKILLS" / script
    
    args = pattern.format(project=project, **kwargs)
    cmd = f"{PYTHON} {script_path} {args}"
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=WORKSPACE_ROOT)
    
    # Try to parse JSON
    for line in reversed(result.stdout.strip().split("\n")):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    
    return {
        "status": "ok" if result.returncode == 0 else "error",
        "action": action,
        "stdout": result.stdout[:500],
        "stderr": result.stderr[:200] if result.stderr else "",
    }


def main():
    parser = argparse.ArgumentParser(
        prog="solocorn",
        description="Solocorn Studios Production CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  solocorn init my_movie --title "AP Stats Episode 1"
  solocorn pipeline my_movie --mode 2d
  solocorn render my_movie
  solocorn dashboard my_movie --port 8888
  solocorn status my_movie
  solocorn test
  solocorn health
  solocorn start
  solocorn stop
  solocorn cleanup my_movie --confirm
        """
    )
    
    parser.add_argument("action", choices=list(QUICK_ACTIONS.keys()) + ["list-actions", "stop"])
    parser.add_argument("project", nargs="?", default="")
    parser.add_argument("--title", default="My Movie")
    parser.add_argument("--mode", default="2d")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--video", default="")
    parser.add_argument("--shot", default="")
    parser.add_argument("--episode", default="")
    parser.add_argument("--platform", default="all")
    
    args = parser.parse_args()
    
    if args.action == "list-actions":
        print("Available actions:")
        for name in sorted(QUICK_ACTIONS.keys()):
            print(f"  {name:20s}")
        return
    
    if args.action == "test":
        result = run_action("test")
        print(json.dumps(result, indent=2))
        return
    
    if args.action == "health":
        script_path = WORKSPACE_ROOT / "01_SKILLS" / "health_check.py"
        result = subprocess.run([PYTHON, str(script_path)], cwd=WORKSPACE_ROOT)
        sys.exit(result.returncode)
    
    if args.action == "start":
        script_path = WORKSPACE_ROOT / "01_SKILLS" / "start_services.py"
        result = subprocess.run([PYTHON, str(script_path)], cwd=WORKSPACE_ROOT)
        sys.exit(result.returncode)
    
    if args.action == "stop":
        script_path = WORKSPACE_ROOT / "01_SKILLS" / "start_services.py"
        result = subprocess.run([PYTHON, str(script_path), "--stop"], cwd=WORKSPACE_ROOT)
        sys.exit(result.returncode)
    
    if args.action == "cleanup":
        script_path = WORKSPACE_ROOT / "01_SKILLS" / "asset_cleanup.py"
        result = subprocess.run([PYTHON, str(script_path), args.project, "--confirm"], cwd=WORKSPACE_ROOT)
        sys.exit(result.returncode)
    
    if not args.project:
        print("Error: project slug required for this action")
        sys.exit(1)
    
    result = run_action(
        args.action, args.project,
        title=args.title, mode=args.mode,
        video=args.video, shot=args.shot,
        episode=args.episode, platform=args.platform,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
