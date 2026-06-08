#!/usr/bin/env python3
"""
prompt_refiner.py — Self-Improving Storyboard Prompts via img2img Refinement

Takes rendered frames, sends them through ComfyUI img2img for quality
enhancement, and updates storyboard prompts based on visual analysis.

Usage:
    python prompt_refiner.py refine <project_slug> [--shot SC001_SH001]
    python prompt_refiner.py refine <project_slug> --all-shots --denoise 0.4
"""

import argparse
import json
import os
import random
import time
import urllib.request
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def comfyui_post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{COMFYUI_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def comfyui_get(path: str) -> dict:
    with urllib.request.urlopen(f"{COMFYUI_URL}{path}", timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_image(image_path: Path) -> str:
    """Upload an image to ComfyUI and return the server-side filename."""
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    with open(image_path, "rb") as f:
        file_data = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{COMFYUI_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["name"]


def download_image(filename: str, subfolder: str = "") -> bytes:
    params = f"?filename={filename}&subfolder={subfolder}&type=output"
    with urllib.request.urlopen(f"{COMFYUI_URL}/view{params}", timeout=60) as resp:
        return resp.read()


def build_img2img_workflow(image_name: str, prompt: str, denoise: float, width: int, height: int, seed: int = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    return {
        "1": {"inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}, "class_type": "CheckpointLoaderSimple"},
        "2": {"inputs": {"text": prompt, "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
        "3": {"inputs": {"text": "blurry, low quality, deformed, ugly", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
        "8": {"inputs": {"image": image_name, "upload": "image"}, "class_type": "LoadImage"},
        "9": {"inputs": {"pixels": ["8", 0], "vae": ["1", 2]}, "class_type": "VAEEncode"},
        "10": {"inputs": {"seed": seed, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": denoise, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["9", 0]}, "class_type": "KSampler"},
        "11": {"inputs": {"samples": ["10", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
        "12": {"inputs": {"filename_prefix": "refined", "images": ["11", 0]}, "class_type": "SaveImage"},
    }


def wait_for_result(prompt_id: str, timeout: int = 300) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        try:
            history = comfyui_get(f"/history/{prompt_id}")
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "success":
                    return {"status": "ok", "entry": entry}
                elif status.get("completed"):
                    return {"status": "error", "message": str(status)}
        except Exception:
            pass
        time.sleep(3)
    return {"status": "timeout"}


class PromptRefiner:
    def __init__(self, project_slug: str, denoise: float = 0.4):
        self.project_slug = project_slug
        self.denoise = denoise
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.manifest = _load_json(self.project_dir / "02-storyboards" / "storyboard_manifest.json")
        self.renders_dir = self.project_dir / "04-raw_renders"
        self.refined_dir = self.project_dir / "02-storyboards" / "refined"
        self.refined_dir.mkdir(parents=True, exist_ok=True)

    def refine(self, shot_id: str | None = None, all_shots: bool = False) -> dict:
        if not self.renders_dir.exists():
            return {"status": "error", "message": "No renders found. Run render_shots first."}

        frame_lookup = {f["shot_id"]: f for f in self.manifest.get("frames", [])}
        shots = list(frame_lookup.keys()) if all_shots else ([shot_id] if shot_id else [])

        results = []
        for sid in shots:
            render_dir = self.renders_dir / sid
            if not render_dir.exists():
                results.append({"shot_id": sid, "status": "skipped", "reason": "No render output"})
                continue

            png_files = sorted(render_dir.glob("*.png"))
            if not png_files:
                results.append({"shot_id": sid, "status": "skipped", "reason": "No PNG frames"})
                continue

            source_frame = png_files[0]
            frame_data = frame_lookup.get(sid, {})
            original_prompt = frame_data.get("prompt", "")
            enhanced_prompt = f"{original_prompt}, highly detailed, cinematic lighting, 8k uhd, sharp focus"

            try:
                uploaded_name = upload_image(source_frame)
                width = self.manifest.get("resolution", {}).get("width", 1792)
                height = self.manifest.get("resolution", {}).get("height", 1024)

                workflow = build_img2img_workflow(uploaded_name, enhanced_prompt, self.denoise, width, height)
                queue = comfyui_post("/prompt", {"prompt": workflow, "client_id": f"refiner_{sid}"})
                prompt_id = queue["prompt_id"]

                result = wait_for_result(prompt_id)
                if result["status"] != "ok":
                    results.append({"shot_id": sid, "status": "error", "phase": "generation", "error": result.get("message", "unknown")})
                    continue

                outputs = result["entry"].get("outputs", {})
                saved = []
                for node_id, node_output in outputs.items():
                    for img in node_output.get("images", []):
                        img_data = download_image(img["filename"], img.get("subfolder", ""))
                        out_name = f"{sid}_refined.png"
                        out_path = self.refined_dir / out_name
                        out_path.write_bytes(img_data)
                        saved.append(str(out_path))

                results.append({
                    "shot_id": sid,
                    "status": "ok",
                    "source": str(source_frame),
                    "refined": saved[0] if saved else None,
                    "denoise": self.denoise,
                })

            except Exception as e:
                results.append({"shot_id": sid, "status": "error", "phase": "upload", "error": str(e)})

        return {
            "status": "ok",
            "project": self.project_slug,
            "denoise": self.denoise,
            "results": results,
        }


def main():
    parser = argparse.ArgumentParser(description="Prompt Refiner")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("refine", help="Refine renders via img2img")
    p.add_argument("project_slug")
    p.add_argument("--shot")
    p.add_argument("--all-shots", action="store_true")
    p.add_argument("--denoise", type=float, default=0.4)
    args = parser.parse_args()

    if args.command == "refine":
        refiner = PromptRefiner(args.project_slug, denoise=args.denoise)
        result = refiner.refine(shot_id=args.shot, all_shots=args.all_shots)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
