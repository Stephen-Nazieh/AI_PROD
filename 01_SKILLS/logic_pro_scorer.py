#!/usr/bin/env python3
"""
logic_pro_scorer.py — Mood-Matched Music Scoring

Maps scene headings to emotional moods, selects appropriate music stems from
a template library, and auto-assembles a soundtrack using ffmpeg.

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
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
MUSIC_LIBRARY = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "music-stems"
FFMPEG = "/opt/homebrew/bin/ffmpeg"


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

            if not stem:
                results.append({"scene_id": sid, "status": "skipped", "reason": "No matching music stems", "moods": moods})
                continue

            output_path = self.music_dir / f"{sid}_music.wav"
            duration = scene.get("shot_count", 3) * 3.0  # ~3 sec per shot

            try:
                # Use ffmpeg to trim/loop stem to target duration
                subprocess.run([
                    FFMPEG, "-y", "-i", str(stem),
                    "-t", str(duration),
                    "-af", "afade=t=out:st={}:d=1.0".format(max(0, duration - 1.0)),
                    "-ar", "44100", "-ac", "2",
                    str(output_path),
                ], check=True, capture_output=True, timeout=60)

                results.append({
                    "scene_id": sid,
                    "status": "ok",
                    "heading": heading,
                    "moods": moods,
                    "source_stem": str(stem),
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
