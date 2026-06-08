#!/usr/bin/env python3
"""
kokoro_tts.py — Local Text-to-Speech Engine for Solocorn Studios

Replaces cloud-based TTS (ElevenLabs) with fully local inference.
Uses Kokoro-ONNX (~82MB model) for fast, high-quality voice synthesis.
Optional F5-TTS (~3GB) available for premium natural-sounding output.

No API keys. No network latency. No subscription.

Usage:
    python kokoro_tts.py speak "Hello world" output.wav --voice af_sarah
    python kokoro_tts.py list-voices
    python kokoro_tts.py batch lines.txt out_dir/ --voice am_michael

Env:
    KOKORO_VOICE      — default voice (default: af_sarah)
    KOKORO_SPEED      — speech speed factor (default: 1.0)
    KOKORO_LANG       — language code: "a"=American, "b"=British, "j"=Japanese,
                        "z"=Mandarin, "e"=Spanish, "f"=French, "h"=Hindi,
                        "i"=Italian, "p"=Brazilian Portuguese (default: a)
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import List

import numpy as np
import soundfile as sf

# Silence espeak phonemizer warnings on first import
warnings.filterwarnings("ignore", category=UserWarning)

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VOICE = os.environ.get("KOKORO_VOICE", "af_sarah")
DEFAULT_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))
DEFAULT_LANG = os.environ.get("KOKORO_LANG", "a")

# Model paths (downloaded from GitHub releases)
KOKORO_MODEL_PATH = (
    WORKSPACE_ROOT / "06_SHARED_ASSETS" / "ai-models" / "kokoro" / "kokoro-v1.0.onnx"
)
KOKORO_VOICES_PATH = (
    WORKSPACE_ROOT / "06_SHARED_ASSETS" / "ai-models" / "kokoro" / "voices-v1.0.bin"
)

# Cache the pipeline globally to avoid re-loading the model
_KOKORO_PIPELINE = None


def _get_pipeline():
    """Lazy-load the Kokoro pipeline (cached)."""
    global _KOKORO_PIPELINE
    if _KOKORO_PIPELINE is not None:
        return _KOKORO_PIPELINE

    try:
        from kokoro_onnx import Kokoro
    except ImportError as e:
        raise RuntimeError(
            "kokoro-onnx not installed. Run: pip install kokoro-onnx soundfile"
        ) from e

    if not KOKORO_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Kokoro model not found at {KOKORO_MODEL_PATH}.\n"
            "Download from: https://github.com/thewh1teagle/kokoro-onnx/releases"
        )
    if not KOKORO_VOICES_PATH.exists():
        raise FileNotFoundError(
            f"Kokoro voices not found at {KOKORO_VOICES_PATH}.\n"
            "Download from: https://github.com/thewh1teagle/kokoro-onnx/releases"
        )

    _KOKORO_PIPELINE = Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))
    return _KOKORO_PIPELINE


# ── Voice catalogue (built-in) ──────────────────────────────────────────────

VOICE_CATALOGUE = {
    # American English (f)
    "af_sarah":   {"lang": "en-us", "gender": "F", "desc": "American female — Sarah"},
    "af_nicole":  {"lang": "en-us", "gender": "F", "desc": "American female — Nicole"},
    "af_heart":   {"lang": "en-us", "gender": "F", "desc": "American female — Heart"},
    "af_bella":   {"lang": "en-us", "gender": "F", "desc": "American female — Bella"},
    "am_michael": {"lang": "en-us", "gender": "M", "desc": "American male — Michael"},
    "am_adam":    {"lang": "en-us", "gender": "M", "desc": "American male — Adam"},
    # British English (b)
    "bf_emma":    {"lang": "en-gb", "gender": "F", "desc": "British female — Emma"},
    "bf_isabella":{"lang": "en-gb", "gender": "F", "desc": "British female — Isabella"},
    "bm_george":  {"lang": "en-gb", "gender": "M", "desc": "British male — George"},
    "bm_lewis":   {"lang": "en-gb", "gender": "M", "desc": "British male — Lewis"},
    # Japanese (j)
    "jf_alpha":   {"lang": "ja",    "gender": "F", "desc": "Japanese female — Alpha"},
    "jm_kumo":    {"lang": "ja",    "gender": "M", "desc": "Japanese male — Kumo"},
    # Mandarin (z)
    "zf_xiaobei": {"lang": "zh",    "gender": "F", "desc": "Mandarin female — Xiaobei"},
    "zm_yunjian": {"lang": "zh",    "gender": "M", "desc": "Mandarin male — Yunjian"},
    # Spanish (e)
    "ef_dora":    {"lang": "es",    "gender": "F", "desc": "Spanish female — Dora"},
    "em_alex":    {"lang": "es",    "gender": "M", "desc": "Spanish male — Alex"},
    # French (f)
    "ff_siwis":   {"lang": "fr",    "gender": "F", "desc": "French female — Siwis"},
    # Hindi (h)
    "hf_alpha":   {"lang": "hi",    "gender": "F", "desc": "Hindi female — Alpha"},
    "hm_omega":   {"lang": "hi",    "gender": "M", "desc": "Hindi male — Omega"},
    # Italian (i)
    "if_sara":    {"lang": "it",    "gender": "F", "desc": "Italian female — Sara"},
    "im_nicola":  {"lang": "it",    "gender": "M", "desc": "Italian male — Nicola"},
    # Brazilian Portuguese (p)
    "pf_dora":    {"lang": "pt-br", "gender": "F", "desc": "Brazilian Portuguese female — Dora"},
    "pm_alex":    {"lang": "pt-br", "gender": "M", "desc": "Brazilian Portuguese male — Alex"},
}


def list_voices(gender: str | None = None, lang: str | None = None) -> dict:
    """Return matching voices as a structured dict."""
    matches = {}
    for vid, info in VOICE_CATALOGUE.items():
        if gender and info["gender"].lower() != gender.lower():
            continue
        if lang and not info["lang"].startswith(lang):
            continue
        matches[vid] = info
    return {
        "status": "ok",
        "voices": matches,
        "count": len(matches),
        "message": f"Found {len(matches)} voice(s)",
    }


def speak(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    sample_rate: int = 24000,
) -> dict:
    """
    Synthesize speech from text and write to a WAV file.

    Args:
        text: The text to speak.
        output_path: Destination .wav file path.
        voice: Voice ID from VOICE_CATALOGUE.
        speed: Speech speed multiplier (0.5 = half, 2.0 = double).
        sample_rate: Output sample rate (Kokoro default is 24000).

    Returns:
        Structured result dict.
    """
    if voice not in VOICE_CATALOGUE:
        return {
            "status": "error",
            "message": f"Unknown voice '{voice}'. Run list_voices() for options.",
        }

    out = Path(output_path)
    if not out.is_absolute():
        out = WORKSPACE_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        pipeline = _get_pipeline()
        samples, sr = pipeline.create(text, voice, speed=speed)
        # Ensure numpy array
        if not isinstance(samples, np.ndarray):
            samples = np.array(samples)
        sf.write(str(out), samples, sr)
        duration = len(samples) / sr
        return {
            "status": "ok",
            "output_path": str(out),
            "voice": voice,
            "duration_sec": round(duration, 2),
            "sample_rate": sr,
            "message": f"Synthesized {duration:.1f}s of audio → {out.name}",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"TTS synthesis failed: {e}",
            "stderr": str(e),
        }


def speak_ssml(
    ssml: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
) -> dict:
    """
    Synthesize speech from SSML markup.
    Kokoro supports basic <break> and <emphasis> tags.
    """
    # Strip SSML wrapper tags for Kokoro (it handles plain text + basic tags)
    clean = ssml.replace("<speak>", "").replace("</speak>", "")
    return speak(clean, output_path, voice=voice, speed=speed)


def batch_synthesize(
    lines: List[str],
    output_dir: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    naming: str = "line_{i:04d}.wav",
) -> dict:
    """
    Synthesize multiple lines into separate files.

    Args:
        lines: List of text strings.
        output_dir: Directory for output WAV files.
        voice: Voice ID.
        speed: Speed multiplier.
        naming: Filename template with {i} index placeholder.

    Returns:
        Structured result with list of outputs.
    """
    out_dir = Path(output_dir)
    if not out_dir.is_absolute():
        out_dir = WORKSPACE_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    errors = []
    for i, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        fname = naming.format(i=i)
        fpath = out_dir / fname
        res = speak(line.strip(), str(fpath), voice=voice, speed=speed)
        if res["status"] == "ok":
            results.append(res)
        else:
            errors.append({"line": i, "text": line, "error": res["message"]})

    return {
        "status": "ok" if not errors else "partial",
        "synthesized": len(results),
        "errors": len(errors),
        "outputs": results,
        "error_details": errors,
        "message": f"Batch: {len(results)} OK, {len(errors)} failed",
    }


def cast_character(
    character_name: str,
    lines: List[str],
    output_dir: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
) -> dict:
    """
    Cast a character voice and synthesize all their dialogue lines.
    Useful for the voice-cast-director agent.
    """
    char_dir = Path(output_dir) / character_name.replace(" ", "_").lower()
    return batch_synthesize(
        lines=lines,
        output_dir=str(char_dir),
        voice=voice,
        speed=speed,
        naming=f"{character_name.replace(' ', '_').lower()}_{{i:04d}}.wav",
    )


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Kokoro Local TTS Engine")
    sub = parser.add_subparsers(dest="command", required=True)

    # list-voices
    sub.add_parser("list-voices", help="List available voices")

    # speak
    p_speak = sub.add_parser("speak", help="Synthesize a single utterance")
    p_speak.add_argument("text", help="Text to speak")
    p_speak.add_argument("output", help="Output WAV file path")
    p_speak.add_argument("--voice", default=DEFAULT_VOICE, help="Voice ID")
    p_speak.add_argument("--speed", type=float, default=DEFAULT_SPEED, help="Speed factor")

    # batch
    p_batch = sub.add_parser("batch", help="Synthesize lines from a text file")
    p_batch.add_argument("input_file", help="Text file with one line per utterance")
    p_batch.add_argument("output_dir", help="Output directory")
    p_batch.add_argument("--voice", default=DEFAULT_VOICE, help="Voice ID")
    p_batch.add_argument("--speed", type=float, default=DEFAULT_SPEED, help="Speed factor")

    # cast
    p_cast = sub.add_parser("cast", help="Cast a character voice")
    p_cast.add_argument("character", help="Character name")
    p_cast.add_argument("input_file", help="Text file with dialogue lines")
    p_cast.add_argument("output_dir", help="Output directory")
    p_cast.add_argument("--voice", default=DEFAULT_VOICE, help="Voice ID")
    p_cast.add_argument("--speed", type=float, default=DEFAULT_SPEED, help="Speed factor")

    args = parser.parse_args()

    if args.command == "list-voices":
        result = list_voices()
        for vid, info in result["voices"].items():
            print(f"  {vid:20}  {info['desc']}  ({info['lang']})")
        print(f"\nTotal: {result['count']} voices")

    elif args.command == "speak":
        result = speak(args.text, args.output, voice=args.voice, speed=args.speed)
        print(json.dumps(result, indent=2))

    elif args.command == "batch":
        lines = Path(args.input_file).read_text(encoding="utf-8").splitlines()
        result = batch_synthesize(lines, args.output_dir, voice=args.voice, speed=args.speed)
        print(json.dumps(result, indent=2))

    elif args.command == "cast":
        lines = Path(args.input_file).read_text(encoding="utf-8").splitlines()
        result = cast_character(args.character, lines, args.output_dir, voice=args.voice, speed=args.speed)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
