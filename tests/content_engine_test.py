#!/usr/bin/env python3
"""Content-engine smoke tests — fast offline invariants + regression guards for the bugs that
actually bit us at batch scale (SAR concat, ffmpeg stdin, non-VRoid bone crash, markdown captions,
abstract-subject B-roll). Network/service checks are warn-only.

Run:  env/bin/python3 tests/content_engine_test.py   (picked up by `make test`)
Exit non-zero on any hard failure.
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "content_engine"))
sys.path.insert(0, str(ROOT / "content_engine" / "agents"))
sys.path.insert(0, str(ROOT / "content_engine" / "memory"))
sys.path.insert(0, str(ROOT / "02-pipeline"))

PASS, FAIL, WARN = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[33m!\033[0m"
hard = 0

def check(name, fn, warn_only=False):
    global hard
    try:
        d = fn() or ""
        print(f"  {PASS} {name}{(' — ' + d) if d else ''}")
    except Exception as e:
        print(f"  {(WARN if warn_only else FAIL)} {name} — {e}")
        if not warn_only: hard += 1

def src(rel):
    return (ROOT / rel).read_text()

# ── imports (catch syntax/import breaks) ────────────────────────────────────
def t_imports():
    import llm, qa, finish, publish, analytics, scheduler, anchor_broll, paperclip_sync  # noqa
    import director, scriptwriter  # noqa
    import broll_images  # noqa
    return "core modules import"

# ── regression guards: the exact fixes for bugs we hit ──────────────────────
def t_setsar():
    assert "setsar=1" in src("02-pipeline/produce.py"), "produce.py clip missing setsar=1 (SAR concat bug)"
    assert "setsar=1" in src("02-pipeline/broll_images.py"), "broll image_clip missing setsar=1"
    return "setsar=1 present (concat SAR fix)"

def t_nostdin():
    assert '"-nostdin"' in src("02-pipeline/produce.py"), "produce ff() missing -nostdin (loop-stdin bug)"
    assert '"-nostdin"' in src("content_engine/finish.py"), "finish ff() missing -nostdin"
    return "ffmpeg -nostdin present"

def t_bone_lookup():
    s = src("01-scripts/bl_scene_engine.py")
    assert "bone_world" in s and "J_Bip_C_Head" in s, "tolerant bone_world() lookup missing"
    return "tolerant bone lookup present"

def t_stale_guard():
    assert "_fresh" in src("content_engine/engine.py"), "engine missing stale-episode mtime guard"
    return "stale-episode guard present"

# ── pure-function behavior ──────────────────────────────────────────────────
def t_clean_hook():
    import director
    assert director.clean_hook("Sharks outlived dinosaurs — insane!") == "Sharks outlived dinosaurs"
    assert director.clean_hook("Bananas are radioactive — really?") == "Bananas are radioactive"
    return "filler suffixes stripped"

def t_casting_spread():
    import director
    seen = {director.pick_presenter(f"daily-curiosities-{i:02d}-x")[0] for i in range(1, 11)}
    assert len(seen) >= 9, f"only {len(seen)}/10 distinct presenters"
    return f"{len(seen)}/10 distinct"

def t_karaoke():
    import finish
    out = finish.chunk_captions([(0.0, 8.0, "this is a fairly long caption that should be chunked into pieces")])
    assert len(out) >= 3 and all(len(c[2].split()) <= 4 for c in out), "captions not chunked to <=4 words"
    return f"{len(out)} chunks"

def t_caption_markdown():
    import finish, os, tempfile
    srt = tempfile.NamedTemporaryFile("w", suffix=".srt", delete=False)
    srt.write("1\n00:00:01,000 --> 00:00:03,000\nHOST: the **Eiffel Tower** grows\n"); srt.close()
    caps = finish.parse_srt(srt.name); os.unlink(srt.name)
    assert caps and "*" not in caps[0][2], "markdown not stripped from captions"
    return "markdown stripped"

def t_broll_science():
    import broll_images as B
    g = B._comfy_graph("bacteria", 1)
    neg = g["7"]["inputs"]["text"]; pos = g["6"]["inputs"]["text"]
    assert "person" in neg and "face" in neg, "anti-human negative missing"
    assert "microscope" in pos or "scientific" in pos, "science framing missing for abstract subject"
    return "science framing + anti-human negative"

def t_seed_banks():
    import os
    d = ROOT / "content_engine" / "channels"
    facts = {}
    for ch in ("daily-curiosities", "weird-history"):
        p = d / ch / "idea_seeds.txt"
        n = len([l for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")])
        facts[ch] = n
        assert n >= 10, f"{ch} seed bank too small ({n})"
    return ", ".join(f"{k}={v}" for k, v in facts.items())

# ── real-artifact QA (validates the gate + a finished short, if one exists) ──
def t_qa_real_short():
    import glob, qa
    shorts = glob.glob(str(ROOT / "content_engine" / "runs" / "*" / "out" / "*_social.mp4"))
    if not shorts:
        raise RuntimeError("no finished short to QA (run a batch first)")
    rep = qa.verify_social(sorted(shorts)[-1])
    assert rep["ok"], f"QA failed on real short: {rep['issues']}"
    return f"QA pass on {pathlib.Path(shorts[-1]).name[:30]} {rep['stats'].get('dims')}"

# ── services (warn-only) ────────────────────────────────────────────────────
def t_services():
    import urllib.request
    down = []
    for name, url in (("mlx-smart", "http://127.0.0.1:8000/v1/models"),
                      ("comfyui", "http://127.0.0.1:8188/system_stats"),
                      ("paperclip", "http://127.0.0.1:3100/api/companies")):
        try: urllib.request.urlopen(url, timeout=3).read()
        except Exception: down.append(name)
    assert not down, f"down: {down}"
    return "mlx + comfyui + paperclip up"

print("Content-engine smoke tests")
check("modules import", t_imports)
check("setsar=1 concat fix", t_setsar)
check("ffmpeg -nostdin", t_nostdin)
check("tolerant bone lookup", t_bone_lookup)
check("stale-episode guard", t_stale_guard)
check("clean_hook strips filler", t_clean_hook)
check("even casting spread", t_casting_spread)
check("karaoke caption chunking", t_karaoke)
check("captions strip markdown", t_caption_markdown)
check("B-roll science framing", t_broll_science)
check("seed banks stocked", t_seed_banks)
check("QA passes on a real short", t_qa_real_short, warn_only=True)
check("local services reachable", t_services, warn_only=True)

print(f"\n{'FAILED' if hard else 'OK'} — {hard} hard failure(s)")
sys.exit(1 if hard else 0)
