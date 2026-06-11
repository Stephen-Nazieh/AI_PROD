#!/usr/bin/env python3
"""
auto_dubbing_pipeline.py — Full Auto-Dubbing: TTS → Audio → Phoneme Timing → Facial Animation

Generates dialogue audio for every shot, estimates phoneme timings, and
applies VRM blend shape keyframes for lip-sync facial animation.

Usage:
    python auto_dubbing_pipeline.py dub <project_slug> [--shot SC001_SH001]
    python auto_dubbing_pipeline.py dub <project_slug> --all-shots
    python auto_dubbing_pipeline.py dub <project_slug> --engine kokoro --voice af_sarah

Pipeline:
    shot-list.json dialogue
        → Kokoro TTS (fast) or OpenVoice clone (character-specific)
        → WAV file in 06-audio/dialogue/
        → phoneme timing estimation
        → Blender VRM blend shape keyframes
"""

import argparse
import json
import math
import os
import subprocess
import sys
import wave
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "01_SKILLS"))
try:
    from render_cache import RenderCache  # content-addressed skip-rerender
except Exception:  # cache is optional — never block dubbing if it can't import
    RenderCache = None
BLENDER_BINARY = "/Applications/Blender.app/Contents/MacOS/Blender"
KOKORO_SCRIPT = WORKSPACE_ROOT / "01_SKILLS" / "kokoro_tts.py"
OPENVoice_SCRIPT = WORKSPACE_ROOT / "01_SKILLS" / "openvoice_cloner.py"

# Phoneme mapping (simplified English)
PHONEME_MAP = {
    "a": "A", "e": "E", "i": "I", "o": "O", "u": "U",
    "y": "I", "w": "U",
}
BLEND_SHAPES = ["A", "I", "U", "E", "O", "Blink"]


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def get_audio_duration(wav_path: Path) -> float:
    """Get duration of a WAV file in seconds."""
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / rate


def text_to_phonemes(text: str) -> list[str]:
    """Simple vowel-based phoneme extraction."""
    text = text.lower()
    phonemes = []
    for char in text:
        if char in PHONEME_MAP:
            phonemes.append(PHONEME_MAP[char])
        elif char.isalpha():
            phonemes.append("Rest")
        elif char == " ":
            phonemes.append("Rest")
    # Collapse consecutive rests
    collapsed = []
    for p in phonemes:
        if collapsed and collapsed[-1] == "Rest" and p == "Rest":
            continue
        collapsed.append(p)
    return collapsed


def distribute_phonemes(phonemes: list[str], duration: float, fps: float = 24.0) -> list[dict]:
    """Distribute phonemes evenly across audio duration."""
    if not phonemes:
        return []
    total_frames = int(duration * fps)
    frame_per_phoneme = max(1, total_frames // max(1, len(phonemes)))
    result = []
    frame = 1
    for p in phonemes:
        result.append({"phoneme": p, "frame": frame, "duration": frame_per_phoneme})
        frame += frame_per_phoneme
    return result


def generate_kokoro_audio(text: str, output_path: Path, voice: str = "af_sarah", speed: float = 1.0) -> dict:
    """Generate audio using Kokoro TTS."""
    python = WORKSPACE_ROOT / "env" / "bin" / "python3"
    cmd = [
        str(python), str(KOKORO_SCRIPT),
        "speak", text, str(output_path),
        "--voice", voice,
        "--speed", str(speed),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return {"status": "error", "error": result.stderr}
    return {"status": "ok", "path": str(output_path)}


def generate_openvoice_audio(text: str, output_path: Path, character_name: str) -> dict:
    """Generate audio using OpenVoice character clone."""
    python = WORKSPACE_ROOT / "env" / "bin" / "python3"
    cmd = [
        str(python), str(OPENVoice_SCRIPT),
        "cast", character_name,
        "--text", text,
        "--output", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        return {"status": "error", "error": result.stderr}
    return {"status": "ok", "path": str(output_path)}


def find_character_voice(text: str, character_manifest: dict) -> tuple[str, str]:
    """Determine best voice engine for a line of dialogue."""
    characters = character_manifest.get("characters", {})
    for char_id, char_data in characters.items():
        display_name = char_data.get("display_name", char_id).lower()
        if display_name in text.lower() or char_id.lower() in text.lower():
            # Check if OpenVoice embedding exists
            registry_path = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "character_voices.json"
            if registry_path.exists():
                registry = _load_json(registry_path)
                if char_id in registry.get("characters", {}):
                    return "openvoice", char_id
            return "kokoro", char_data.get("kokoro_voice", "af_sarah")
    return "kokoro", "af_sarah"


class AutoDubbingPipeline:
    def __init__(self, project_slug: str, engine: str = "auto", voice: str = "af_sarah",
                 use_cache: bool = True):
        self.project_slug = project_slug
        self.engine = engine
        self.voice = voice
        # Skip re-synthesizing a shot whose (text, engine, voice) is unchanged.
        # Disable with use_cache=False or env DISABLE_RENDER_CACHE=1.
        self.cache = (RenderCache() if use_cache and RenderCache
                      and not os.environ.get("DISABLE_RENDER_CACHE") else None)
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_path = self.project_dir / "03-layout" / "layout.blend"
        self.shot_list = _load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.character_manifest = _load_json(self.project_dir / "01-scripts" / "character_manifest.json")
        self.audio_dir = self.project_dir / "06-audio" / "dialogue"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def dub(self, shot_id: str | None = None, all_shots: bool = False) -> dict:
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

            # Determine voice
            voice_engine, voice_id = find_character_voice(dialogue, self.character_manifest)
            if self.engine != "auto":
                voice_engine = self.engine

            # Generate audio
            wav_path = self.audio_dir / f"{sid}.wav"
            print(f"🎙️  {sid}: '{dialogue[:50]}...' → {voice_engine} ({voice_id})")

            def _synth(out: Path) -> dict:
                if voice_engine == "openvoice":
                    return generate_openvoice_audio(dialogue, out, voice_id)
                return generate_kokoro_audio(dialogue, out, self.voice)

            if self.cache is not None:
                held = {}
                cache_inputs = {"text": dialogue, "engine": voice_engine,
                                "voice_id": voice_id, "kokoro_voice": self.voice}
                cres = self.cache.materialize(
                    "dub", cache_inputs, wav_path,
                    lambda out: held.update(r=_synth(out)))
                if cres["hit"]:
                    print(f"   ⚡ cache hit — restored {sid}.wav (no TTS)")
                    gen_result = {"status": "ok", "path": str(wav_path), "cached": True}
                else:
                    gen_result = held.get("r", {"status": "error", "error": "producer did not run"})
            elif voice_engine == "openvoice":
                gen_result = generate_openvoice_audio(dialogue, wav_path, voice_id)
            else:
                gen_result = generate_kokoro_audio(dialogue, wav_path, self.voice)

            if gen_result["status"] != "ok":
                results.append({"shot_id": sid, "status": "error", "phase": "tts", "error": gen_result.get("error", "unknown")})
                continue

            # Get actual duration
            try:
                duration = get_audio_duration(wav_path)
            except Exception:
                duration = len(dialogue) * 0.07  # fallback estimate

            # Estimate phonemes
            phonemes = text_to_phonemes(dialogue)
            timed_phonemes = distribute_phonemes(phonemes, duration)

            results.append({
                "shot_id": sid,
                "status": "ok",
                "engine": voice_engine,
                "voice": voice_id,
                "audio_path": str(wav_path),
                "duration_sec": round(duration, 2),
                "phonemes": len(phonemes),
                "cached": gen_result.get("cached", False),
            })

        return {
            "status": "ok",
            "project": self.project_slug,
            "results": results,
            "audio_dir": str(self.audio_dir),
        }


def main():
    parser = argparse.ArgumentParser(description="Auto-Dubbing Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("dub", help="Generate dialogue audio")
    p.add_argument("project_slug")
    p.add_argument("--shot")
    p.add_argument("--all-shots", action="store_true")
    p.add_argument("--engine", choices=["auto", "kokoro", "openvoice"], default="auto")
    p.add_argument("--voice", default="af_sarah")
    args = parser.parse_args()

    pipeline = AutoDubbingPipeline(args.project_slug, engine=args.engine, voice=args.voice)
    result = pipeline.dub(shot_id=args.shot, all_shots=args.all_shots)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
