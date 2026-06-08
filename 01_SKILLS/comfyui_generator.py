#!/usr/bin/env python3
"""
comfyui_generator.py — ComfyUI API Wrapper for DeParadigm Media

Generate images via ComfyUI's REST API using SDXL Base or Flux-dev.
Handles workflow construction, queue submission, and result polling.

Models required:
  SDXL Base:
    - models/checkpoints/sd_xl_base_1.0.safetensors
  Flux-dev (requires additional models):
    - models/checkpoints/flux1-dev.safetensors
    - models/clip/clip_l.safetensors
    - models/clip/t5xxl_fp8_e4m3fn.safetensors (or text_encoders/)
    - models/vae/ae.safetensors

Env:
  COMFYUI_URL — default: http://127.0.0.1:8188
"""

import argparse
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


# ── Workflow builders ───────────────────────────────────────────────────────

def build_sdxl_workflow(
    prompt: str,
    checkpoint: str = "sd_xl_base_1.0.safetensors",
    width: int = 1024,
    height: int = 1024,
    steps: int = 30,
    cfg: float = 7.0,
    seed: int = None,
) -> dict:
    """Build a txt2img workflow for SDXL Base."""
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    return {
        "1": {
            "inputs": {"ckpt_name": checkpoint},
            "class_type": "CheckpointLoaderSimple",
        },
        "2": {
            "inputs": {"text": prompt, "clip": ["1", 1]},
            "class_type": "CLIPTextEncode",
        },
        "3": {
            "inputs": {"text": "", "clip": ["1", 1]},
            "class_type": "CLIPTextEncode",
        },
        "4": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
            "class_type": "EmptyLatentImage",
        },
        "5": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
            "class_type": "KSampler",
        },
        "6": {
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            "class_type": "VAEDecode",
        },
        "7": {
            "inputs": {"filename_prefix": "sdxl", "images": ["6", 0]},
            "class_type": "SaveImage",
        },
    }


def build_flux_workflow(
    prompt: str,
    unet_name: str = "flux1-dev.safetensors",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    guidance: float = 3.5,
    seed: int = None,
) -> dict:
    """Build a txt2img workflow for Flux-dev (requires CLIP + T5 + VAE)."""
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    return {
        "1": {
            "inputs": {"ckpt_name": "flux1-dev.safetensors"},
            "class_type": "CheckpointLoaderSimple",
        },
        "2": {
            "inputs": {
                "clip_name1": "clip_l.safetensors",
                "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
                "type": "flux",
            },
            "class_type": "DualCLIPLoader",
        },
        "3": {
            "inputs": {"vae_name": "ae.safetensors"},
            "class_type": "VAELoader",
        },
        "4": {
            "inputs": {"text": prompt, "clip": ["2", 0]},
            "class_type": "CLIPTextEncode",
        },
        "5": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
            "class_type": "EmptySD3LatentImage",
        },
        "6": {
            "inputs": {
                "max_shift": 1.15,
                "base_shift": 0.5,
                "width": width,
                "height": height,
                "model": ["1", 0],
            },
            "class_type": "ModelSamplingFlux",
        },
        "7": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["6", 0],
                "positive": ["4", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
        },
        "8": {
            "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
            "class_type": "VAEDecode",
        },
        "9": {
            "inputs": {"filename_prefix": "flux", "images": ["8", 0]},
            "class_type": "SaveImage",
        },
    }


# ── API client ──────────────────────────────────────────────────────────────

class ComfyUIClient:
    def __init__(self, base_url: str = DEFAULT_URL):
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    def _post(self, path: str, payload: dict) -> dict:
        resp = requests.post(
            f"{self.base_url}{path}", json=payload, timeout=60
        )
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        resp = requests.get(f"{self.base_url}{path}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def queue_prompt(self, workflow: dict) -> dict:
        """Submit a workflow to the ComfyUI queue."""
        payload = {"prompt": workflow, "client_id": self.client_id}
        return self._post("/prompt", payload)

    def get_history(self, prompt_id: str) -> dict:
        """Get execution history for a prompt."""
        return self._get(f"/history/{prompt_id}")

    def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """Download a generated image."""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        resp = requests.get(f"{self.base_url}/view", params=params, timeout=60)
        resp.raise_for_status()
        return resp.content

    def wait_for_result(
        self, prompt_id: str, timeout: int = 300, poll_interval: float = 2.0
    ) -> dict:
        """Poll until generation completes or fails."""
        start = time.time()
        while time.time() - start < timeout:
            history = self.get_history(prompt_id)
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "success":
                    return {"status": "ok", "entry": entry}
                elif status.get("completed") and status.get("status_str") != "success":
                    return {"status": "error", "message": f"Generation failed: {status}", "entry": entry}
            time.sleep(poll_interval)
        return {"status": "timeout", "message": f"Timed out after {timeout}s"}

    def generate(
        self,
        prompt: str,
        model: str = "sdxl",
        width: int = 1024,
        height: int = 1024,
        steps: int = None,
        output_dir: str = None,
        seed: int = None,
    ) -> dict:
        """
        End-to-end generate: build workflow → queue → poll → download.

        Args:
            prompt: Text prompt.
            model: "sdxl" or "flux".
            width/height: Output dimensions.
            steps: Sampling steps (default: 30 for SDXL, 20 for Flux).
            output_dir: Where to save the image (default: ComfyUI output).
            seed: Fixed seed for reproducibility.

        Returns:
            Structured result with image path and metadata.
        """
        if model == "sdxl":
            workflow = build_sdxl_workflow(
                prompt, width=width, height=height,
                steps=steps or 30, seed=seed,
            )
        elif model == "flux":
            workflow = build_flux_workflow(
                prompt, width=width, height=height,
                steps=steps or 20, seed=seed,
            )
        else:
            return {"status": "error", "message": f"Unknown model: {model}. Use 'sdxl' or 'flux'."}

        # Submit
        queue_result = self.queue_prompt(workflow)
        prompt_id = queue_result.get("prompt_id")
        if not prompt_id:
            return {"status": "error", "message": "No prompt_id returned", "data": queue_result}

        # Poll
        result = self.wait_for_result(prompt_id)
        if result["status"] != "ok":
            return result

        # Extract output filenames
        outputs = result["entry"].get("outputs", {})
        images = []
        for node_id, node_output in outputs.items():
            for img in node_output.get("images", []):
                filename = img["filename"]
                subfolder = img.get("subfolder", "")
                images.append({"filename": filename, "subfolder": subfolder})

        # Download
        saved_paths = []
        out_dir = Path(output_dir) if output_dir else WORKSPACE_ROOT / "06_SHARED_ASSETS" / "ai-generated"
        out_dir.mkdir(parents=True, exist_ok=True)

        for img_info in images:
            img_data = self.get_image(img_info["filename"], img_info["subfolder"])
            ext = Path(img_info["filename"]).suffix or ".png"
            out_name = f"{model}_{int(time.time())}_{random.randint(1000,9999)}{ext}"
            out_path = out_dir / out_name
            out_path.write_bytes(img_data)
            saved_paths.append(str(out_path))

        return {
            "status": "ok",
            "prompt_id": prompt_id,
            "model": model,
            "prompt": prompt,
            "images": saved_paths,
            "message": f"Generated {len(saved_paths)} image(s) with {model}",
        }

    def list_models(self, model_type: str = "checkpoints") -> list:
        """List available models of a given type."""
        try:
            resp = self._get(f"/object_info/CheckpointLoaderSimple")
            inputs = resp.get("CheckpointLoaderSimple", {}).get("input", {})
            required = inputs.get("required", {})
            ckpt_input = required.get("ckpt_name", [[]])
            return ckpt_input[0] if ckpt_input else []
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ComfyUI Image Generator")
    parser.add_argument("prompt", help="Text prompt for image generation")
    parser.add_argument("--model", choices=["sdxl", "flux"], default="sdxl", help="Model to use")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--url", default=DEFAULT_URL, help="ComfyUI base URL")
    parser.add_argument("--list-models", action="store_true", help="List available checkpoints")
    args = parser.parse_args()

    client = ComfyUIClient(args.url)

    if args.list_models:
        models = client.list_models()
        print("Available checkpoints:")
        for m in models:
            print(f"  {m}")
        return

    result = client.generate(
        prompt=args.prompt,
        model=args.model,
        width=args.width,
        height=args.height,
        steps=args.steps,
        seed=args.seed,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
