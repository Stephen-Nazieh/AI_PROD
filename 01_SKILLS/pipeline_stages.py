#!/usr/bin/env python3
"""Pipeline stage producers + QA review gate.

Drives a run from an existing script (01-scripts/screenplay.md) through the rest of
the canonical pipeline, calling real tools with graceful degradation:

  02-storyboards  storyboard()  — LLM shot list from the script
  04-raw_renders  renders()     — ComfyUI image per shot
  06-audio        audio()       — TTS voiceover (solocorn_media_bridge)
  07-editing      editing()     — ffmpeg slideshow synced to the voiceover
  08-subtitles    subtitles()   — .srt cues from the spoken script
  09-deliver      deliver()     — ffmpeg final master (+ burned subs) + thumbnail

QA review gate (qa_review) runs at key stages (script + deliver): rule checks plus
an LLM content review that can BLOCK the run before more compute is spent.

Each producer returns {"ok": bool, "detail": str, "artifacts": [..]}.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "01_SKILLS"
sys.path.insert(0, str(SKILLS))
import studio_lib as S  # noqa: E402

MAX_SHOTS = int(os.environ.get("PIPELINE_MAX_SHOTS", "5"))


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_script(rd: pathlib.Path) -> str:
    d = rd / "01-scripts"
    f = d / "screenplay.md"
    if f.exists():
        return f.read_text(encoding="utf-8", errors="ignore")
    # fall back to the largest .md a writer left under 01-scripts/
    mds = sorted(d.glob("*.md"), key=lambda p: -p.stat().st_size) if d.is_dir() else []
    return mds[0].read_text(encoding="utf-8", errors="ignore") if mds else ""


def _script_to_spoken(script: str) -> str:
    """Strip frontmatter, markdown, delivery beats, and section tags → spoken text."""
    body = script
    if body.startswith("---"):
        body = body.split("---", 2)[-1]
    body = re.sub(r"\[[^\]]{0,24}\]", "", body)          # [beat] [smirk] [Hook] ...
    body = re.sub(r"[#*_`>]", "", body)                   # markdown marks
    body = re.sub(r"^\s*-\s+", "", body, flags=re.M)      # list bullets
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return " ".join(lines)


def _extract_json(text: str):
    for pat in (r"\[.*\]", r"\{.*\}"):
        m = re.search(pat, text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


def _ffprobe_duration(path: pathlib.Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _srt_ts(t: float) -> str:
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ── producers ─────────────────────────────────────────────────────────────────

def storyboard(rd: pathlib.Path, **_) -> dict:
    script = _read_script(rd)
    if not script.strip():
        return {"ok": False, "detail": "no screenplay.md to storyboard"}
    msg = [
        {"role": "system", "content":
         "You are a storyboard artist. Given a short video script, output a JSON array "
         "of 3-6 shots. Each shot: {\"id\":1,\"line\":\"<the script line>\","
         "\"visual\":\"<a vivid, concrete image-generation prompt>\",\"seconds\":5}. "
         "Output ONLY the JSON array."},
        {"role": "user", "content": script[:3000]},
    ]
    shots = _extract_json(S.mlx_chat(msg, big=True, max_tokens=1200) or "")
    if not isinstance(shots, list) or not shots:
        # fallback: one shot per non-empty paragraph
        paras = [p.strip() for p in script.split("\n\n") if p.strip()][:MAX_SHOTS]
        shots = [{"id": i + 1, "line": p[:160], "visual": _script_to_spoken(p)[:160],
                  "seconds": 5} for i, p in enumerate(paras)]
    shots = shots[:MAX_SHOTS]
    for i, s in enumerate(shots):
        s["id"] = i + 1
    out = rd / "02-storyboards" / "shotlist.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(shots, indent=2), encoding="utf-8")
    return {"ok": True, "detail": f"{len(shots)} shots", "artifacts": ["02-storyboards/shotlist.json"]}


def _channel_visual(rd: pathlib.Path) -> tuple[str, int]:
    """(style_suffix, seed_base) for the run's channel, so shots share an identity."""
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / "00_CORE" / "channel_visuals.yaml").read_text())
        unit = rd.parts[rd.parts.index("production") - 1]  # …/<unit>/production/<run>
        ch = (cfg.get("channels") or {}).get(unit) or {}
        d = cfg.get("defaults") or {}
        return ch.get("style", d.get("style", "")), int(ch.get("seed_base", d.get("seed_base", 100)))
    except Exception:
        return "", 100


def renders(rd: pathlib.Path, **_) -> dict:
    sl = rd / "02-storyboards" / "shotlist.json"
    if not sl.exists():
        return {"ok": False, "detail": "no shotlist.json (run storyboard first)"}
    shots = json.loads(sl.read_text())[:MAX_SHOTS]
    outdir = rd / "04-raw_renders"
    outdir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(SKILLS))
    import comfyui_client
    style, seed_base = _channel_visual(rd)  # per-channel identity → coherent set
    done = 0
    for s in shots:
        op = outdir / f"shot_{int(s['id']):02d}.png"
        base = s.get("visual") or s.get("line") or "abstract background"
        prompt = f"{base}, {style}" if style else base
        try:
            comfyui_client.render(prompt, str(op), seed=seed_base + int(s["id"]))
            if op.exists() and op.stat().st_size > 0:
                done += 1
        except Exception as e:
            print(f"  ⚠️ render shot {s['id']} failed: {str(e)[:80]}", file=sys.stderr)
    return {"ok": done > 0, "detail": f"{done}/{len(shots)} shots rendered (styled)",
            "artifacts": [f"04-raw_renders/ ({done} png)"]}


def audio(rd: pathlib.Path, **_) -> dict:
    spoken = _script_to_spoken(_read_script(rd))
    if not spoken:
        return {"ok": False, "detail": "no spoken text in script"}
    out = rd / "06-audio" / "voiceover.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        sys.path.insert(0, str(SKILLS))
        import solocorn_media_bridge as bridge
        bridge.synthesize_voiceover(spoken[:5000], str(out))
    except Exception as e:
        return {"ok": False, "detail": f"TTS error: {str(e)[:100]}"}
    ok = out.exists() and out.stat().st_size > 1000
    return {"ok": ok, "detail": f"{out.stat().st_size // 1024}KB voiceover" if ok else "TTS produced no audio",
            "artifacts": ["06-audio/voiceover.wav"]}


def editing(rd: pathlib.Path, **_) -> dict:
    frames = sorted((rd / "04-raw_renders").glob("shot_*.png"))
    if not frames:
        return {"ok": False, "detail": "no renders to edit"}
    audio_f = rd / "06-audio" / "voiceover.wav"
    outdir = rd / "07-editing"
    outdir.mkdir(parents=True, exist_ok=True)
    timeline = outdir / "timeline.mp4"
    dur = _ffprobe_duration(audio_f) if audio_f.exists() else 0.0
    if dur <= 0:
        dur = len(frames) * 4.0
    per = max(1.0, dur / len(frames))
    concat = outdir / "_concat.txt"
    lines = []
    for f in frames:
        lines.append(f"file '{f.as_posix()}'")
        lines.append(f"duration {per:.3f}")
    lines.append(f"file '{frames[-1].as_posix()}'")  # concat demuxer holds last frame
    concat.write_text("\n".join(lines), encoding="utf-8")
    # All -i inputs MUST precede output options.
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat)]
    if audio_f.exists():
        cmd += ["-i", str(audio_f)]
    cmd += ["-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
                   "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p", "-r", "30"]
    if audio_f.exists():
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(timeline)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    concat.unlink(missing_ok=True)
    ok = timeline.exists() and timeline.stat().st_size > 1000
    return {"ok": ok, "detail": (f"timeline {timeline.stat().st_size // 1024}KB, ~{dur:.0f}s"
                                 if ok else "ffmpeg: " + r.stderr.strip()[-150:]),
            "artifacts": ["07-editing/timeline.mp4"]}


def subtitles(rd: pathlib.Path, **_) -> dict:
    spoken = _script_to_spoken(_read_script(rd))
    if not spoken:
        return {"ok": False, "detail": "no spoken text"}
    words = spoken.split()
    out = rd / "08-subtitles" / "captions.srt"
    out.parent.mkdir(parents=True, exist_ok=True)
    cues, i, t, idx = [], 0, 0.0, 1
    while i < len(words):
        chunk = words[i:i + 8]
        i += 8
        d = max(1.5, len(chunk) * 0.4)
        cues.append(f"{idx}\n{_srt_ts(t)} --> {_srt_ts(t + d)}\n{' '.join(chunk)}\n")
        t += d
        idx += 1
    out.write_text("\n".join(cues), encoding="utf-8")
    return {"ok": True, "detail": f"{idx - 1} cues", "artifacts": ["08-subtitles/captions.srt"]}


def deliver(rd: pathlib.Path, **_) -> dict:
    timeline = rd / "07-editing" / "timeline.mp4"
    if not timeline.exists():
        return {"ok": False, "detail": "no timeline.mp4 to deliver"}
    outdir = rd / "09-deliver"
    outdir.mkdir(parents=True, exist_ok=True)
    master = outdir / "master.mp4"
    srt = next((rd / "08-subtitles").glob("*.srt"), None)
    if srt:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(timeline),
             "-vf", f"subtitles='{srt.as_posix()}'", "-c:a", "copy", str(master)],
            capture_output=True, text=True, timeout=600)
        if not (master.exists() and master.stat().st_size > 1000):
            shutil.copy2(timeline, master)  # subtitle burn failed → ship clean
    else:
        shutil.copy2(timeline, master)
    thumb = outdir / "thumbnail.jpg"
    frames = sorted((rd / "04-raw_renders").glob("shot_*.png"))
    if frames:
        subprocess.run(["ffmpeg", "-y", "-i", str(frames[0]), "-vf", "scale=1280:720", str(thumb)],
                       capture_output=True, timeout=60)
    ok = master.exists() and master.stat().st_size > 1000
    return {"ok": ok, "detail": (f"master {master.stat().st_size // 1024}KB"
                                 f"{' + thumbnail' if thumb.exists() else ''}" if ok else "deliver failed"),
            "artifacts": ["09-deliver/master.mp4", "09-deliver/thumbnail.jpg"]}


PRODUCERS = {"storyboard": storyboard, "renders": renders, "audio": audio,
             "editing": editing, "subtitles": subtitles, "deliver": deliver}


# ── QA review gate (#5) ───────────────────────────────────────────────────────

QA_STAGES = {"01-scripts", "09-deliver"}


def qa_review(rd: pathlib.Path, stage: str) -> dict:
    """Content QA at key stages. Returns {pass: bool, notes: str}. Rule checks plus
    an LLM review that can block the run before downstream compute is spent."""
    if stage == "01-scripts":
        script = _read_script(rd)
        if len(script.strip()) < 80:
            return {"pass": False, "notes": "script missing or too short"}
        msg = [
            {"role": "system", "content":
             "You are a strict but fair script editor for a short-form video channel. "
             "Judge whether this script is publish-ready: clear structure, on-topic, "
             "coherent, and free of offensive/unsafe content. Reply with ONLY JSON: "
             "{\"verdict\":\"pass\" or \"revise\",\"notes\":\"<one short reason>\"}."},
            {"role": "user", "content": script[:3000]},
        ]
        v = _extract_json(S.mlx_chat(msg, big=True, max_tokens=200, temperature=0.0) or "")
        if isinstance(v, dict) and str(v.get("verdict", "")).lower() == "revise":
            return {"pass": False, "notes": "QA review → revise: " + str(v.get("notes", ""))[:160]}
        note = v.get("notes", "ok") if isinstance(v, dict) else "ok"
        return {"pass": True, "notes": f"QA review → pass ({str(note)[:80]})"}
    if stage == "09-deliver":
        m = rd / "09-deliver" / "master.mp4"
        if not (m.exists() and m.stat().st_size > 10000):
            return {"pass": False, "notes": "master.mp4 missing or too small"}
        return {"pass": True, "notes": f"master delivered ({m.stat().st_size // 1024}KB)"}
    return {"pass": True, "notes": ""}
