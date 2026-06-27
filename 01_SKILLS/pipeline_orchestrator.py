#!/usr/bin/env python3
"""
pipeline_orchestrator.py — One-Command Full Pipeline Execution

Runs the entire 2D (or 3D) pipeline from screenplay to delivered MP4
with dependency tracking, parallel execution, structured logging, and progress reporting.

Usage:
    python pipeline_orchestrator.py run <project_slug> --mode 2d
    python pipeline_orchestrator.py run <project_slug> --mode 3d
    python pipeline_orchestrator.py run <project_slug> --mode 2d --from render
    python pipeline_orchestrator.py run <project_slug> --mode 2d --parallel --jobs 4
    python pipeline_orchestrator.py dry-run <project_slug> --mode 3d
    python pipeline_orchestrator.py list --mode 3d

Pipeline DAG (2D):
    init → storyboard → characters → backgrounds → dubbing → music → sfx
    → composite → color → subtitles → thumbnails → assemble → distribute

Pipeline DAG (3D):
    init → storyboard → {sets, characters} → layout → import_characters
    → {keyframes, geo_animation, facial_animation} + {dubbing, music, sound_design}
    → render → {interpolate, color_grade, subtitles, thumbnails} → assemble → distribute
"""

import argparse
import concurrent.futures
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(WORKSPACE_ROOT / "env" / "bin" / "python3")
LOG_DIR = WORKSPACE_ROOT / "logs"

# Pipeline definition: step → (script, args_template, dependencies)
PIPELINE_2D = {
    "init": {
        "script": "init_project.py",
        "args": "create {project} --title '{title}'",
        "deps": [],
        "skippable": True,
    },
    "storyboard": {
        "script": "storyboard_generator.py",
        "args": "generate {project}",
        "deps": ["init"],
        "skippable": True,
        "comfyui": True,
    },
    "characters": {
        "script": "character_2d_generator.py",
        "args": "create {project} protagonist --prompt 'a student character' --style anime",
        "deps": ["init"],
        "skippable": True,
        "comfyui": True,
    },
    "backgrounds": {
        "script": "background_2d_generator.py",
        "args": "generate {project} --all-scenes --style anime",
        "deps": ["init"],
        "skippable": True,
        "comfyui": True,
    },
    "dubbing": {
        "script": "auto_dubbing_pipeline.py",
        "args": "dub {project} --all-shots --engine kokoro",
        "deps": ["init"],
        "skippable": True,
    },
    "music": {
        "script": "logic_pro_scorer.py",
        "args": "score {project} --all-scenes",
        "deps": ["init"],
        "skippable": True,
    },
    "sound_design": {
        "script": "sound_designer.py",
        "args": "design {project} --all-scenes",
        "deps": ["init"],
        "skippable": True,
    },
    "composite": {
        "script": "animation_2d_compositor.py",
        "args": "composite {project} --all-shots",
        "deps": ["characters", "backgrounds", "dubbing"],
        "skippable": False,
    },
    "interpolate": {
        "script": "frame_interpolator.py",
        "args": "smooth {project} --all-shots --factor 2",
        "deps": ["composite"],
        "skippable": True,
    },
    "color_grade": {
        "script": "advanced_color_grader.py",
        "args": "grade {project} --all-shots --style cinematic",
        "deps": ["composite"],
        "skippable": True,
    },
    "subtitles": {
        "script": "subtitle_generator.py",
        "args": "generate {project} --format srt",
        "deps": ["dubbing"],
        "skippable": True,
    },
    "thumbnails": {
        "script": "thumbnail_generator.py",
        "args": "generate {project} --text 'Episode 1'",
        "deps": ["composite"],
        "skippable": True,
    },
    "assemble": {
        "script": "episode_manager.py",
        "args": "assemble {project} --episode EP01",
        "deps": ["composite", "color_grade", "subtitles"],
        "skippable": False,
    },
    "distribute": {
        "script": "distribution_formatter.py",
        "args": "batch {project} --platform all",
        "deps": ["assemble"],
        "skippable": False,
    },
}

# Pipeline DAG (3D):
#   init → storyboard → {sets, characters} → layout → import_characters
#   → {keyframes, geo_animation, facial_animation} + {dubbing, music, sound_design}
#   → render → {interpolate, color_grade, subtitles, thumbnails} → assemble → distribute
# 3D mode = the integrated Blender script→video pipeline (02-pipeline/). One generic engine
# + set registry + show bible produce the whole episode; this DAG wraps it for the platform
# (one command surface, dry-run, resume, logging, ledger). Requires --company/--unit; the run
# slug ({project}) maps to business_units/<company>/<unit>/production/<project>/.
PIPELINE_3D = {
    "init": {
        "script": "init_project.py",
        "args": "create {project} --company {company} --unit {unit} --title '{title}'",
        "deps": [], "skippable": True,
    },
    "produce": {                       # parse → VO → render → assemble → stitch → captions
        "script": "../02-pipeline/produce.py",
        "args": "--company {company} --unit {unit} --run {project} --episode {project}",
        "deps": ["init"], "skippable": False, "timeout": 7200,
    },
    "distribute": {                    # 9:16 vertical + thumbnail + burned captions
        "script": "../02-pipeline/distribute.py",
        "args": "--company {company} --unit {unit} --run {project} --title '{title}'",
        "deps": ["produce"], "skippable": False, "timeout": 1800,
    },
}


RUN_COMPANY = ""   # set by run_pipeline; consumed by run_step's arg templating (3D mode)
RUN_UNIT = ""

def _pipeline_for(mode: str) -> dict:
    return PIPELINE_3D if mode == "3d" else PIPELINE_2D


def _log_entry(log_file: Path, entry: dict):
    """Append a structured JSONL log entry."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_step(step_name: str, project_slug: str, title: str, dry_run: bool = False,
             log_file: Path = None, comfyui_lock: threading.Lock = None, mode: str = "2d") -> dict:
    """Execute a single pipeline step."""
    cfg = _pipeline_for(mode)[step_name]
    script_path = (WORKSPACE_ROOT / "01_SKILLS" / cfg["script"]).resolve()
    args = cfg["args"].format(project=project_slug, title=title, company=RUN_COMPANY, unit=RUN_UNIT)
    cmd = f"{PYTHON} {script_path} {args}"
    step_timeout = cfg.get("timeout", 600)   # per-step override (3D renders exceed 10 min)
    
    if dry_run:
        result = {"status": "dry_run", "step": step_name, "command": cmd}
        if log_file:
            _log_entry(log_file, {**result, "timestamp": datetime.now().isoformat()})
        return result

    if cfg.get("comfyui") and comfyui_lock:
        comfyui_lock.acquire()
    
    start = time.time()
    start_iso = datetime.now().isoformat()
    try:
        proc_result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=step_timeout, cwd=WORKSPACE_ROOT,
        )
        elapsed = time.time() - start
        
        # Try to parse JSON from last line of stdout
        output_lines = [l for l in proc_result.stdout.strip().split("\n") if l.strip()]
        parsed = {}
        for line in reversed(output_lines):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        
        result = {
            "status": "ok" if proc_result.returncode == 0 else "error",
            "step": step_name,
            "time_sec": round(elapsed, 2),
            "parsed_output": parsed,
            "stderr": proc_result.stderr[:200] if proc_result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        result = {"status": "timeout", "step": step_name, "time_sec": step_timeout}
    except Exception as e:
        result = {"status": "error", "step": step_name, "error": str(e)[:200]}
    
    if cfg.get("comfyui") and comfyui_lock:
        comfyui_lock.release()
    
    if log_file:
        _log_entry(log_file, {
            **result,
            "timestamp": start_iso,
            "finished": datetime.now().isoformat(),
            "command": cmd,
        })
    
    return result


def _preflight_check(pipeline: dict) -> list[str]:
    """Check critical services before starting pipeline."""
    import urllib.request
    issues = []
    # ComfyUI is only required when the selected pipeline actually has comfyui-tagged steps
    # (true for the 2D image-generation DAG; the 3D Blender/VRoid DAG doesn't touch it).
    if any(cfg.get("comfyui") for cfg in pipeline.values()):
        try:
            req = urllib.request.Request("http://127.0.0.1:8188/system_stats", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status != 200:
                    issues.append("ComfyUI not responding on :8188")
        except Exception:
            issues.append("ComfyUI not available on :8188")
    # At least one MLX server should be up
    mlx_ok = False
    for port in [8000, 8001, 8002]:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    mlx_ok = True
                    break
        except Exception:
            pass
    if not mlx_ok:
        issues.append("No MLX inference server responding on :8000/:8001/:8002")
    return issues


def _topological_layers(pipeline: dict) -> list[list[str]]:
    """Group steps into layers where each layer's deps are satisfied by previous layers."""
    completed = set()
    remaining = set(pipeline.keys())
    layers = []
    while remaining:
        layer = []
        for step in remaining:
            deps = pipeline[step]["deps"]
            # Deps not in the pipeline dict are assumed already completed (e.g. resume-from)
            if all(d in completed or d not in pipeline for d in deps):
                layer.append(step)
        if not layer:
            raise ValueError(f"Circular dependency detected in pipeline: {remaining}")
        layers.append(layer)
        completed.update(layer)
        remaining -= set(layer)
    return layers


def run_pipeline(project_slug: str, mode: str = "2d", from_step: str = None,
                 dry_run: bool = False, title: str = "", parallel: bool = False,
                 jobs: int = 4, company: str = "", unit: str = "") -> dict:
    """Run the full pipeline."""
    global RUN_COMPANY, RUN_UNIT
    RUN_COMPANY, RUN_UNIT = company, unit
    if mode == "3d" and not (company and unit):
        return {"status": "error", "project": project_slug, "mode": mode,
                "error": "3D mode requires --company and --unit (maps to business_units/<company>/<unit>/production/<slug>/)"}
    pipeline = _pipeline_for(mode)
    steps = list(pipeline.keys())

    if from_step and from_step in steps:
        steps = steps[steps.index(from_step):]

    # Pre-flight check (skip for dry-run)
    if not dry_run:
        issues = _preflight_check(pipeline)
        if issues:
            print("🚫 Pre-flight check failed:")
            for issue in issues:
                print(f"   ❌ {issue}")
            print("\nFix the issues above or use --dry-run to preview the pipeline.")
            return {
                "status": "error",
                "project": project_slug,
                "mode": mode,
                "dry_run": False,
                "error": "pre-flight failed",
                "issues": issues,
            }
    
    # Setup logging
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"pipeline_{project_slug}_{timestamp}.jsonl"
    _log_entry(log_file, {
        "event": "pipeline_start",
        "project": project_slug,
        "mode": mode,
        "dry_run": dry_run,
        "parallel": parallel,
        "jobs": jobs,
        "timestamp": datetime.now().isoformat(),
    })
    
    results = {}
    total_start = time.time()
    
    print(f"🎬 Starting {mode.upper()} pipeline for '{project_slug}'")
    print(f"   Steps: {len(steps)} | Dry run: {dry_run} | Parallel: {parallel} | Jobs: {jobs}")
    print(f"   Log: {log_file}")
    print("=" * 60)
    
    if not parallel or dry_run:
        # Sequential execution
        for i, step_name in enumerate(steps, 1):
            print(f"\n[{i}/{len(steps)}] {step_name}...", end=" ", flush=True)
            
            result = run_step(step_name, project_slug, title or project_slug, dry_run, log_file, mode=mode)
            results[step_name] = result
            
            if result["status"] == "ok":
                t = result.get("time_sec", 0)
                print(f"✅ {t:.1f}s")
            elif result["status"] == "dry_run":
                print(f"⏭️  (dry run)")
            else:
                print(f"❌ {result.get('error', result.get('stderr', 'Unknown'))[:60]}")
                if not dry_run:
                    print(f"\n   Stopping pipeline. Fix {step_name} and resume with --from {step_name}")
                    break
    else:
        # Parallel execution by topological layers
        layers = _topological_layers({k: v for k, v in pipeline.items() if k in steps})
        step_num = 0
        total_steps = len(steps)
        failed = False
        
        comfyui_lock = threading.Lock()
        for layer in layers:
            if failed:
                for step_name in layer:
                    results[step_name] = {"status": "skipped", "step": step_name, "reason": "dependency failed"}
                continue
            
            if len(layer) == 1:
                step_name = layer[0]
                step_num += 1
                print(f"\n[{step_num}/{total_steps}] {step_name}...", end=" ", flush=True)
                result = run_step(step_name, project_slug, title or project_slug, dry_run, log_file, comfyui_lock, mode)
                results[step_name] = result
                if result["status"] == "ok":
                    print(f"✅ {result.get('time_sec', 0):.1f}s")
                else:
                    print(f"❌ {result.get('error', result.get('stderr', 'Unknown'))[:60]}")
                    failed = True
            else:
                # Run layer in parallel
                print(f"\n  → Parallel layer: {', '.join(layer)}")
                with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
                    futures = {
                        executor.submit(run_step, step_name, project_slug, title or project_slug, dry_run, log_file, comfyui_lock, mode): step_name
                        for step_name in layer
                    }
                    for future in concurrent.futures.as_completed(futures):
                        step_name = futures[future]
                        step_num += 1
                        try:
                            result = future.result()
                        except Exception as e:
                            result = {"status": "error", "step": step_name, "error": str(e)[:200]}
                        results[step_name] = result
                        status_icon = "✅" if result["status"] == "ok" else "❌"
                        t = result.get("time_sec", 0)
                        print(f"  [{step_num}/{total_steps}] {step_name}: {status_icon} {t:.1f}s")
                        if result["status"] != "ok":
                            failed = True
    
    total_time = time.time() - total_start
    result_list = [results.get(s, {"status": "not_run", "step": s}) for s in steps]
    successes = sum(1 for r in result_list if r["status"] in ("ok", "dry_run"))
    
    print("\n" + "=" * 60)
    print(f"Pipeline complete: {successes}/{len(steps)} steps successful")
    print(f"Total time: {total_time:.1f}s")
    print(f"Log: {log_file}")
    print("=" * 60)
    
    # macOS notification
    try:
        from notify import send_pipeline_notification
        send_pipeline_notification(
            project_slug, successes, len(steps),
            failed=(successes < len(steps) and not dry_run),
            log_file=str(log_file),
        )
    except Exception:
        pass
    
    _log_entry(log_file, {
        "event": "pipeline_end",
        "project": project_slug,
        "mode": mode,
        "dry_run": dry_run,
        "total_time_sec": round(total_time, 2),
        "successful": successes,
        "total_steps": len(steps),
        "timestamp": datetime.now().isoformat(),
    })
    
    return {
        "status": "ok",
        "project": project_slug,
        "mode": mode,
        "dry_run": dry_run,
        "parallel": parallel,
        "jobs": jobs,
        "total_steps": len(steps),
        "successful": successes,
        "total_time_sec": round(total_time, 2),
        "results": result_list,
        "log_file": str(log_file),
    }


def main():
    parser = argparse.ArgumentParser(description="Pipeline Orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    p_run = sub.add_parser("run", help="Run full pipeline")
    p_run.add_argument("project_slug")
    p_run.add_argument("--mode", default="2d", choices=["2d", "3d"])
    p_run.add_argument("--resume-from", default=None)
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--title", default="")
    p_run.add_argument("--parallel", action="store_true", help="Run independent steps in parallel")
    p_run.add_argument("--jobs", type=int, default=4, help="Max parallel workers (default: 4)")
    p_run.add_argument("--company", default="", help="Company slug (3D mode: business_units/<company>/...)")
    p_run.add_argument("--unit", default="", help="Business-unit slug (3D mode)")

    p_dry = sub.add_parser("dry-run", help="Show what would run")
    p_dry.add_argument("project_slug")
    p_dry.add_argument("--mode", default="2d", choices=["2d", "3d"])
    p_dry.add_argument("--title", default="")
    p_dry.add_argument("--company", default=""); p_dry.add_argument("--unit", default="")

    p_list = sub.add_parser("list", help="List pipeline steps")
    p_list.add_argument("--mode", default="2d", choices=["2d", "3d"])

    args = parser.parse_args()

    if args.cmd == "list":
        for name, cfg in _pipeline_for(args.mode).items():
            deps = ", ".join(cfg["deps"]) if cfg["deps"] else "none"
            print(f"  {name:20s} → {cfg['script']:30s} (deps: {deps})")
    elif args.cmd in ("run", "dry-run"):
        is_dry_run = args.cmd == "dry-run" or getattr(args, 'dry_run', False)
        result = run_pipeline(args.project_slug, args.mode, getattr(args, 'resume_from', None),
                             is_dry_run, args.title,
                             getattr(args, 'parallel', False), getattr(args, 'jobs', 4),
                             getattr(args, 'company', ''), getattr(args, 'unit', ''))
        if not is_dry_run:
            print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))

if __name__ == "__main__":
    main()
