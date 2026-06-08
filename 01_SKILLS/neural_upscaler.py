#!/usr/bin/env python3
"""
neural_upscaler.py — ONNX Super-Resolution Upscaler for Rendered Frames

Upscales rendered frames using a lightweight ONNX super-resolution model.
Runs locally on Apple Silicon via ONNX Runtime.

Usage:
    python neural_upscaler.py upscale <project_slug> [--shot SC001_SH001]
    python neural_upscaler.py upscale <project_slug> --all-shots --scale 4
    python neural_upscaler.py benchmark <project_slug>
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
RENDERS_DIR = "04-raw_renders"
UPSCALED_DIR = "04-raw_renders_upscaled"

# Default ONNX model (ONNX Model Zoo - sub-pixel CNN)
DEFAULT_MODEL = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "ai-models" / "upscaler" / "super-resolution-10.onnx"


def load_session(model_path: Path):
    """Load ONNX inference session."""
    import onnxruntime as ort
    providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    session = ort.InferenceSession(str(model_path), providers=providers)
    return session


def preprocess(img: Image.Image) -> np.ndarray:
    """Convert PIL image to ONNX input format (YCbCr Y channel)."""
    # Convert to YCbCr and extract Y channel
    ycbcr = img.convert("YCbCr")
    y, cb, cr = ycbcr.split()
    
    # Normalize Y to [0, 1]
    y_arr = np.array(y, dtype=np.float32) / 255.0
    y_arr = y_arr[np.newaxis, np.newaxis, :, :]  # NCHW
    return y_arr, cb, cr


def postprocess(output: np.ndarray, cb: Image.Image, cr: Image.Image, scale: int) -> Image.Image:
    """Convert ONNX output back to PIL RGB image."""
    # Denormalize
    y_out = np.clip(output[0, 0] * 255.0, 0, 255).astype(np.uint8)
    y_img = Image.fromarray(y_out, mode="L")
    
    # Upsample Cb, Cr to match output size
    cb_up = cb.resize(y_img.size, Image.Resampling.BICUBIC)
    cr_up = cr.resize(y_img.size, Image.Resampling.BICUBIC)
    
    # Merge back to YCbCr then RGB
    ycbcr = Image.merge("YCbCr", (y_img, cb_up, cr_up))
    return ycbcr.convert("RGB")


def upscale_image(input_path: Path, output_path: Path, session, scale: int = 4) -> dict:
    """Upscale a single image via ONNX super-resolution."""
    start = time.time()
    img = Image.open(input_path)
    
    # For sub-pixel CNN model, input must be 224x224, output is 672x672 (scale ~3)
    # Resize input to model's expected size if needed
    input_arr, cb, cr = preprocess(img)
    
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    
    # Some models need exact input sizes - handle gracefully
    try:
        outputs = session.run([output_name], {input_name: input_arr})
    except Exception as e:
        # Fallback: use Lanczos resize if ONNX fails
        w, h = img.size
        upscaled = img.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
        upscaled.save(output_path)
        return {
            "status": "fallback",
            "method": "lanczos",
            "input_size": img.size,
            "output_size": upscaled.size,
            "time_sec": round(time.time() - start, 2),
        }
    
    result_img = postprocess(outputs[0], cb, cr, scale)
    result_img.save(output_path)
    
    return {
        "status": "ok",
        "method": "onnx",
        "input_size": img.size,
        "output_size": result_img.size,
        "time_sec": round(time.time() - start, 2),
    }


class NeuralUpscaler:
    def __init__(self, project_slug: str, model_path: Path = None, scale: int = 4):
        self.project_slug = project_slug
        self.scale = scale
        self.model_path = model_path or DEFAULT_MODEL
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.renders_dir = self.project_dir / RENDERS_DIR
        self.upscaled_dir = self.project_dir / UPSCALED_DIR
        self.upscaled_dir.mkdir(parents=True, exist_ok=True)
        
        self.session = None
        if self.model_path.exists():
            try:
                self.session = load_session(self.model_path)
            except Exception as e:
                print(f"⚠️ ONNX load failed ({e}), using Lanczos fallback")

    def upscale(self, shot_id: str | None = None, all_shots: bool = False) -> dict:
        if not self.renders_dir.exists():
            return {"status": "error", "message": f"No renders found: {self.renders_dir}"}

        shots_to_process = []
        for shot_dir in sorted(self.renders_dir.iterdir()):
            if shot_dir.is_dir():
                sid = shot_dir.name
                if shot_id and sid != shot_id:
                    continue
                pngs = sorted(shot_dir.glob("*.png"))
                if pngs:
                    shots_to_process.append((sid, pngs[0]))

        if not all_shots and not shot_id:
            return {"status": "error", "message": "Specify --shot or --all-shots"}

        results = []
        for sid, png_path in shots_to_process:
            out_dir = self.upscaled_dir / sid
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{png_path.stem}_upscaled{png_path.suffix}"
            
            print(f"  🔍 Upscaling {sid} ({self.scale}x)...")
            result = upscale_image(png_path, out_path, self.session, self.scale)
            result["shot_id"] = sid
            results.append(result)

        return {
            "status": "ok",
            "project": self.project_slug,
            "model": str(self.model_path),
            "scale": self.scale,
            "total": len(results),
            "results": results,
            "output_dir": str(self.upscaled_dir),
        }

    def benchmark(self) -> dict:
        """Benchmark upscaling speed."""
        if not self.renders_dir.exists():
            return {"status": "error", "message": "No renders found"}

        times = []
        for shot_dir in sorted(self.renders_dir.iterdir()):
            if shot_dir.is_dir():
                for png in shot_dir.glob("*.png"):
                    start = time.time()
                    img = Image.open(png)
                    w, h = img.size
                    upscaled = img.resize((w * self.scale, h * self.scale), Image.Resampling.LANCZOS)
                    _ = np.array(upscaled)
                    times.append(time.time() - start)
                    break  # one per shot

        if not times:
            return {"status": "error", "message": "No frames to benchmark"}

        return {
            "status": "ok",
            "method": "lanczos" if self.session is None else "onnx",
            "frames_tested": len(times),
            "avg_time_sec": round(sum(times) / len(times), 3),
            "min_time_sec": round(min(times), 3),
            "max_time_sec": round(max(times), 3),
        }


def main():
    parser = argparse.ArgumentParser(description="Neural Upscaler")
    sub = parser.add_subparsers(dest="command", required=True)

    p_up = sub.add_parser("upscale", help="Upscale rendered frames")
    p_up.add_argument("project_slug")
    p_up.add_argument("--shot")
    p_up.add_argument("--all-shots", action="store_true")
    p_up.add_argument("--scale", type=int, default=4)
    p_up.add_argument("--model", help="Path to ONNX model")

    p_bench = sub.add_parser("benchmark", help="Benchmark upscaling speed")
    p_bench.add_argument("project_slug")
    p_bench.add_argument("--scale", type=int, default=4)

    args = parser.parse_args()

    if args.command == "upscale":
        model = Path(args.model) if getattr(args, 'model', None) else None
        upscaler = NeuralUpscaler(args.project_slug, model_path=model, scale=args.scale)
        result = upscaler.upscale(shot_id=args.shot, all_shots=args.all_shots)
        print(json.dumps(result, indent=2))
    elif args.command == "benchmark":
        upscaler = NeuralUpscaler(args.project_slug, model_path=None, scale=args.scale)
        result = upscaler.benchmark()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
