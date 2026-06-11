#!/usr/bin/env python3
"""
Media-bridge functional tests — fast, fully-offline checks for the deterministic
core of the render/assembly path that previously had only import coverage:

  • snap_seconds_to_frames  — frame quantization + FCP time-string contract
  • generate_fcpxml_timeline — produces well-formed, parseable FCPXML
  • sanitize_generated_code  — the Manim code sanitizer (AGENTS.md requires it be
                               validated against ≥3 generated scene classes)

No Paperclip / Postgres / MLX / ffmpeg needed. WAV durations fall back to a fixed
default when a path isn't a real WAV, so plain temp files are enough.

Run:  env/bin/python3 tests/media_test.py   (auto-run by `studio doctor`)
Exit non-zero if any hard check fails.
"""
import pathlib
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))

import solocorn_media_bridge as M  # noqa: E402
from understand_anything.claude_interface import sanitize_generated_code  # noqa: E402

PASS, FAIL = "\033[32m✓\033[0m", "\033[31m✗\033[0m"
hard_failures = 0


def check(name, fn):
    global hard_failures
    try:
        detail = fn() or ""
        print(f"  {PASS} {name}{(' — ' + detail) if detail else ''}")
    except Exception as e:
        print(f"  {FAIL} {name} — {e}")
        hard_failures += 1
        if "-v" in sys.argv:
            traceback.print_exc()


def _eq(got, want, label=""):
    assert got == want, f"{label}expected {want!r}, got {got!r}"


# ── snap_seconds_to_frames ────────────────────────────────────────────────────

def t_snap_ceils_to_whole_frames():
    # 1.0s @ 24fps = exactly 24 frames → "2400/2400s" (24 * 100 / 2400 = 1.0s)
    frames, s = M.snap_seconds_to_frames(1.0, fps=24)
    _eq(frames, 24, "frames: "); _eq(s, "2400/2400s", "string: ")
    # ceil guarantees we never clip mid-frame: 0.01s rounds UP to 1 frame
    frames, s = M.snap_seconds_to_frames(0.01, fps=24)
    _eq(frames, 1, "ceil up: "); _eq(s, "100/2400s")
    # 14.17s → ceil(340.08) = 341 frames (docstring's "340" is an off-by-one typo)
    frames, _ = M.snap_seconds_to_frames(14.17, fps=24)
    _eq(frames, 341, "14.17s frames: ")
    return "24fps quantization + ceil contract holds"


def t_snap_fps_timebase_is_24_only():
    """Characterization: the FCP string hard-codes the /2400s (24fps) timebase, so
    fps != 24 yields a string that does NOT represent the input seconds. Pin this
    known limitation so a future fix is a deliberate, test-visible change."""
    frames, s = M.snap_seconds_to_frames(1.0, fps=30)
    _eq(frames, 30, "30fps frame count: ")  # frame COUNT honors fps...
    # ...but the string uses the 24fps timebase: 30*100/2400 = 1.25s, not 1.0s.
    _eq(s, "3000/2400s", "30fps string (buggy timebase): ")
    seconds_implied = (30 * 100) / 2400
    assert abs(seconds_implied - 1.25) < 1e-9, "timebase math drifted"
    return "fps≠24 timebase mismatch documented (1.0s→1.25s @30fps)"


# ── generate_fcpxml_timeline ──────────────────────────────────────────────────

def t_fcpxml_is_wellformed_and_structured():
    with tempfile.TemporaryDirectory() as d:
        dp = pathlib.Path(d)
        # scene 1: video + audio; scene 2: video only. Scene index = stem.split('_')[1].
        video1 = dp / "scene_1_render.png"; video1.write_bytes(b"\x89PNG fake")
        audio1 = dp / "scene_1_voice.wav"; audio1.write_bytes(b"not-a-real-wav")
        video2 = dp / "scene_2_render.png"; video2.write_bytes(b"\x89PNG fake")
        out = dp / "timeline.fcpxml"

        ret = M.generate_fcpxml_timeline([str(video1), str(audio1), str(video2)], str(out))
        assert pathlib.Path(ret).exists(), "no file returned/written"

        content = out.read_text(encoding="utf-8")
        assert content.startswith('<?xml'), "missing XML declaration"
        # Parse it — proves well-formedness (the real regression risk for FCPXML).
        root = ET.fromstring(content)
        _eq(root.tag, "fcpxml", "root tag: ")
        assert root.get("version"), "fcpxml missing version attr"

        # One <asset> per input path; two video scenes → two <asset-clip> on the spine.
        assets = root.findall(".//asset")
        _eq(len(assets), 3, "asset count: ")
        clips = root.findall(".//spine/asset-clip")
        _eq(len(clips), 2, "spine clip count: ")
        # scene 1's audio is nested as a lane=-1 sub-clip under its video clip.
        nested = root.findall(".//spine/asset-clip/asset-clip[@lane='-1']")
        _eq(len(nested), 1, "nested audio lane count: ")
        return f"valid FCPXML v{root.get('version')}, 3 assets / 2 clips / 1 nested audio"


# ── sanitize_generated_code (Manim sanitizer — ≥3 cases per AGENTS.md) ─────────

def t_sanitizer_strips_code_fences():
    raw = "```python\nself.play(Create(axes))\n```"
    out = sanitize_generated_code(raw)
    assert "```" not in out, "code fence leaked through"
    assert "self.play(Create(axes))" in out
    return "fences removed"


def t_sanitizer_drops_loose_single_words():
    # A stray single-word line (not a call, not self.) is dropped...
    raw = "Here\nself.wait(2)\naxes.plot()"
    out = sanitize_generated_code(raw)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert "Here" not in lines, "loose word survived"
    # ...but legitimate single-token call/`self.` lines are kept.
    assert "self.wait(2)" in out and "axes.plot()" in out
    return "stray token dropped, calls kept"


def t_sanitizer_reindents_and_seals_parens():
    # nested kwarg re-indented to 12 spaces
    out = sanitize_generated_code("x_range=[-3, 3, 1]")
    _eq(out, " " * 12 + "x_range=[-3, 3, 1]\n", "reindent: ")
    # dangling '(' gets one closing ')' appended
    out = sanitize_generated_code("axes = Axes(")
    assert out.strip() == "axes = Axes()", f"paren not sealed: {out!r}"
    return "12-space reindent + dangling-paren seal"


def t_sanitizer_output_is_valid_python():
    """The whole point of the sanitizer: a messy class compiles after cleaning."""
    raw = (
        "```python\n"
        "class DemoScene(Scene):\n"
        "    def construct(self):\n"
        "        axes = Axes(\n"
        "        self.play(Create(axes))\n"
        "```"
    )
    out = sanitize_generated_code(raw)
    compile(out, "<sanitized>", "exec")  # raises SyntaxError if the sanitizer failed
    return "sanitized scene compiles"


# ── run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Media-bridge functional tests")
    check("snap_seconds_to_frames — 24fps quantization", t_snap_ceils_to_whole_frames)
    check("snap_seconds_to_frames — 24fps timebase limitation", t_snap_fps_timebase_is_24_only)
    check("generate_fcpxml_timeline — well-formed + structured", t_fcpxml_is_wellformed_and_structured)
    check("sanitizer — strips code fences", t_sanitizer_strips_code_fences)
    check("sanitizer — drops loose single words", t_sanitizer_drops_loose_single_words)
    check("sanitizer — reindents kwargs + seals parens", t_sanitizer_reindents_and_seals_parens)
    check("sanitizer — output compiles as Python", t_sanitizer_output_is_valid_python)

    print()
    if hard_failures:
        print(f"\033[31mFAIL — {hard_failures} hard failure(s)\033[0m")
        sys.exit(1)
    print("\033[32mOK — 0 hard failure(s)\033[0m")
