#!/usr/bin/env python3
"""
logic_pro_scorer.py — Mood-Matched Music Scoring

NOTE: despite the name, this does NOT drive Apple Logic Pro (which is GUI-only and
can't be scripted headlessly). It is an ffmpeg-based scorer: it maps scene headings
to moods, then either trims/loops a matching stem from the library OR, when no
licensed stem exists for a mood, synthesizes a royalty-free ambient bed in-process
(see synthesize_music_bed). The name is retained for pipeline/gateway compatibility.

Usage:
    python logic_pro_scorer.py score <project_slug> [--scene SC001]
    python logic_pro_scorer.py score <project_slug> --all-scenes
    python logic_pro_scorer.py init-library

Mood detection:
    INT. CLASSROOM - DAY     → calm, academic, ambient
    EXT. PARK - DAY          → upbeat, nature, peaceful
    INT. OFFICE - NIGHT      → tense, dramatic, suspense
    EXT. CITY - NIGHT        → energetic, urban, dark
"""

import argparse
import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
MUSIC_LIBRARY = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "music-stems"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
SR = 44100

# Mood → (chord root Hz, is_major). Drives the procedural ambient bed used when no
# licensed stem exists for a mood — minor/low for tense/dark, major/higher for calm.
MOOD_TONE = {
    "dark": (110.0, False), "tense": (123.5, False), "suspense": (110.0, False),
    "dramatic": (146.8, False), "sad": (130.8, False), "sterile": (220.0, False),
    "urban": (98.0, False), "gritty": (98.0, False), "nocturnal": (110.0, False),
    "calm": (130.8, True), "peaceful": (146.8, True), "academic": (174.6, True),
    "warm": (130.8, True), "intimate": (146.8, True), "upbeat": (164.8, True),
    "bright": (196.0, True), "energetic": (164.8, True), "nature": (146.8, True),
    "light": (174.6, True), "professional": (146.8, True),
    "neutral": (146.8, True), "ambient": (130.8, True),
}


def synthesize_music_bed(moods: list[str], duration: float, out_path: Path) -> Path:
    """Synthesize a mood-matched ambient music bed (chord pad + slow tremolo).

    Self-contained numpy synthesis so the music stage produces real, royalty-free
    audio even with an empty stem library. Kept low (-13 dBFS-ish) to sit under
    dialogue. Mirrors sound_designer's synth-fallback approach.
    """
    duration = max(2.0, float(duration))
    root, major = next(((MOOD_TONE[m]) for m in moods if m in MOOD_TONE), (146.8, True))
    third = 4 if major else 3
    chord = [root, root * 2 ** (third / 12), root * 2 ** (7 / 12), root * 2]
    n = int(SR * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    sig = np.zeros(n, dtype=np.float64)
    for k, f in enumerate(chord):
        detune = 1.0 + 0.002 * (k - 1)                      # subtle chorus
        voice = np.sin(2 * np.pi * f * detune * t)
        voice += 0.3 * np.sin(2 * np.pi * 2 * f * detune * t)  # 2nd-harmonic warmth
        sig += voice / (k + 2)                              # higher notes quieter
    sig *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.12 * t)        # slow tremolo LFO
    sig /= np.max(np.abs(sig)) + 1e-9
    sig *= 0.22                                             # headroom under VO
    fade = int(SR * 1.0)
    if n > 2 * fade:
        sig[:fade] *= np.linspace(0, 1, fade)
        sig[-fade:] *= np.linspace(1, 0, fade)
    sf.write(str(out_path), np.stack([sig, sig], axis=-1).astype(np.float32), SR)
    return out_path


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# Scene heading → mood keywords
MOOD_RULES = [
    ("night", ["dark", "tense", "suspense", "nocturnal"]),
    ("day", ["bright", "upbeat", "peaceful", "energetic"]),
    ("classroom", ["calm", "academic", "light"]),
    ("office", ["tense", "professional", "neutral"]),
    ("park", ["peaceful", "nature", "upbeat"]),
    ("city", ["energetic", "urban", "dark"]),
    ("home", ["warm", "calm", "intimate"]),
    ("hospital", ["tense", "sad", "sterile"]),
    ("street", ["urban", "energetic", "gritty"]),
]


def detect_mood(heading: str) -> list[str]:
    """Extract mood keywords from a scene heading."""
    heading = heading.lower()
    moods = set()
    for keyword, mood_list in MOOD_RULES:
        if keyword in heading:
            moods.update(mood_list)
    if not moods:
        moods = ["neutral", "ambient"]
    return list(moods)


def init_library() -> dict:
    """Create music stem library structure."""
    MUSIC_LIBRARY.mkdir(parents=True, exist_ok=True)
    moods = ["calm", "academic", "upbeat", "peaceful", "tense", "dramatic", "suspense", "energetic", "urban", "dark", "warm", "intimate", "neutral", "ambient"]
    for mood in moods:
        (MUSIC_LIBRARY / mood).mkdir(exist_ok=True)

    manifest = {
        "version": 1,
        "moods": {mood: [] for mood in moods},
        "note": "Place WAV/MP3 stem files into mood folders. Files are auto-selected by scene heading.",
    }
    manifest_path = MUSIC_LIBRARY / "library_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "library_dir": str(MUSIC_LIBRARY),
        "moods_created": len(moods),
        "message": "Music library initialized. Add stems to mood folders.",
    }


def list_stems() -> dict:
    manifest = _load_json(MUSIC_LIBRARY / "library_manifest.json")
    available = {}
    for mood_dir in sorted(MUSIC_LIBRARY.iterdir()):
        if mood_dir.is_dir() and mood_dir.name != "__pycache__":
            stems = [f.name for f in mood_dir.glob("*.wav")] + [f.name for f in mood_dir.glob("*.mp3")]
            if stems:
                available[mood_dir.name] = stems
    return {"status": "ok", "moods": available, "total_stems": sum(len(v) for v in available.values())}


def select_stem(moods: list[str]) -> Path | None:
    """Pick a random stem matching one of the moods."""
    for mood in moods:
        mood_dir = MUSIC_LIBRARY / mood
        if mood_dir.exists():
            stems = list(mood_dir.glob("*.wav")) + list(mood_dir.glob("*.mp3"))
            if stems:
                return random.choice(stems)
    return None


class MusicScorer:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.shot_list = _load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.music_dir = self.project_dir / "06-audio" / "music"
        self.music_dir.mkdir(parents=True, exist_ok=True)

    def score(self, scene_id: str | None = None, all_scenes: bool = False) -> dict:
        scenes = self.shot_list.get("scenes", [])
        if scene_id:
            scenes = [s for s in scenes if s["scene_id"] == scene_id]
        if not all_scenes and not scene_id:
            return {"status": "error", "message": "Specify --scene or --all-scenes"}

        results = []
        for scene in scenes:
            sid = scene["scene_id"]
            heading = scene.get("heading", "")
            moods = detect_mood(heading)
            stem = select_stem(moods)

            output_path = self.music_dir / f"{sid}_music.wav"
            duration = scene.get("shot_count", 3) * 3.0  # ~3 sec per shot

            try:
                if stem:
                    # Trim/loop a real library stem to target duration with a fade-out.
                    subprocess.run([
                        FFMPEG, "-y", "-i", str(stem),
                        "-t", str(duration),
                        "-af", "afade=t=out:st={}:d=1.0".format(max(0, duration - 1.0)),
                        "-ar", "44100", "-ac", "2",
                        str(output_path),
                    ], check=True, capture_output=True, timeout=60)
                    source = str(stem)
                else:
                    # No licensed stem for this mood → synthesize an ambient bed.
                    synthesize_music_bed(moods, duration, output_path)
                    source = "procedural-synth"

                results.append({
                    "scene_id": sid,
                    "status": "ok",
                    "heading": heading,
                    "moods": moods,
                    "source_stem": source,
                    "output": str(output_path),
                    "duration": duration,
                })
            except Exception as e:
                results.append({"scene_id": sid, "status": "error", "error": str(e)})

        return {
            "status": "ok",
            "project": self.project_slug,
            "music_dir": str(self.music_dir),
            "results": results,
        }


def main():
    parser = argparse.ArgumentParser(description="Logic Pro Music Scorer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-library", help="Create music stem library")

    p_score = sub.add_parser("score", help="Score scenes with music")
    p_score.add_argument("project_slug")
    p_score.add_argument("--scene")
    p_score.add_argument("--all-scenes", action="store_true")

    p_list = sub.add_parser("list", help="List available stems")

    args = parser.parse_args()

    if args.command == "init-library":
        result = init_library()
        print(json.dumps(result, indent=2))
    elif args.command == "score":
        scorer = MusicScorer(args.project_slug)
        result = scorer.score(scene_id=args.scene, all_scenes=args.all_scenes)
        print(json.dumps(result, indent=2))
    elif args.command == "list":
        result = list_stems()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
