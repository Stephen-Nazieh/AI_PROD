#!/usr/bin/env python3
"""
blender_ai_keyframer.py — AI-Assisted Keyframe Generation via MLX Qwen

Reads shot action/dialogue, sends to local MLX Qwen model, receives Python
bpy animation code, and executes it inside Blender.

Usage (outside Blender):
    python blender_ai_keyframer.py generate <project_slug> [--shot SC001_SH001]
    python blender_ai_keyframer.py generate <project_slug> --all-shots

Usage (inside Blender):
    blender --background --python blender_ai_keyframer.py -- generate <project_slug>

Env:
    MLX_URL — default: http://127.0.0.1:8001 (Qwen32B)
    MLX_MODEL — model identifier
"""

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"
DEFAULT_MLX_URL = os.environ.get("MLX_URL", "http://127.0.0.1:8001")
DEFAULT_MLX_MODEL = os.environ.get("MLX_MODEL", "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")

SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Blender Python API (bpy) animator. 
    You write concise, correct Python code that runs inside Blender.
    
    Rules:
    - Respond ONLY with a single Python code block. No explanations.
    - Use bpy.ops for creating objects, keyframe_insert for animation.
    - Assume a scene is already open. Do NOT call bpy.ops.wm.read_factory_settings().
    - Do NOT use bpy.context.scene.collection.objects.link() without checking.
    - For camera animation, modify existing camera objects by name (e.g., bpy.data.objects['CAM_SC001_SH001']).
    - For object animation, create new objects if they don't exist.
    - Use math.radians() for degree values.
    - The script will be run via `blender --background --python-expr`.
    - End the code block cleanly. Do not include <|im_end|> or similar tokens.
""")


def call_mlx(prompt: str, temperature: float = 0.2, max_tokens: int = 800) -> str:
    """Send prompt to MLX server and return raw response text."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        f"{DEFAULT_MLX_URL}/v1/chat/completions",
        data=json.dumps({
            "model": DEFAULT_MLX_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def extract_python_code(text: str) -> str:
    """Extract Python code from markdown fences and clean trailing tokens."""
    # Try fenced code block
    match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if match:
        code = match.group(1)
    else:
        match = re.search(r"```\n(.*?)```", text, re.DOTALL)
        if match:
            code = match.group(1)
        else:
            code = text

    # Clean trailing tokens
    code = re.sub(r"<\|im_end\|>.*", "", code, flags=re.DOTALL)
    code = code.strip()
    return code


def validate_code(code: str) -> tuple[bool, str]:
    """Basic validation of generated bpy code."""
    forbidden = [
        "bpy.ops.wm.read_factory_settings",
        "bpy.ops.wm.quit_blender",
        "os.system",
        "subprocess",
        "exec(",
        "eval(",
    ]
    for f in forbidden:
        if f in code:
            return False, f"Forbidden pattern: {f}"
    try:
        compile(code, "<generated>", "exec")
        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error: {e}"


def build_prompt(shot: dict) -> str:
    """Build a prompt from shot metadata."""
    shot_id = shot["shot_id"]
    action = shot.get("action", "")
    dialogue = shot.get("dialogue", "")
    shot_type = shot.get("shot_type", "medium")
    movement = shot.get("camera_movement", "static")
    notes = shot.get("notes", "")

    prompt = f"""Shot: {shot_id}
Shot type: {shot_type}
Camera movement: {movement}
Action: {action}
Dialogue: {dialogue}
Notes: {notes}

Write Python bpy code to animate this shot. The camera is named CAM_{shot_id}.
If the action involves a character or object that doesn't exist, create it.
Add appropriate keyframes for the shot duration (assume 72 frames).
"""
    return prompt


# ── Blender Executor (runs inside Blender) ──────────────────────────────────

class AIKeyframeExecutor:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_path = self.project_dir / "03-layout" / "layout.blend"
        self.shot_list = self._load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.cache_dir = self.project_dir / "03-layout" / "ai_keyframe_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def generate_and_apply(self, shot_id: str | None = None, all_shots: bool = False) -> dict:
        import bpy

        if not self.layout_path.exists():
            return {"status": "error", "message": f"Layout not found: {self.layout_path}"}

        bpy.ops.wm.open_mainfile(filepath=str(self.layout_path))

        shots = self.shot_list.get("shots", [])
        if shot_id:
            shots = [s for s in shots if s["shot_id"] == shot_id]
        if not all_shots and not shot_id:
            return {"status": "error", "message": "Specify --shot or --all-shots"}

        results = []

        for shot in shots:
            sid = shot["shot_id"]
            cache_file = self.cache_dir / f"{sid}.py"

            # Check cache first
            if cache_file.exists():
                code = cache_file.read_text(encoding="utf-8")
                source = "cache"
            else:
                prompt = build_prompt(shot)
                print(f"\n🤖 Generating animation for {sid}...")
                try:
                    raw = call_mlx(prompt)
                    code = extract_python_code(raw)
                    source = "mlx"
                    # Cache it
                    cache_file.write_text(code, encoding="utf-8")
                except Exception as e:
                    results.append({"shot_id": sid, "status": "error", "phase": "generation", "error": str(e)})
                    continue

            # Validate
            valid, error_msg = validate_code(code)
            if not valid:
                results.append({"shot_id": sid, "status": "error", "phase": "validation", "error": error_msg, "code": code[:200]})
                continue

            # The layout step already placed this camera correctly via
            # _position_camera() (framing distance/height/tilt derived from
            # shot_type). The LLM tends to hallucinate its own camera.location /
            # rotation_euler values, clobbering that correct framing — so for
            # static shots, snapshot the pre-existing transform and restore it
            # after the generated code runs.
            cam_obj_pre = bpy.data.objects.get(f"CAM_{sid}")
            pre_loc = tuple(cam_obj_pre.location) if cam_obj_pre else None
            pre_rot = tuple(cam_obj_pre.rotation_euler) if cam_obj_pre else None

            # Execute inside Blender
            print(f"  ⚙️ Executing {len(code)} chars of bpy code...")
            try:
                exec(code, {"bpy": bpy, "__name__": "__main__"})

                # Blender 5.1.2 fails to evaluate an animated camera's transform
                # during render, producing scene-independent placeholder frames
                # (proven via isolation testing — see render-engine investigation).
                # A "static" shot's camera shouldn't be keyframed or repositioned
                # at all, so strip any animation data and restore the framing the
                # layout step computed.
                if shot.get("camera_movement", "static") == "static":
                    cam_obj = bpy.data.objects.get(f"CAM_{sid}")
                    if cam_obj is not None:
                        if cam_obj.animation_data is not None:
                            cam_obj.animation_data_clear()
                        if pre_loc is not None:
                            cam_obj.location = pre_loc
                        if pre_rot is not None:
                            cam_obj.rotation_euler = pre_rot

                results.append({"shot_id": sid, "status": "ok", "source": source, "code_length": len(code)})
            except Exception as e:
                results.append({"shot_id": sid, "status": "error", "phase": "execution", "error": str(e), "code": code[:200]})

        # Save
        bpy.ops.wm.save_as_mainfile(filepath=str(self.layout_path))

        return {
            "status": "ok",
            "project": self.project_slug,
            "layout_path": str(self.layout_path),
            "results": results,
            "successful": sum(1 for r in results if r["status"] == "ok"),
            "failed": sum(1 for r in results if r["status"] == "error"),
        }


# ── CLI ─────────────────────────────────────────────────────────────────────

def run_inside_blender():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Blender AI Keyframer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="Generate AI keyframes for shots")
    p_gen.add_argument("project_slug", help="Project identifier")
    p_gen.add_argument("--shot", help="Specific shot ID")
    p_gen.add_argument("--all-shots", action="store_true", help="Process all shots")
    p_gen.add_argument("--dry-run", action="store_true", help="Generate code without executing")

    args = parser.parse_args(argv)

    if args.command == "generate":
        executor = AIKeyframeExecutor(args.project_slug)
        if args.dry_run:
            # Just generate and print code
            shots = executor.shot_list.get("shots", [])
            if args.shot:
                shots = [s for s in shots if s["shot_id"] == args.shot]
            for shot in shots:
                prompt = build_prompt(shot)
                raw = call_mlx(prompt)
                code = extract_python_code(raw)
                print(f"\n--- {shot['shot_id']} ---")
                print(code)
        else:
            result = executor.generate_and_apply(shot_id=args.shot, all_shots=args.all_shots)
            print(json.dumps(result, indent=2))


def run_outside_blender():
    parser = argparse.ArgumentParser(description="Blender AI Keyframer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="Generate AI keyframes for shots")
    p_gen.add_argument("project_slug", help="Project identifier")
    p_gen.add_argument("--shot", help="Specific shot ID")
    p_gen.add_argument("--all-shots", action="store_true", help="Process all shots")
    p_gen.add_argument("--dry-run", action="store_true", help="Generate code without executing")

    args = parser.parse_args()
    script_path = Path(__file__).resolve()

    if args.command == "generate":
        cmd = [
            BLENDER_BINARY,
            "--background",
            "--python", str(script_path),
            "--",
            "generate", args.project_slug,
        ]
        if args.shot:
            cmd.extend(["--shot", args.shot])
        if args.all_shots:
            cmd.append("--all-shots")
        if args.dry_run:
            cmd.append("--dry-run")
        print(f"🤖 AI keyframing for {args.project_slug}...")
        subprocess.run(cmd, check=True)


def main():
    try:
        import bpy
        INSIDE_BLENDER = True
    except ImportError:
        INSIDE_BLENDER = False

    if INSIDE_BLENDER:
        run_inside_blender()
    else:
        run_outside_blender()


if __name__ == "__main__":
    main()
