#!/usr/bin/env python3
"""
generate_channel_script.py — auto-generate an on-brand short-video script for a
business unit (channel) and write it into a 05_PROJECTS run as shot-list.json +
screenplay.md, ready for the 2D pipeline.

The local LLM (MLX :8000) only returns a compact {title, mood, shots:[{action,
dialogue}]} payload; this module expands it into the full shot-list schema
(stable shot ids, per-line durations, a single `protagonist` narrator matching the
sprite the pipeline's `characters` stage generates). Falls back to a deterministic
on-brand script if the model output can't be parsed — so a run is never empty.

    python generate_channel_script.py <company> <unit> <run_slug> [--topic "..."]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "01_SKILLS"))
import studio_lib as S  # noqa: E402

MLX_URL = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "mlx-community/Qwen2.5-32B-Instruct-4bit"
WPM = 150.0  # speaking rate for duration estimates


def _unit_context(company: str, unit: str) -> str:
    """Pull BRIEF/STYLE for voice + domain grounding (best-effort)."""
    folder = S.unit_folder(company, unit)
    bits = []
    for name in ("BRIEF.md", "STYLE.md"):
        p = folder / name
        if p.exists():
            bits.append(f"=== {name} ===\n{p.read_text(encoding='utf-8')[:1500]}")
    return "\n\n".join(bits) or f"Channel: {unit}"


def _llm(prompt: str, system: str, max_tokens: int = 1200) -> str:
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "temperature": 0.7, "max_tokens": max_tokens,
    }
    req = urllib.request.Request(MLX_URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _parse_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    # Grab the outermost {...} if the model added prose around it.
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _fallback(unit: str) -> dict:
    return {
        "title": f"{unit.replace('-', ' ').title()} — Pilot Short",
        "mood": "academic",
        "shots": [
            {"action": "Host greets the viewer", "dialogue":
             "Welcome back. Today we're keeping it short and useful."},
            {"action": "Host introduces the idea", "dialogue":
             "Here's one concept that changes how you see the rest."},
            {"action": "Host explains with an example", "dialogue":
             "Picture a simple example, and the pattern jumps right out at you."},
            {"action": "Host wraps up", "dialogue":
             "That's the core of it. Like and subscribe for the next one."},
        ],
    }


def generate(company: str, unit: str, topic: str | None) -> dict:
    ctx = _unit_context(company, unit)
    system = (
        "You are a YouTube scriptwriter. Write a TIGHT ~60-second single-narrator "
        "short. Output ONLY JSON, no prose, in this exact shape:\n"
        '{"title": str, "mood": one of '
        '["academic","calm","tense","dramatic","upbeat","energetic","dark","warm","neutral"], '
        '"shots": [{"action": str, "dialogue": str}]}\n'
        "4-6 shots. dialogue = one or two spoken sentences (no stage directions). "
        "Match the channel's voice from the brief below."
    )
    ask = f"Channel context:\n{ctx}\n\n"
    ask += (f"Write the short about: {topic}" if topic else
            "Pick one strong on-brand topic for this channel and write the short.")
    for attempt in range(2):
        try:
            data = _parse_json(_llm(ask, system))
        except Exception:
            data = None
        if data and isinstance(data.get("shots"), list) and data["shots"]:
            data.setdefault("title", f"{unit} short")
            data.setdefault("mood", "neutral")
            return data
        ask += "\n\nReturn ONLY valid JSON matching the schema. No commentary."
    return _fallback(unit)


def to_shot_list(data: dict, run_slug: str) -> dict:
    mood = data.get("mood", "neutral")
    heading = f"INT. STUDIO - DAY"
    shots = []
    for i, s in enumerate(data["shots"], start=1):
        dialogue = (s.get("dialogue") or "").strip()
        words = max(1, len(dialogue.split()))
        dur = round(max(2.5, words / WPM * 60.0 + 0.8), 1)  # speak time + beat
        shots.append({
            "shot_id": f"SC001_SH{i:03d}",
            "scene_id": "SC001",
            "shot_type": "medium" if i % 2 else "close_up",
            "camera_movement": "static",
            "duration_seconds": dur,
            "action": (s.get("action") or "Host speaks to camera").strip(),
            "dialogue": dialogue,
            "characters": ["protagonist"],
        })
    return {
        "project": run_slug,
        "title": data.get("title", run_slug),
        "scenes": [{"scene_id": "SC001", "heading": heading,
                    "description": data.get("title", ""), "mood": mood,
                    "time_of_day": "day", "shot_count": len(shots)}],
        "shots": shots,
    }


def _screenplay(data: dict) -> str:
    lines = [f"# {data.get('title','Short')}", "", "## FADE IN:", "",
             "### SCENE 1: INT. STUDIO - DAY", ""]
    for s in data["shots"]:
        if s.get("action"):
            lines.append(s["action"])
        lines += ["", "HOST", s.get("dialogue", ""), ""]
    lines.append("## FADE OUT.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(prog="generate_channel_script")
    ap.add_argument("company"); ap.add_argument("unit"); ap.add_argument("run_slug")
    ap.add_argument("--topic", default=None)
    a = ap.parse_args()

    run_dir = WORKSPACE_ROOT / "05_PROJECTS" / a.run_slug
    scripts = run_dir / "01-scripts"
    if not scripts.exists():
        print(json.dumps({"status": "error",
                          "message": f"run not scaffolded: {run_dir} (run init_project first)"}))
        return 1

    data = generate(a.company, a.unit, a.topic)
    shot_list = to_shot_list(data, a.run_slug)
    (scripts / "shot-list.json").write_text(json.dumps(shot_list, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
    (scripts / "screenplay.md").write_text(_screenplay(data), encoding="utf-8")

    # single-narrator manifest matching the `protagonist` sprite + chosen voice
    voice = "af_sarah"
    (run_dir / "05-assets" / "character_manifest.json").write_text(
        json.dumps({"characters": [{"name": "protagonist", "type": "main",
                                     "voice": voice, "format": "2d"}]}, indent=2),
        encoding="utf-8")

    print(json.dumps({"status": "ok", "title": shot_list["title"],
                      "shots": len(shot_list["shots"]), "mood": shot_list["scenes"][0]["mood"],
                      "run_dir": str(run_dir)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
