#!/usr/bin/env python3
"""Dubbing × render-cache integration — proves the cache actually skips re-synthesis.

Builds an AutoDubbingPipeline with its fields set directly (no 05_PROJECTS on disk),
stubs the Kokoro TTS with a call-counting fake, and runs dub() twice. The second
run must restore from cache without invoking TTS — the whole point of #9.

Run:  env/bin/python3 tests/dub_cache_test.py   (auto-run by `studio doctor`)
"""
import pathlib
import sys
import tempfile
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))

import auto_dubbing_pipeline as DUB  # noqa: E402
import render_cache as RC  # noqa: E402

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


def _make_pipeline(audio_dir, cache_root):
    """Construct without __init__ so we don't scaffold under 05_PROJECTS."""
    p = object.__new__(DUB.AutoDubbingPipeline)
    p.project_slug = "test-proj"
    p.engine = "kokoro"          # force kokoro path (avoids OpenVoice branch)
    p.voice = "af_sarah"
    p.character_manifest = {}
    p.audio_dir = audio_dir
    p.cache = RC.RenderCache(root=cache_root)
    p.shot_list = {"shots": [
        {"shot_id": "SC001_SH001", "dialogue": "Hello there, welcome to the lesson."},
        {"shot_id": "SC001_SH002", "dialogue": "Today we cover the normal distribution."},
    ]}
    return p


def t_second_run_hits_cache():
    with tempfile.TemporaryDirectory() as d:
        dp = pathlib.Path(d)
        calls = {"n": 0}

        def fake_kokoro(text, output_path, voice="af_sarah", speed=1.0):
            calls["n"] += 1
            pathlib.Path(output_path).write_bytes(b"FAKEWAV:" + text.encode())
            return {"status": "ok", "path": str(output_path)}

        DUB.generate_kokoro_audio = fake_kokoro  # monkeypatch

        p1 = _make_pipeline(dp / "audio", dp / "cache")
        r1 = p1.dub(all_shots=True)
        assert r1["status"] == "ok", r1
        assert calls["n"] == 2, f"first run should synth both shots (got {calls['n']})"
        assert all(not s["cached"] for s in r1["results"]), "first run should be all misses"

        # Fresh pipeline, fresh audio dir, SAME cache + same dialogue → both hit.
        p2 = _make_pipeline(dp / "audio2", dp / "cache")
        r2 = p2.dub(all_shots=True)
        assert calls["n"] == 2, f"second run must NOT call TTS again (got {calls['n']})"
        assert all(s["cached"] for s in r2["results"]), "second run should be all hits"
        # restored bytes match what the producer originally wrote
        restored = (dp / "audio2" / "SC001_SH001.wav").read_bytes()
        assert restored.startswith(b"FAKEWAV:Hello there"), restored[:20]
        return "2 synths on run 1, 0 on run 2 — cache restored both"


def t_changed_dialogue_resynths():
    with tempfile.TemporaryDirectory() as d:
        dp = pathlib.Path(d)
        calls = {"n": 0}

        def fake_kokoro(text, output_path, voice="af_sarah", speed=1.0):
            calls["n"] += 1
            pathlib.Path(output_path).write_bytes(b"WAV:" + text.encode())
            return {"status": "ok", "path": str(output_path)}

        DUB.generate_kokoro_audio = fake_kokoro

        p1 = _make_pipeline(dp / "a", dp / "cache")
        p1.dub(all_shots=True)               # 2 synths
        # edit one line of dialogue → that shot must re-synth, the other still hits
        p2 = _make_pipeline(dp / "b", dp / "cache")
        p2.shot_list["shots"][0]["dialogue"] = "Hello there, welcome to the EDITED lesson."
        r = p2.dub(all_shots=True)
        assert calls["n"] == 3, f"only the edited shot should re-synth (got {calls['n']})"
        cached_flags = {s["shot_id"]: s["cached"] for s in r["results"]}
        assert cached_flags["SC001_SH001"] is False, "edited shot must miss"
        assert cached_flags["SC001_SH002"] is True, "unchanged shot must hit"
        return "edit busts only the changed shot"


if __name__ == "__main__":
    print("Dubbing × render-cache integration")
    check("second run restores from cache (no re-synth)", t_second_run_hits_cache)
    check("edited dialogue re-synths only that shot", t_changed_dialogue_resynths)

    print()
    if hard_failures:
        print(f"\033[31mFAIL — {hard_failures} hard failure(s)\033[0m")
        sys.exit(1)
    print("\033[32mOK — 0 hard failure(s)\033[0m")
