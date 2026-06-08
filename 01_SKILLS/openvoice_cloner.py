#!/usr/bin/env python3
"""
openvoice_cloner.py — Per-Character Voice Cloning for DeParadigm Media

Clones character voices using OpenVoice V2. Each character gets a unique,
consistent voice based on a short reference audio sample (~5-30 seconds).

Usage:
    # Clone a voice and speak a line
    python openvoice_cloner.py speak "Hello world" --reference /path/to/ref.wav --output output.wav

    # Register a character voice
    python openvoice_cloner.py register "Professor Ava" --reference /path/to/ava_ref.wav

    # Speak as a registered character
    python openvoice_cloner.py cast "Professor Ava" --text "Welcome to statistics class"

    # Batch generate all dialogue for a character
    python openvoice_cloner.py batch-cast "Professor Ava" --lines-file lines.txt --output-dir ./ava_dialogue/

Env:
    OPENVOICE_CHECKPOINT_DIR — default: /Users/nazeera/Documents/AI_PRODUCER/OpenVoice/checkpoints
    OPENVOICE_DEVICE — default: auto (mps > cpu)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import soundfile as sf
import torch

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
OPENVOICE_ROOT = WORKSPACE_ROOT / "OpenVoice"
CHECKPOINT_DIR = Path(os.environ.get("OPENVOICE_CHECKPOINT_DIR", OPENVOICE_ROOT / "checkpoints"))
DEVICE = os.environ.get("OPENVOICE_DEVICE", "mps" if torch.backends.mps.is_available() else "cpu")

# Add OpenVoice to path
sys.path.insert(0, str(OPENVOICE_ROOT))

# Lazy imports to avoid slow startup
_openvoice_loaded = False
_en_base_speaker_tts = None
_tone_color_converter = None
_en_source_default_se = None


def _load_models():
    """Lazy-load OpenVoice models (cached)."""
    global _openvoice_loaded, _en_base_speaker_tts, _tone_color_converter, _en_source_default_se
    if _openvoice_loaded:
        return

    from openvoice.api import BaseSpeakerTTS, ToneColorConverter

    en_ckpt_base = CHECKPOINT_DIR / "base_speakers" / "EN"
    ckpt_converter = CHECKPOINT_DIR / "converter"

    _en_base_speaker_tts = BaseSpeakerTTS(
        str(en_ckpt_base / "config.json"), device=DEVICE
    )
    _en_base_speaker_tts.load_ckpt(str(en_ckpt_base / "checkpoint.pth"))

    _tone_color_converter = ToneColorConverter(
        str(ckpt_converter / "config.json"), device=DEVICE, enable_watermark=False
    )
    _tone_color_converter.load_ckpt(str(ckpt_converter / "checkpoint.pth"))

    _en_source_default_se = torch.load(
        str(en_ckpt_base / "en_default_se.pth"), map_location=DEVICE
    )

    _openvoice_loaded = True


def _get_character_registry(project_slug: str | None = None) -> Path:
    """Get path to character voice registry."""
    if project_slug:
        return WORKSPACE_ROOT / "05_PROJECTS" / project_slug / "01-scripts" / "character_voices.json"
    return WORKSPACE_ROOT / "06_SHARED_ASSETS" / "character_voices.json"


def _load_registry(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_registry(path: Path, registry: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def extract_speaker_embedding(reference_path: str) -> torch.Tensor:
    """Extract speaker embedding from a reference audio file."""
    _load_models()
    return _tone_color_converter.extract_se(reference_path)


def speak(
    text: str,
    output_path: str,
    reference_path: str | None = None,
    speaker_embedding: torch.Tensor | None = None,
    speaker: str = "default",
    language: str = "English",
    speed: float = 1.0,
) -> dict:
    """
    Generate speech with a cloned voice.

    Args:
        text: Text to speak.
        output_path: Output WAV file path.
        reference_path: Path to reference audio for voice cloning.
        speaker_embedding: Pre-computed speaker embedding (alternative to reference_path).
        speaker: Base speaker preset (default, friendly, etc.).
        language: Language code.
        speed: Speech speed multiplier.

    Returns:
        Structured result dict.
    """
    _load_models()

    out = Path(output_path)
    if not out.is_absolute():
        out = WORKSPACE_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    # Generate base TTS
    tmp_path = str(out.with_suffix(".tmp.wav"))
    _en_base_speaker_tts.tts(text, tmp_path, speaker=speaker, language=language, speed=speed)

    # Apply voice cloning if reference provided
    if reference_path or speaker_embedding is not None:
        if speaker_embedding is None:
            speaker_embedding = extract_speaker_embedding(reference_path)
        _tone_color_converter.convert(
            audio_src_path=tmp_path,
            src_se=_en_source_default_se,
            tgt_se=speaker_embedding,
            output_path=str(out),
        )
        Path(tmp_path).unlink(missing_ok=True)
    else:
        Path(tmp_path).rename(out)

    return {
        "status": "ok",
        "output_path": str(out),
        "text": text,
        "duration_sec": round(sf.info(str(out)).duration, 2),
        "message": f"Generated speech → {out.name}",
    }


def register_character(
    character_name: str,
    reference_path: str,
    project_slug: str | None = None,
    description: str = "",
) -> dict:
    """
    Register a character voice from reference audio.

    Args:
        character_name: Character name (e.g., "Professor Ava").
        reference_path: Path to reference audio file.
        project_slug: Optional project to scope the voice to.
        description: Optional voice description.

    Returns:
        Structured result with saved embedding path.
    """
    _load_models()

    ref = Path(reference_path)
    if not ref.exists():
        return {"status": "error", "message": f"Reference audio not found: {ref}"}

    # Extract and save embedding
    se = extract_speaker_embedding(str(ref))
    se_dir = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "voice-embeddings"
    se_dir.mkdir(parents=True, exist_ok=True)
    safe_name = character_name.replace(" ", "_").lower()
    se_path = se_dir / f"{safe_name}_se.pth"
    torch.save(se.cpu(), str(se_path))

    # Update registry
    registry = _load_registry(_get_character_registry(project_slug))
    registry[character_name] = {
        "embedding_path": str(se_path),
        "reference_path": str(ref.resolve()),
        "description": description,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _save_registry(_get_character_registry(project_slug), registry)

    return {
        "status": "ok",
        "character": character_name,
        "embedding_path": str(se_path),
        "registry": str(_get_character_registry(project_slug)),
        "message": f"Registered '{character_name}' voice cloning profile",
    }


def cast_character(
    character_name: str,
    text: str,
    output_path: str,
    project_slug: str | None = None,
    speed: float = 1.0,
) -> dict:
    """Generate speech as a registered character."""
    registry = _load_registry(_get_character_registry(project_slug))
    if character_name not in registry:
        # Try global registry fallback
        registry = _load_registry(_get_character_registry(None))
        if character_name not in registry:
            return {
                "status": "error",
                "message": f"Character '{character_name}' not registered. Run: register <name> --reference <path>",
            }

    char_info = registry[character_name]
    se = torch.load(char_info["embedding_path"], map_location=DEVICE)
    return speak(text, output_path, speaker_embedding=se, speed=speed)


def batch_cast(
    character_name: str,
    lines: list[str],
    output_dir: str,
    project_slug: str | None = None,
    speed: float = 1.0,
    naming: str = "{char}_{i:04d}.wav",
) -> dict:
    """Batch generate dialogue lines for a character."""
    out_dir = Path(output_dir)
    if not out_dir.is_absolute():
        out_dir = WORKSPACE_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    errors = []
    for i, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        fname = naming.format(char=character_name.replace(" ", "_").lower(), i=i)
        fpath = out_dir / fname
        res = cast_character(character_name, line.strip(), str(fpath), project_slug, speed)
        if res["status"] == "ok":
            results.append(res)
        else:
            errors.append({"line": i, "text": line, "error": res["message"]})

    return {
        "status": "ok" if not errors else "partial",
        "character": character_name,
        "generated": len(results),
        "errors": len(errors),
        "outputs": results,
        "error_details": errors,
        "message": f"Batch: {len(results)} OK, {len(errors)} failed",
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OpenVoice Character Voice Cloner")
    sub = parser.add_subparsers(dest="command", required=True)

    # speak
    p_speak = sub.add_parser("speak", help="Speak with a cloned voice")
    p_speak.add_argument("text", help="Text to speak")
    p_speak.add_argument("--reference", required=True, help="Reference audio file")
    p_speak.add_argument("--output", required=True, help="Output WAV path")
    p_speak.add_argument("--speed", type=float, default=1.0)

    # register
    p_reg = sub.add_parser("register", help="Register a character voice")
    p_reg.add_argument("character", help="Character name")
    p_reg.add_argument("--reference", required=True, help="Reference audio file")
    p_reg.add_argument("--project", help="Project slug (optional)")
    p_reg.add_argument("--description", default="", help="Voice description")

    # cast
    p_cast = sub.add_parser("cast", help="Speak as a registered character")
    p_cast.add_argument("character", help="Character name")
    p_cast.add_argument("--text", required=True, help="Text to speak")
    p_cast.add_argument("--output", required=True, help="Output WAV path")
    p_cast.add_argument("--project", help="Project slug")
    p_cast.add_argument("--speed", type=float, default=1.0)

    # batch-cast
    p_batch = sub.add_parser("batch-cast", help="Batch generate lines for a character")
    p_batch.add_argument("character", help="Character name")
    p_batch.add_argument("--lines-file", required=True, help="File with one line per utterance")
    p_batch.add_argument("--output-dir", required=True, help="Output directory")
    p_batch.add_argument("--project", help="Project slug")
    p_batch.add_argument("--speed", type=float, default=1.0)

    # list
    p_list = sub.add_parser("list", help="List registered characters")
    p_list.add_argument("--project", help="Project slug")

    args = parser.parse_args()

    if args.command == "speak":
        result = speak(args.text, args.output, reference_path=args.reference, speed=args.speed)
        print(json.dumps(result, indent=2))

    elif args.command == "register":
        result = register_character(args.character, args.reference, args.project, args.description)
        print(json.dumps(result, indent=2))

    elif args.command == "cast":
        result = cast_character(args.character, args.text, args.output, args.project, args.speed)
        print(json.dumps(result, indent=2))

    elif args.command == "batch-cast":
        lines = Path(args.lines_file).read_text(encoding="utf-8").splitlines()
        result = batch_cast(args.character, lines, args.output_dir, args.project, args.speed)
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        registry = _load_registry(_get_character_registry(args.project))
        print("Registered characters:")
        for name, info in registry.items():
            desc = info.get("description", "")
            print(f"  {name}: {desc or 'No description'}")
            print(f"    Reference: {info.get('reference_path', 'N/A')}")
            print(f"    Embedding: {info.get('embedding_path', 'N/A')}")


if __name__ == "__main__":
    main()
