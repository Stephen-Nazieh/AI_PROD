#!/usr/bin/env python3
"""
quality_gate.py — Automated Render Quality Assessment

Analyzes rendered frames for sharpness, contrast, brightness, and noise.
Flags low-quality shots and optionally triggers automatic re-render with
adjusted settings.

Usage:
    python quality_gate.py check <project_slug> [--shot SC001_SH001]
    python quality_gate.py check <project_slug> --all-shots --re-render
    python quality_gate.py benchmark <project_slug>

Metrics:
    - Sharpness: Laplacian variance (edge detection)
    - Contrast: Standard deviation of luminance
    - Brightness: Mean luminance
    - Noise: High-frequency component energy
"""

import argparse
import json
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageStat

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
RENDERS_DIR = "04-raw_renders"

# Quality thresholds
THRESHOLDS = {
    "sharpness": {"min": 50.0, "ideal": 200.0},
    "contrast": {"min": 30.0, "ideal": 80.0},
    "brightness": {"min": 20.0, "max": 240.0, "ideal": 128.0},
    "noise": {"max": 15.0, "ideal": 5.0},
}


def analyze_image(image_path: Path) -> dict:
    """Compute quality metrics for a single image."""
    img = Image.open(image_path).convert("L")  # grayscale
    arr = np.array(img, dtype=np.float32)

    # Sharpness: Laplacian variance
    # Approximate with edge filter
    edges = img.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.array(edges, dtype=np.float32)
    sharpness = float(np.var(edge_arr))

    # Contrast: std dev
    contrast = float(np.std(arr))

    # Brightness: mean
    brightness = float(np.mean(arr))

    # Noise: high-frequency energy (difference from blurred)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
    blur_arr = np.array(blurred, dtype=np.float32)
    noise = float(np.std(arr - blur_arr))

    return {
        "sharpness": round(sharpness, 2),
        "contrast": round(contrast, 2),
        "brightness": round(brightness, 2),
        "noise": round(noise, 2),
    }


def score_metrics(metrics: dict) -> dict:
    """Score metrics against thresholds."""
    scores = {}
    passed = True

    # Sharpness
    s = metrics["sharpness"]
    if s < THRESHOLDS["sharpness"]["min"]:
        scores["sharpness"] = {"status": "fail", "value": s, "reason": f"Too blurry (< {THRESHOLDS['sharpness']['min']})"}
        passed = False
    elif s < THRESHOLDS["sharpness"]["ideal"] * 0.5:
        scores["sharpness"] = {"status": "warn", "value": s, "reason": "Slightly soft"}
    else:
        scores["sharpness"] = {"status": "pass", "value": s}

    # Contrast
    c = metrics["contrast"]
    if c < THRESHOLDS["contrast"]["min"]:
        scores["contrast"] = {"status": "fail", "value": c, "reason": f"Too flat (< {THRESHOLDS['contrast']['min']})"}
        passed = False
    else:
        scores["contrast"] = {"status": "pass", "value": c}

    # Brightness
    b = metrics["brightness"]
    if b < THRESHOLDS["brightness"]["min"] or b > THRESHOLDS["brightness"]["max"]:
        scores["brightness"] = {"status": "fail", "value": b, "reason": f"Out of range ({THRESHOLDS['brightness']['min']}-{THRESHOLDS['brightness']['max']})"}
        passed = False
    else:
        scores["brightness"] = {"status": "pass", "value": b}

    # Noise
    n = metrics["noise"]
    if n > THRESHOLDS["noise"]["max"]:
        scores["noise"] = {"status": "fail", "value": n, "reason": f"Too noisy (> {THRESHOLDS['noise']['max']})"}
        passed = False
    else:
        scores["noise"] = {"status": "pass", "value": n}

    scores["overall"] = "pass" if passed else "fail"
    return scores


class QualityGate:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.renders_dir = self.project_dir / RENDERS_DIR

    def check(self, shot_id: str | None = None, all_shots: bool = False, re_render: bool = False) -> dict:
        if not self.renders_dir.exists():
            return {"status": "error", "message": f"No renders found: {self.renders_dir}"}

        shots_to_check = []
        for shot_dir in sorted(self.renders_dir.iterdir()):
            if shot_dir.is_dir():
                sid = shot_dir.name
                if shot_id and sid != shot_id:
                    continue
                pngs = sorted(shot_dir.glob("*.png"))
                if pngs:
                    shots_to_check.append((sid, pngs[0]))

        if not all_shots and not shot_id:
            return {"status": "error", "message": "Specify --shot or --all-shots"}

        results = []
        failed_shots = []

        for sid, png_path in shots_to_check:
            metrics = analyze_image(png_path)
            scores = score_metrics(metrics)

            result = {
                "shot_id": sid,
                "frame": str(png_path),
                "metrics": metrics,
                "scores": scores,
                "passed": scores["overall"] == "pass",
            }
            results.append(result)

            if not result["passed"]:
                failed_shots.append(sid)

        # Trigger re-render if requested
        re_render_result = None
        if re_render and failed_shots:
            print(f"\n🔄 Re-rendering {len(failed_shots)} failed shots with higher quality...")
            re_render_result = self._re_render(failed_shots)

        return {
            "status": "ok",
            "project": self.project_slug,
            "total_checked": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
            "failed_shots": failed_shots,
            "results": results,
            "re_render": re_render_result,
        }

    def benchmark(self) -> dict:
        """Compute average metrics across all rendered frames."""
        if not self.renders_dir.exists():
            return {"status": "error", "message": "No renders found"}

        all_metrics = []
        for shot_dir in sorted(self.renders_dir.iterdir()):
            if shot_dir.is_dir():
                for png in shot_dir.glob("*.png"):
                    all_metrics.append(analyze_image(png))

        if not all_metrics:
            return {"status": "error", "message": "No PNG frames found"}

        avg = {
            "sharpness": round(sum(m["sharpness"] for m in all_metrics) / len(all_metrics), 2),
            "contrast": round(sum(m["contrast"] for m in all_metrics) / len(all_metrics), 2),
            "brightness": round(sum(m["brightness"] for m in all_metrics) / len(all_metrics), 2),
            "noise": round(sum(m["noise"] for m in all_metrics) / len(all_metrics), 2),
        }

        return {
            "status": "ok",
            "project": self.project_slug,
            "total_frames": len(all_metrics),
            "averages": avg,
            "thresholds": THRESHOLDS,
        }

    def _re_render(self, shot_ids: list[str]) -> dict:
        """Trigger re-render with higher quality settings."""
        python = WORKSPACE_ROOT / "env" / "bin" / "python3"
        script = WORKSPACE_ROOT / "01_SKILLS" / "blender_render_dispatcher.py"
        cmd = [
            str(python), str(script), "render", self.project_slug,
            "--engine", "cycles",
            "--shots", ",".join(shot_ids),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "shots": shot_ids,
            "output": result.stdout,
            "errors": result.stderr if result.returncode != 0 else "",
        }


def main():
    parser = argparse.ArgumentParser(description="Quality Gate")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Check render quality")
    p_check.add_argument("project_slug")
    p_check.add_argument("--shot")
    p_check.add_argument("--all-shots", action="store_true")
    p_check.add_argument("--re-render", action="store_true", help="Auto re-render failed shots in Cycles")

    p_bench = sub.add_parser("benchmark", help="Benchmark all renders")
    p_bench.add_argument("project_slug")

    args = parser.parse_args()
    gate = QualityGate(args.project_slug)

    if args.command == "check":
        result = gate.check(shot_id=args.shot, all_shots=args.all_shots, re_render=args.re_render)
        print(json.dumps(result, indent=2))
    elif args.command == "benchmark":
        result = gate.benchmark()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
