#!/usr/bin/env python3
"""
ComfyUI client — render images via the local ComfyUI server (:8188) using a
minimal SDXL text-to-image graph. Used by the A/B thumbnail seam.

    comfyui_client render "<prompt>" <out.png> [--width 1280 --height 720]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.request

COMFY = "http://127.0.0.1:8188"
CHECKPOINT = "sd_xl_base_1.0.safetensors"
NEG = "text, watermark, logo, blurry, low quality, deformed, extra limbs"


def _post(path, payload):
    req = urllib.request.Request(f"{COMFY}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _get(path, timeout=30):
    with urllib.request.urlopen(f"{COMFY}{path}", timeout=timeout) as r:
        return r.read()


def _workflow(prompt: str, width: int, height: int, seed: int) -> dict:
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["4", 1]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": 25, "cfg": 7.0, "sampler_name": "euler",
            "scheduler": "normal", "denoise": 1.0,
            "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "dpm_thumb", "images": ["8", 0]}},
    }


def render(prompt: str, out_path: str, width: int = 1280, height: int = 720,
           seed: int = 0, wait: int = 180) -> str:
    pid = _post("/prompt", {"prompt": _workflow(prompt, width, height, seed)})["prompt_id"]
    deadline = time.time() + wait
    while time.time() < deadline:
        hist = json.loads(_get(f"/history/{pid}").decode())
        if pid in hist:
            outs = hist[pid].get("outputs", {})
            imgs = outs.get("9", {}).get("images", [])
            if imgs:
                img = imgs[0]
                data = _get(f"/view?filename={img['filename']}&subfolder={img.get('subfolder','')}&type={img.get('type','output')}")
                p = pathlib.Path(out_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                return out_path
        time.sleep(2)
    raise TimeoutError(f"ComfyUI render did not finish within {wait}s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="comfyui_client")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("render")
    pr.add_argument("prompt"); pr.add_argument("out")
    pr.add_argument("--width", type=int, default=1280); pr.add_argument("--height", type=int, default=720)
    pr.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    if a.cmd == "render":
        print("  " + render(a.prompt, a.out, a.width, a.height, a.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
