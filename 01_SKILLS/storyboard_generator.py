#!/usr/bin/env python3
"""
storyboard_generator.py — Autonomous Storyboard Generator for Solocorn Studios

Generates concept art storyboards from a parsed screenplay shot list.
Fully autonomous: reads shot metadata, crafts prompts, batch-generates images,
compiles a reviewable HTML storyboard, and registers assets.

Usage:
    python storyboard_generator.py generate ap-stats-movie --model sdxl --style anime
    python storyboard_generator.py generate ap-stats-movie --model flux --style cinematic
    python storyboard_generator.py compile ap-stats-movie
    python storyboard_generator.py render-queue ap-stats-movie --model sdxl

Env:
    COMFYUI_URL           — default: http://127.0.0.1:8188
    STORYBOARD_STYLE      — default style preset (anime|cinematic|watercolor|line_art)
    STORYBOARD_MODEL      — default model (sdxl|flux)
"""

import argparse
import json
import os
import random
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# Import local tools
sys.path.insert(0, str(Path(__file__).parent))
from asset_manager import AssetManager
from script_parser import ScriptParser

# Optional: import render_queue for async dispatch
try:
    from render_queue import QueueDatabase, RenderJob
    _RENDER_QUEUE_AVAILABLE = True
except ImportError:
    _RENDER_QUEUE_AVAILABLE = False

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
DEFAULT_STYLE = os.environ.get("STORYBOARD_STYLE", "anime")
DEFAULT_MODEL = os.environ.get("STORYBOARD_MODEL", "sdxl")

# ── Style presets ───────────────────────────────────────────────────────────

STYLE_PRESETS = {
    "anime": {
        "keywords": "anime style, clean lines, solid colors, cel shading, vibrant palette, studio ghibli inspired",
        "negative": "photorealistic, 3d render, blurry, deformed, ugly, duplicate, watermark, signature",
        "aspect": (16, 9),
    },
    "cinematic": {
        "keywords": "cinematic lighting, film grain, shallow depth of field, color graded, anamorphic lens, 35mm film, dramatic composition",
        "negative": "cartoon, anime, illustration, blurry, deformed, ugly, duplicate, watermark, signature",
        "aspect": (21, 9),
    },
    "watercolor": {
        "keywords": "watercolor painting, soft edges, flowing pigments, paper texture, artistic, impressionistic, gentle colors",
        "negative": "photorealistic, 3d render, sharp edges, digital art, blurry, deformed, ugly, watermark",
        "aspect": (16, 9),
    },
    "line_art": {
        "keywords": "line art, ink drawing, black and white, cross hatching, technical illustration, clean contours, storyboard sketch",
        "negative": "color, shading, photorealistic, 3d render, blurry, deformed, ugly, watermark",
        "aspect": (16, 9),
    },
    "photorealistic": {
        "keywords": "photorealistic, hyper detailed, 8k uhd, natural lighting, professional photography, sharp focus, realistic textures",
        "negative": "cartoon, anime, illustration, painting, blurry, deformed, ugly, duplicate, watermark, signature",
        "aspect": (16, 9),
    },
}

# ── Shot type visual mappings ───────────────────────────────────────────────

SHOT_TYPE_DESCRIPTIONS = {
    "wide": "wide establishing shot showing the full scene and environment",
    "medium": "medium shot framing subject from waist up, showing body language",
    "close_up": "close up shot focusing on facial expression and emotional detail",
    "extreme_close_up": "extreme close up on eyes or specific detail, intense emotional impact",
    "insert": "insert shot focusing on a specific object or detail in the scene",
    "over_shoulder": "over-the-shoulder shot showing one character's perspective on another",
    "aerial": "aerial shot from above showing the layout and spatial relationships",
    "static": "static framed shot with no camera movement, stable composition",
    "tracking": "tracking shot following the subject's movement through the scene",
    "pan": "panning shot sweeping across the scene horizontally",
    "tilt": "tilting shot moving vertically up or down",
    "dolly": "dolly shot moving the camera forward or backward",
}

CAMERA_MOVEMENT_DESCRIPTIONS = {
    "static": "static camera, no movement",
    "pan": "slow horizontal pan",
    "tilt": "vertical tilt",
    "dolly": "smooth dolly movement",
    "tracking": "tracking shot following subject",
    "zoom": "gradual zoom",
    "handheld": "subtle handheld camera feel",
    "crane": "sweeping crane shot",
}

# ── Prompt engine ───────────────────────────────────────────────────────────

class PromptEngine:
    """Autonomous prompt crafting from shot metadata."""

    def __init__(self, style_preset: str = DEFAULT_STYLE):
        self.style = STYLE_PRESETS.get(style_preset, STYLE_PRESETS["anime"])
        self.style_name = style_preset

    def craft(self, shot: dict, character_lookups: dict | None = None) -> str:
        """
        Craft a rich image generation prompt from shot metadata.

        Args:
            shot: Shot dict from shot-list.json.
            character_lookups: Optional dict mapping character names to visual descriptions.

        Returns:
            A detailed prompt string ready for ComfyUI.
        """
        parts = []

        # 1. Scene environment
        scene_heading = shot.get("scene_heading", "")
        if scene_heading:
            # Parse INT/EXT, location, time
            env_desc = self._parse_scene_heading(scene_heading)
            if env_desc:
                parts.append(env_desc)

        # 2. Shot type framing
        shot_type = shot.get("shot_type", "medium")
        shot_desc = SHOT_TYPE_DESCRIPTIONS.get(shot_type, f"{shot_type} shot")
        parts.append(shot_desc)

        # 3. Camera movement
        movement = shot.get("camera_movement", "static")
        move_desc = CAMERA_MOVEMENT_DESCRIPTIONS.get(movement, f"{movement} camera")
        parts.append(move_desc)

        # 4. Subject / Action
        action = shot.get("action", "")
        subject = shot.get("subject", "")
        if subject and action:
            parts.append(f"{subject} {action}")
        elif action:
            parts.append(action)
        elif subject:
            parts.append(subject)

        # 5. Dialogue context (if no action)
        dialogue = shot.get("dialogue", "")
        if dialogue and not action:
            parts.append(f"character speaking: '{dialogue[:80]}'")

        # 6. Notes as supplementary detail
        notes = shot.get("notes", "")
        if notes:
            # Strip [shot: ...] metadata from notes
            clean_notes = self._clean_notes(notes)
            if clean_notes and clean_notes not in action:
                parts.append(clean_notes)

        # 7. Apply character consistency lookups
        if character_lookups:
            for char_name, char_desc in character_lookups.items():
                if char_name.lower() in " ".join(parts).lower():
                    parts.append(f"{char_name} appearance: {char_desc}")

        # 8. Style keywords
        parts.append(self.style["keywords"])

        # 9. Cinematic quality boosters
        parts.append("professional storyboard frame, clear composition, high detail")

        prompt = ", ".join(p for p in parts if p.strip())
        # Clean up double commas and spacing
        prompt = prompt.replace(",,", ",").replace("  ", " ").strip()
        return prompt

    def negative(self) -> str:
        return self.style.get("negative", "")

    def resolution(self, base_height: int = 1024) -> tuple[int, int]:
        """Return (width, height) for the style's aspect ratio."""
        w_ratio, h_ratio = self.style.get("aspect", (16, 9))
        # Scale to base_height
        height = base_height
        width = int(height * w_ratio / h_ratio)
        # Round to multiples of 64 for SD compatibility
        width = (width // 64) * 64
        height = (height // 64) * 64
        return width, height

    def _parse_scene_heading(self, heading: str) -> str:
        """Convert 'INT. CLASSROOM - DAY' to a visual description."""
        heading = heading.strip()
        if heading.startswith("INT."):
            location = heading[4:].strip().split("-")[0].strip()
            time_of_day = heading.split("-")[-1].strip() if "-" in heading else ""
            return f"interior {location.lower()}, {time_of_day.lower() if time_of_day else 'indoor'} lighting"
        elif heading.startswith("EXT."):
            location = heading[4:].strip().split("-")[0].strip()
            time_of_day = heading.split("-")[-1].strip() if "-" in heading else ""
            return f"exterior {location.lower()}, {time_of_day.lower() if time_of_day else 'outdoor'} lighting"
        return heading

    def _clean_notes(self, notes: str) -> str:
        """Remove [shot: ...] tags from notes."""
        import re
        clean = re.sub(r"\[shot:[^\]]*\]", "", notes)
        clean = re.sub(r"\[\w+:[^\]]*\]", "", clean)
        return clean.strip(" .")


# ── ComfyUI workflow builders ───────────────────────────────────────────────

def build_sdxl_workflow(prompt: str, negative: str, width: int, height: int, steps: int = 30, seed: int = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    return {
        "1": {"inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}, "class_type": "CheckpointLoaderSimple"},
        "2": {"inputs": {"text": prompt, "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
        "3": {"inputs": {"text": negative, "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
        "4": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "5": {"inputs": {"seed": seed, "steps": steps, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}, "class_type": "KSampler"},
        "6": {"inputs": {"samples": ["5", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
        "7": {"inputs": {"filename_prefix": "storyboard_sdxl", "images": ["6", 0]}, "class_type": "SaveImage"},
    }


def build_flux_workflow(prompt: str, width: int, height: int, steps: int = 20, seed: int = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    return {
        "1": {"inputs": {"ckpt_name": "flux1-dev.safetensors"}, "class_type": "CheckpointLoaderSimple"},
        "2": {"inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp8_e4m3fn.safetensors", "type": "flux"}, "class_type": "DualCLIPLoader"},
        "3": {"inputs": {"vae_name": "ae.safetensors"}, "class_type": "VAELoader"},
        "4": {"inputs": {"text": prompt, "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
        "5": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptySD3LatentImage"},
        "6": {"inputs": {"max_shift": 1.15, "base_shift": 0.5, "width": width, "height": height, "model": ["1", 0]}, "class_type": "ModelSamplingFlux"},
        "7": {"inputs": {"seed": seed, "steps": steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0, "model": ["6", 0], "positive": ["4", 0], "negative": ["4", 0], "latent_image": ["5", 0]}, "class_type": "KSampler"},
        "8": {"inputs": {"samples": ["7", 0], "vae": ["3", 0]}, "class_type": "VAEDecode"},
        "9": {"inputs": {"filename_prefix": "storyboard_flux", "images": ["8", 0]}, "class_type": "SaveImage"},
    }


# ── Storyboard Generator ────────────────────────────────────────────────────

class StoryboardGenerator:
    def __init__(self, comfyui_url: str = DEFAULT_COMFYUI_URL):
        self.comfyui_url = comfyui_url.rstrip("/")
        self.client_id = f"storyboard_{random.randint(1000, 9999)}"

    def _post(self, path: str, payload: dict) -> dict:
        resp = requests.post(f"{self.comfyui_url}{path}", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        resp = requests.get(f"{self.comfyui_url}{path}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def comfyui_available(self) -> bool:
        try:
            requests.get(f"{self.comfyui_url}/system_stats", timeout=5)
            return True
        except Exception:
            return False

    def load_shot_list(self, project_slug: str) -> dict:
        """Load shot-list.json for a project."""
        shot_list_path = WORKSPACE_ROOT / "05_PROJECTS" / project_slug / "01-scripts" / "shot-list.json"
        if not shot_list_path.exists():
            raise FileNotFoundError(f"Shot list not found: {shot_list_path}")
        return json.loads(shot_list_path.read_text(encoding="utf-8"))

    def load_character_lookups(self, project_slug: str) -> dict:
        """Load character visual descriptions if available."""
        char_path = WORKSPACE_ROOT / "05_PROJECTS" / project_slug / "01-scripts" / "character_looks.json"
        if char_path.exists():
            return json.loads(char_path.read_text(encoding="utf-8"))
        return {}

    def generate_storyboard(
        self,
        project_slug: str,
        model: str = DEFAULT_MODEL,
        style: str = DEFAULT_STYLE,
        shot_ids: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Autonomous storyboard generation from shot list.

        Args:
            project_slug: Project identifier.
            model: "sdxl" or "flux".
            style: Style preset key.
            shot_ids: Optional filter — generate only these shots.
            dry_run: If True, only craft prompts without generating.

        Returns:
            Structured result with generated frames and manifest.
        """
        if not self.comfyui_available():
            return {"status": "error", "message": f"ComfyUI not available at {self.comfyui_url}"}

        # Load data
        shot_list = self.load_shot_list(project_slug)
        characters = self.load_character_lookups(project_slug)
        engine = PromptEngine(style)
        width, height = engine.resolution()

        # Prepare output dir
        output_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug / "02-storyboards"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine which shots to generate
        shots = shot_list.get("shots", [])
        if shot_ids:
            shots = [s for s in shots if s["shot_id"] in shot_ids]

        results = {
            "status": "ok",
            "project": project_slug,
            "model": model,
            "style": style,
            "resolution": f"{width}x{height}",
            "total_shots": len(shots),
            "generated": [],
            "failed": [],
            "dry_run": dry_run,
            "manifest_path": str(output_dir / "storyboard_manifest.json"),
        }

        manifest = {
            "project_slug": project_slug,
            "model": model,
            "style": style,
            "resolution": {"width": width, "height": height},
            "frames": [],
        }

        print(f"🎬 Storyboard generation: {len(shots)} shots, model={model}, style={style}")

        for i, shot in enumerate(shots, 1):
            shot_id = shot["shot_id"]
            prompt = engine.craft(shot, characters)
            negative = engine.negative()

            print(f"\n  [{i}/{len(shots)}] {shot_id}")
            print(f"    Prompt: {prompt[:120]}...")

            if dry_run:
                results["generated"].append({
                    "shot_id": shot_id,
                    "prompt": prompt,
                    "negative": negative,
                    "dry_run": True,
                })
                manifest["frames"].append({
                    "shot_id": shot_id,
                    "prompt": prompt,
                    "output_path": None,
                    "status": "dry_run",
                })
                continue

            # Generate
            try:
                frame_result = self._generate_single(
                    shot_id=shot_id,
                    prompt=prompt,
                    negative=negative,
                    model=model,
                    width=width,
                    height=height,
                    output_dir=output_dir,
                )
                results["generated"].append(frame_result)
                manifest["frames"].append({
                    "shot_id": shot_id,
                    "prompt": prompt,
                    "output_path": frame_result.get("output_path"),
                    "status": "ok",
                })
            except Exception as e:
                print(f"    ❌ Failed: {e}")
                results["failed"].append({"shot_id": shot_id, "error": str(e)})
                manifest["frames"].append({
                    "shot_id": shot_id,
                    "prompt": prompt,
                    "output_path": None,
                    "status": "error",
                    "error": str(e),
                })

        # Save manifest
        manifest_path = output_dir / "storyboard_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Compile HTML review
        html_path = self.compile_html(project_slug, manifest)
        results["html_path"] = str(html_path)

        # Register in asset manager
        try:
            am = AssetManager()
            for frame in manifest["frames"]:
                if frame.get("output_path"):
                    am.register_asset(
                        project_id=project_slug,
                        shot_id=frame["shot_id"],
                        file_path=frame["output_path"],
                        asset_type="storyboard_frame",
                    )
        except Exception as e:
            print(f"⚠️ Asset manager registration skipped: {e}")

        results["summary"] = f"Generated {len(results['generated'])} frames, {len(results['failed'])} failed"
        return results

    def _generate_single(
        self,
        shot_id: str,
        prompt: str,
        negative: str,
        model: str,
        width: int,
        height: int,
        output_dir: Path,
        steps: int = None,
    ) -> dict:
        """Queue one shot to ComfyUI, poll, and download."""
        if model == "sdxl":
            workflow = build_sdxl_workflow(prompt, negative, width, height, steps=steps or 30)
        elif model == "flux":
            workflow = build_flux_workflow(prompt, width, height, steps=steps or 20)
        else:
            raise ValueError(f"Unknown model: {model}")

        # Submit
        queue_result = self._post("/prompt", {"prompt": workflow, "client_id": self.client_id})
        prompt_id = queue_result["prompt_id"]

        # Poll
        result = self._wait_for_result(prompt_id, timeout=600)
        if result["status"] != "ok":
            raise RuntimeError(result.get("message", "Generation failed"))

        # Download images
        outputs = result["entry"].get("outputs", {})
        saved_paths = []
        for node_id, node_output in outputs.items():
            for img in node_output.get("images", []):
                img_data = self._download_image(img["filename"], img.get("subfolder", ""))
                ext = Path(img["filename"]).suffix or ".png"
                out_name = f"{shot_id}{ext}"
                out_path = output_dir / out_name
                out_path.write_bytes(img_data)
                saved_paths.append(str(out_path))

        return {
            "shot_id": shot_id,
            "prompt": prompt,
            "output_path": saved_paths[0] if saved_paths else None,
            "prompt_id": prompt_id,
        }

    def _wait_for_result(self, prompt_id: str, timeout: int = 600, poll_interval: float = 3.0) -> dict:
        start = time.time()
        while time.time() - start < timeout:
            try:
                history = self._get(f"/history/{prompt_id}")
                if prompt_id in history:
                    entry = history[prompt_id]
                    status = entry.get("status", {})
                    if status.get("status_str") == "success":
                        return {"status": "ok", "entry": entry}
                    elif status.get("completed"):
                        return {"status": "error", "message": f"Generation failed: {status}"}
            except Exception:
                pass
            time.sleep(poll_interval)
        return {"status": "timeout", "message": f"Timed out after {timeout}s"}

    def _download_image(self, filename: str, subfolder: str = "") -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": "output"}
        resp = requests.get(f"{self.comfyui_url}/view", params=params, timeout=60)
        resp.raise_for_status()
        return resp.content

    def compile_html(self, project_slug: str, manifest: dict | None = None) -> Path:
        """Generate an HTML storyboard for human review."""
        project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        sb_dir = project_dir / "02-storyboards"

        if manifest is None:
            manifest_path = sb_dir / "storyboard_manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            else:
                manifest = {"frames": []}

        html_path = sb_dir / "storyboard.html"

        frames_html = []
        for frame in manifest.get("frames", []):
            shot_id = frame["shot_id"]
            prompt = frame.get("prompt", "")
            img_path = frame.get("output_path", "")
            status = frame.get("status", "unknown")

            if img_path and Path(img_path).exists():
                # Use relative path from HTML file
                rel_path = Path(img_path).name
                img_tag = f'<img src="{rel_path}" alt="{shot_id}" loading="lazy">'
            else:
                img_tag = f'<div class="missing">{status.upper()}</div>'

            frames_html.append(f"""
            <div class="frame">
                <div class="meta">
                    <span class="shot-id">{shot_id}</span>
                    <span class="status status-{status}">{status}</span>
                </div>
                <div class="image">{img_tag}</div>
                <div class="prompt">{prompt[:300]}{'...' if len(prompt) > 300 else ''}</div>
            </div>
            """)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Storyboard — {project_slug}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0a; color: #eee; margin: 0; padding: 2rem; }}
        h1 {{ font-weight: 300; letter-spacing: -0.5px; margin-bottom: 0.5rem; }}
        .subtitle {{ color: #888; margin-bottom: 2rem; font-size: 0.9rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.5rem; }}
        .frame {{ background: #141414; border-radius: 8px; overflow: hidden; border: 1px solid #222; }}
        .meta {{ display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1rem; background: #1a1a1a; border-bottom: 1px solid #222; }}
        .shot-id {{ font-family: monospace; font-size: 0.85rem; color: #4fc3f7; font-weight: 600; }}
        .status {{ font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 4px; text-transform: uppercase; }}
        .status-ok {{ background: #1b5e20; color: #69f0ae; }}
        .status-error {{ background: #b71c1c; color: #ff8a80; }}
        .status-dry_run {{ background: #f57f17; color: #ffd54f; }}
        .image img {{ width: 100%; height: auto; display: block; }}
        .missing {{ padding: 4rem 2rem; text-align: center; color: #555; font-size: 0.9rem; }}
        .prompt {{ padding: 0.75rem 1rem; font-size: 0.8rem; color: #999; line-height: 1.4; border-top: 1px solid #222; }}
    </style>
</head>
<body>
    <h1>Storyboard</h1>
    <div class="subtitle">{project_slug} — {len(manifest.get('frames', []))} frames — {manifest.get('model', 'unknown')} / {manifest.get('style', 'unknown')}</div>
    <div class="grid">
        {''.join(frames_html)}
    </div>
</body>
</html>"""

        html_path.write_text(html, encoding="utf-8")
        print(f"  📋 HTML storyboard: {html_path}")
        return html_path

    def enqueue_to_render_queue(self, project_slug: str, model: str = DEFAULT_MODEL, style: str = DEFAULT_STYLE) -> dict:
        """
        Enqueue storyboard generation as a render job for async execution.
        Requires render_queue.py to be available.
        """
        if not _RENDER_QUEUE_AVAILABLE:
            return {"status": "error", "message": "render_queue.py not available"}

        db = QueueDatabase()
        script_path = WORKSPACE_ROOT / "01_SKILLS" / "storyboard_generator.py"
        python_bin = WORKSPACE_ROOT / "env" / "bin" / "python3"
        if not python_bin.exists():
            python_bin = Path(sys.executable)
        command = (
            f'"{python_bin}" "{script_path}" generate "{project_slug}" '
            f'--model "{model}" --style "{style}"'
        )
        log_path = WORKSPACE_ROOT / "08_RENDER_FARM" / "logs" / f"{project_slug}_STORYBOARD_{int(time.time())}.log"

        job = RenderJob(
            job_id=None,
            project_id=project_slug,
            shot_id="STORYBOARD",
            renderer="storyboard",
            command=command,
            cwd=str(WORKSPACE_ROOT),
            env_json="{}",
            output_path=str(WORKSPACE_ROOT / "05_PROJECTS" / project_slug / "02-storyboards"),
            log_path=str(log_path),
            priority=3,
            status="queued",
            retry_count=0,
            created_at=datetime.utcnow().isoformat(),
            started_at=None,
            completed_at=None,
            error_message=None,
            exit_code=None,
        )
        job_id = db.enqueue(job)
        return {"status": "ok", "job_id": job_id, "message": f"Storyboard job enqueued: {job_id}"}


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Autonomous Storyboard Generator")
    sub = parser.add_subparsers(dest="command", required=True)

    # generate
    p_gen = sub.add_parser("generate", help="Generate storyboard frames from shot list")
    p_gen.add_argument("project_slug", help="Project identifier")
    p_gen.add_argument("--model", choices=["sdxl", "flux"], default=DEFAULT_MODEL)
    p_gen.add_argument("--style", choices=list(STYLE_PRESETS.keys()), default=DEFAULT_STYLE)
    p_gen.add_argument("--shots", help="Comma-separated shot IDs (default: all)")
    p_gen.add_argument("--dry-run", action="store_true", help="Craft prompts without generating")

    # compile
    p_compile = sub.add_parser("compile", help="Compile HTML storyboard from existing manifest")
    p_compile.add_argument("project_slug", help="Project identifier")

    # render-queue
    p_rq = sub.add_parser("render-queue", help="Enqueue storyboard generation to render queue")
    p_rq.add_argument("project_slug", help="Project identifier")
    p_rq.add_argument("--model", choices=["sdxl", "flux"], default=DEFAULT_MODEL)
    p_rq.add_argument("--style", choices=list(STYLE_PRESETS.keys()), default=DEFAULT_STYLE)

    # craft-prompts
    p_prompts = sub.add_parser("craft-prompts", help="Show auto-crafted prompts for all shots")
    p_prompts.add_argument("project_slug", help="Project identifier")
    p_prompts.add_argument("--style", choices=list(STYLE_PRESETS.keys()), default=DEFAULT_STYLE)

    args = parser.parse_args()

    gen = StoryboardGenerator()

    if args.command == "generate":
        shot_ids = [s.strip() for s in args.shots.split(",")] if args.shots else None
        result = gen.generate_storyboard(
            project_slug=args.project_slug,
            model=args.model,
            style=args.style,
            shot_ids=shot_ids,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "compile":
        html_path = gen.compile_html(args.project_slug)
        print(f"Compiled: {html_path}")

    elif args.command == "render-queue":
        result = gen.enqueue_to_render_queue(args.project_slug, args.model, args.style)
        print(json.dumps(result, indent=2))

    elif args.command == "craft-prompts":
        shot_list = gen.load_shot_list(args.project_slug)
        characters = gen.load_character_lookups(args.project_slug)
        engine = PromptEngine(args.style)
        for shot in shot_list.get("shots", []):
            prompt = engine.craft(shot, characters)
            print(f"\n{shot['shot_id']}:")
            print(f"  {prompt}")
            print(f"  Negative: {engine.negative()}")


if __name__ == "__main__":
    main()
