#!/usr/bin/env python3
"""
blender_set_designer.py — AI Procedural Set Design from Scene Headings

Reads scene headings (e.g., "INT. CLASSROOM - DAY"), sends to MLX Qwen to
generate procedural Blender geometry code, and builds fully lit environments
with walls, floors, furniture, and props.

Usage:
    python blender_set_designer.py design <project_slug> [--scene SC001]
    python blender_set_designer.py design <project_slug> --all-scenes
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import textwrap
import urllib.request
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"
DEFAULT_MLX_URL = os.environ.get("MLX_URL", "http://127.0.0.1:8001")
DEFAULT_MLX_MODEL = os.environ.get("MLX_MODEL", "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")

SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Blender environment artist. You write concise Python bpy code
    that procedurally generates interior/exterior sets from scene descriptions.
    
    Rules:
    - Respond ONLY with a single Python code block. No explanations.
    - Use bpy.ops.mesh.primitive_*_add() for basic shapes.
    - Use simple modifiers (array, mirror, solidify) for detail.
    - Create materials with basic colors — no complex node setups.
    - Group objects into collections named after the scene.
    - Do NOT call bpy.ops.wm.read_factory_settings() or quit_blender.
    - Assume the scene is already open. Create a new collection for the set.
    - Scale: 1 Blender unit = 1 meter.
    - End cleanly. No <|im_end|> tokens.
""")


def call_mlx(prompt: str, temperature: float = 0.25, max_tokens: int = 1000) -> str:
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
    match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if match:
        code = match.group(1)
    else:
        match = re.search(r"```\n(.*?)```", text, re.DOTALL)
        code = match.group(1) if match else text
    code = re.sub(r"<\|im_end\|>.*", "", code, flags=re.DOTALL).strip()
    return code


def validate_code(code: str) -> tuple[bool, str]:
    forbidden = ["bpy.ops.wm.read_factory_settings", "bpy.ops.wm.quit_blender", "os.system", "subprocess", "exec(", "eval("]
    for f in forbidden:
        if f in code:
            return False, f"Forbidden: {f}"
    try:
        compile(code, "<generated>", "exec")
        return True, ""
    except SyntaxError as e:
        return False, f"Syntax: {e}"


def build_prompt(scene: dict) -> str:
    heading = scene.get("heading", "")
    description = scene.get("description", "")
    shots = scene.get("shot_count", 0)

    return f"""Scene heading: {heading}
Description: {description}
Number of shots in this scene: {shots}

Write Python bpy code to build a complete procedural set for this scene.
Include: walls, floor, ceiling (if interior), main furniture, and props.
Use realistic proportions. Group everything into a collection named "SET_{scene['scene_id']}".
Apply simple materials with appropriate colors.
"""


class SetDesigner:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_path = self.project_dir / "03-layout" / "layout.blend"
        self.shot_list = self._load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.cache_dir = self.project_dir / "03-layout" / "set_design_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def design(self, scene_id: str | None = None, all_scenes: bool = False) -> dict:
        import bpy

        if not self.layout_path.exists():
            return {"status": "error", "message": f"Layout not found: {self.layout_path}"}

        bpy.ops.wm.open_mainfile(filepath=str(self.layout_path))

        scenes = self.shot_list.get("scenes", [])
        if scene_id:
            scenes = [s for s in scenes if s["scene_id"] == scene_id]
        if not all_scenes and not scene_id:
            return {"status": "error", "message": "Specify --scene or --all-scenes"}

        results = []
        for scene in scenes:
            sid = scene["scene_id"]
            cache_file = self.cache_dir / f"{sid}.py"

            if cache_file.exists():
                code = extract_python_code(cache_file.read_text(encoding="utf-8"))
                source = "cache"
            else:
                prompt = build_prompt(scene)
                print(f"\n🏗️ Designing set for {sid}: {scene.get('heading', '')}")
                try:
                    raw = call_mlx(prompt)
                    code = extract_python_code(raw)
                    source = "mlx"
                    cache_file.write_text(code, encoding="utf-8")
                except Exception as e:
                    results.append({"scene_id": sid, "status": "error", "phase": "generation", "error": str(e)})
                    continue

            valid, err = validate_code(code)
            if not valid:
                results.append({"scene_id": sid, "status": "error", "phase": "validation", "error": err})
                continue

            print(f"  ⚙️ Building set ({len(code)} chars)...")
            try:
                exec(code, {"bpy": bpy, "__name__": "__main__"})
                results.append({"scene_id": sid, "status": "ok", "source": source})
            except Exception as e:
                results.append({"scene_id": sid, "status": "error", "phase": "execution", "error": str(e)})

        bpy.ops.wm.save_as_mainfile(filepath=str(self.layout_path))
        return {
            "status": "ok",
            "project": self.project_slug,
            "results": results,
            "successful": sum(1 for r in results if r["status"] == "ok"),
            "failed": sum(1 for r in results if r["status"] == "error"),
        }


def run_inside_blender():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Blender Set Designer")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("design", help="Generate procedural sets")
    p.add_argument("project_slug")
    p.add_argument("--scene", help="Specific scene ID")
    p.add_argument("--all-scenes", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    designer = SetDesigner(args.project_slug)
    if args.dry_run:
        for scene in designer.shot_list.get("scenes", []):
            if args.scene and scene["scene_id"] != args.scene:
                continue
            raw = call_mlx(build_prompt(scene))
            print(f"\n--- {scene['scene_id']} ---")
            print(extract_python_code(raw))
    else:
        result = designer.design(scene_id=args.scene, all_scenes=args.all_scenes)
        print(json.dumps(result, indent=2))


def run_outside_blender():
    parser = argparse.ArgumentParser(description="Blender Set Designer")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("design", help="Generate procedural sets")
    p.add_argument("project_slug")
    p.add_argument("--scene")
    p.add_argument("--all-scenes", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    script_path = Path(__file__).resolve()
    cmd = [BLENDER_BINARY, "--background", "--python", str(script_path), "--", "design", args.project_slug]
    if args.scene:
        cmd.extend(["--scene", args.scene])
    if args.all_scenes:
        cmd.append("--all-scenes")
    if args.dry_run:
        cmd.append("--dry-run")
    print(f"🏗️ Designing sets for {args.project_slug}...")
    subprocess.run(cmd, check=True)


def main():
    try:
        import bpy
        run_inside_blender()
    except ImportError:
        run_outside_blender()


if __name__ == "__main__":
    main()
