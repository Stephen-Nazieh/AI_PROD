#!/usr/bin/env python3
"""Render-cache tests — content-addressing + hit/miss restore, fully offline.

Uses a temp cache root and a fake producer that counts how often it runs, so we
can prove: identical inputs hit (producer NOT re-run), changed params miss, and a
changed input FILE's content busts the key (the whole point of content-addressing).

Run:  env/bin/python3 tests/cache_test.py   (auto-run by `studio doctor`)
"""
import pathlib
import sys
import tempfile
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))

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


class Counter:
    """A fake renderer: writes deterministic bytes, counts invocations."""
    def __init__(self, payload=b"RENDERED"):
        self.calls = 0
        self.payload = payload

    def __call__(self, out: pathlib.Path):
        self.calls += 1
        out.write_bytes(self.payload)


def t_miss_then_hit():
    with tempfile.TemporaryDirectory() as d:
        cache = RC.RenderCache(root=pathlib.Path(d) / "cache")
        prod = Counter()
        inputs = {"text": "hello world", "voice": "af_sarah", "speed": 1.0}
        dest1 = pathlib.Path(d) / "run1" / "shot.wav"
        dest2 = pathlib.Path(d) / "run2" / "shot.wav"

        r1 = cache.materialize("dub", inputs, dest1, prod)
        assert r1["hit"] is False, "first call should miss"
        assert prod.calls == 1
        # Second run, identical inputs, different dest dir → restore from cache.
        r2 = cache.materialize("dub", inputs, dest2, prod)
        assert r2["hit"] is True, "identical inputs should hit"
        assert prod.calls == 1, "producer must not run on a hit"
        assert dest2.read_bytes() == b"RENDERED", "restored bytes wrong"
        assert r1["key"] == r2["key"], "same inputs → same key"
        return "miss→store→hit, producer ran once"


def t_changed_param_misses():
    with tempfile.TemporaryDirectory() as d:
        cache = RC.RenderCache(root=pathlib.Path(d) / "cache")
        prod = Counter()
        base = {"text": "hi", "voice": "af_sarah", "speed": 1.0}
        cache.materialize("dub", base, pathlib.Path(d) / "a.wav", prod)
        # change one param → different key → producer must run again
        cache.materialize("dub", {**base, "speed": 1.2}, pathlib.Path(d) / "b.wav", prod)
        assert prod.calls == 2, f"changed param should miss (calls={prod.calls})"
        return "distinct params → distinct keys"


def t_input_file_content_busts_key():
    with tempfile.TemporaryDirectory() as d:
        dp = pathlib.Path(d)
        cache = RC.RenderCache(root=dp / "cache")
        ref = dp / "ref.png"
        ref.write_bytes(b"image-v1")
        prod = Counter()
        inputs = {"prompt": "a cat", "ref_image": str(ref)}

        cache.materialize("storyboard", inputs, dp / "out1.png", prod)
        # same path, same inputs dict, but the FILE content changed → must miss
        ref.write_bytes(b"image-v2-different")
        cache.materialize("storyboard", inputs, dp / "out2.png", prod)
        assert prod.calls == 2, f"changed input file should bust key (calls={prod.calls})"

        # ...and reverting the file content restores the original key → hit
        ref.write_bytes(b"image-v1")
        r = cache.materialize("storyboard", inputs, dp / "out3.png", prod)
        assert r["hit"] is True and prod.calls == 2, "revert should re-hit"
        return "input files hashed by content, not path"


def t_stats_and_disk_tracking():
    with tempfile.TemporaryDirectory() as d:
        cache = RC.RenderCache(root=pathlib.Path(d) / "cache")
        prod = Counter(payload=b"x" * 100)
        inputs = {"text": "a"}
        cache.materialize("dub", inputs, pathlib.Path(d) / "1.wav", prod)  # miss
        cache.materialize("dub", inputs, pathlib.Path(d) / "2.wav", prod)  # hit
        s = cache.stats()
        assert s.get("hit") == 1 and s.get("miss") == 1, s
        n, b = cache.disk()
        assert n == 1 and b == 100, f"disk tracking off: {n} blobs / {b} bytes"
        assert cache.clear() == 1, "clear should report 1 blob removed"
        assert cache.disk() == (0, 0), "store not empty after clear"
        return "hit/miss + disk size + clear correct"


if __name__ == "__main__":
    print("Render-cache tests")
    check("miss then hit (producer runs once)", t_miss_then_hit)
    check("changed param misses", t_changed_param_misses)
    check("input file content busts key", t_input_file_content_busts_key)
    check("stats + disk tracking + clear", t_stats_and_disk_tracking)

    print()
    if hard_failures:
        print(f"\033[31mFAIL — {hard_failures} hard failure(s)\033[0m")
        sys.exit(1)
    print("\033[32mOK — 0 hard failure(s)\033[0m")
