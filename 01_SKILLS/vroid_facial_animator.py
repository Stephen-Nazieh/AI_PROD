#!/usr/bin/env python3
"""
vroid_facial_animator.py — Phoneme-Based Facial Animation for VRoid/VRM

Maps dialogue text to phoneme timings and generates VRM blend shape keyframes
(A, I, U, E, O, Blink) for lip-sync facial animation.

Usage:
    python vroid_facial_animator.py animate <project_slug> [--shot SC001_SH001]
    python vroid_facial_animator.py animate <project_slug> --all-shots

Phoneme mapping:
    A/AA/AH/AE → A  (mouth open wide)
    I/IH/EY/EE → I  (mouth spread)
    U/UH/OO/OW → U  (mouth pursed)
    E/EH/AY/AO → E  (mouth half-open)
    O/AW/OY/AU → O  (mouth rounded)
    Rest/blink → Neutral + Blink
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"

# Phoneme → VRM blend shape mapping
PHONEME_MAP = {
    "a": "A", "aa": "A", "ah": "A", "ae": "A", "ao": "A",
    "i": "I", "ih": "I", "iy": "I", "ey": "I", "ee": "I",
    "u": "U", "uh": "U", "uw": "U", "oo": "U", "ow": "U",
    "e": "E", "eh": "E", "ay": "E", "er": "E",
    "o": "O", "aw": "O", "oy": "O", "au": "O",
}

BLEND_SHAPES = ["A", "I", "U", "E", "O", "Blink"]


def text_to_phonemes(text: str) -> list[str]:
    """Simple rule-based phoneme estimation from English text."""
    text = text.lower()
    text = re.sub(r"[^a-z\s]", "", text)
    phonemes = []
    for word in text.split():
        i = 0
        while i < len(word):
            # Try 2-letter phonemes first
            if i + 1 < len(word):
                digraph = word[i:i+2]
                if digraph in PHONEME_MAP:
                    phonemes.append(PHONEME_MAP[digraph])
                    i += 2
                    continue
            # Single letter
            char = word[i]
            if char in PHONEME_MAP:
                phonemes.append(PHONEME_MAP[char])
            else:
                phonemes.append("Rest")
            i += 1
        phonemes.append("Rest")  # word boundary
    return phonemes


def distribute_phonemes(phonemes: list[str], duration_sec: float, fps: float = 24.0) -> list[dict]:
    """Distribute phonemes evenly across duration."""
    if not phonemes:
        return []
    total_frames = int(duration_sec * fps)
    frame_per_phoneme = max(1, total_frames // len(phonemes))
    result = []
    frame = 1
    for p in phonemes:
        result.append({"phoneme": p, "frame": frame, "duration": frame_per_phoneme})
        frame += frame_per_phoneme
    return result


def find_vrm_mesh(scene) -> object:
    """Find the first mesh object that likely has VRM blend shapes."""
    import bpy
    for obj in scene.objects:
        if obj.type == "MESH" and obj.data.shape_keys:
            return obj
    return None


class FacialAnimator:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_path = self.project_dir / "03-layout" / "layout.blend"
        self.shot_list = self._load_json(self.project_dir / "01-scripts" / "shot-list.json")

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def animate(self, shot_id: str | None = None, all_shots: bool = False) -> dict:
        import bpy

        if not self.layout_path.exists():
            return {"status": "error", "message": f"Layout not found: {self.layout_path}"}

        bpy.ops.wm.open_mainfile(filepath=str(self.layout_path))
        scene = bpy.context.scene
        fps = scene.render.fps

        vrm_mesh = find_vrm_mesh(scene)
        if not vrm_mesh:
            return {"status": "error", "message": "No VRM mesh with shape keys found in layout"}

        shots = self.shot_list.get("shots", [])
        if shot_id:
            shots = [s for s in shots if s["shot_id"] == shot_id]
        if not all_shots and not shot_id:
            return {"status": "error", "message": "Specify --shot or --all-shots"}

        results = []
        for shot in shots:
            sid = shot["shot_id"]
            dialogue = shot.get("dialogue", "").strip()
            if not dialogue:
                results.append({"shot_id": sid, "status": "skipped", "reason": "No dialogue"})
                continue

            duration = shot.get("duration_seconds", 3.0)
            if duration <= 0:
                duration = 3.0
            frame_start = shot.get("shot_number", 1) * 72  # approximate

            phonemes = text_to_phonemes(dialogue)
            timed = distribute_phonemes(phonemes, duration, fps)

            keyframes_added = 0
            key = vrm_mesh.data.shape_keys
            if not key:
                results.append({"shot_id": sid, "status": "error", "reason": "No shape keys"})
                continue

            # Set all blend shapes to 0 at start
            for shape in key.key_blocks:
                if shape.name in BLEND_SHAPES:
                    shape.value = 0.0
                    shape.keyframe_insert(data_path="value", frame=frame_start)

            for entry in timed:
                frame = frame_start + entry["frame"]
                phoneme = entry["phoneme"]

                # Reset all
                for shape in key.key_blocks:
                    if shape.name in BLEND_SHAPES:
                        shape.value = 0.0
                        shape.keyframe_insert(data_path="value", frame=frame)

                # Activate phoneme blend shape
                if phoneme in BLEND_SHAPES:
                    for shape in key.key_blocks:
                        if shape.name == phoneme:
                            shape.value = 1.0
                            shape.keyframe_insert(data_path="value", frame=frame)
                            keyframes_added += 1

            # Add blink every ~3 seconds
            blink_frame = frame_start
            while blink_frame < frame_start + int(duration * fps):
                blink_frame += int(3.0 * fps)
                if blink_frame < frame_start + int(duration * fps):
                    for shape in key.key_blocks:
                        if shape.name == "Blink":
                            shape.value = 0.0
                            shape.keyframe_insert(data_path="value", frame=blink_frame - 2)
                            shape.value = 1.0
                            shape.keyframe_insert(data_path="value", frame=blink_frame)
                            shape.value = 0.0
                            shape.keyframe_insert(data_path="value", frame=blink_frame + 2)
                            keyframes_added += 3

            results.append({
                "shot_id": sid,
                "status": "ok",
                "phonemes": len(phonemes),
                "keyframes": keyframes_added,
                "dialogue": dialogue[:60],
            })

        bpy.ops.wm.save_as_mainfile(filepath=str(self.layout_path))
        return {
            "status": "ok",
            "project": self.project_slug,
            "vrm_mesh": vrm_mesh.name,
            "results": results,
        }


def run_inside_blender():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="VRoid Facial Animator")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("animate", help="Animate facial blend shapes")
    p.add_argument("project_slug")
    p.add_argument("--shot")
    p.add_argument("--all-shots", action="store_true")
    args = parser.parse_args(argv)

    animator = FacialAnimator(args.project_slug)
    result = animator.animate(shot_id=args.shot, all_shots=args.all_shots)
    print(json.dumps(result, indent=2))


def run_outside_blender():
    parser = argparse.ArgumentParser(description="VRoid Facial Animator")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("animate", help="Animate facial blend shapes")
    p.add_argument("project_slug")
    p.add_argument("--shot")
    p.add_argument("--all-shots", action="store_true")
    args = parser.parse_args()
    script_path = Path(__file__).resolve()
    cmd = [BLENDER_BINARY, "--background", "--python", str(script_path), "--", "animate", args.project_slug]
    if args.shot:
        cmd.extend(["--shot", args.shot])
    if args.all_shots:
        cmd.append("--all-shots")
    print(f"🎭 Animating facial blend shapes for {args.project_slug}...")
    subprocess.run(cmd, check=True)


def main():
    try:
        import bpy
        run_inside_blender()
    except ImportError:
        run_outside_blender()


if __name__ == "__main__":
    main()
