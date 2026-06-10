#!/usr/bin/env python3
"""
Creative tools (Phase 5).

  brand-check <co> <unit> <run>          # scripts vs the unit's brand profile (full, local)
  i18n        <co> <unit> <run> --langs es,zh   # scaffold a multi-language dub/subtitle plan
  ab          <co> <unit> <run> --titles 5       # title/thumbnail A/B variants + tracking
  trends      [--channel youtube]                # surface local trend signals (integration seam)

brand-check is fully local (rule-based). i18n/ab/trends are working scaffolds that
record plans + tracking manifests and leave clean seams for the heavy tooling
(XTTS dubbing, ComfyUI thumbnails) and external feeds (platform trend APIs).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
import studio_lib as S  # noqa: E402
import yaml


def run_dir(co, unit, run):
    return S.unit_folder(co, unit) / "production" / run


def unit_dir(co, unit):
    return S.unit_folder(co, unit)


DEFAULT_BRAND = {
    "voice": "clear, educational, concrete; no hype",
    "reading_level_max_grade": 11,
    "forbidden_terms": ["revolutionary", "game-changer", "synergy", "blockchain",
                        "guru", "hack", "10x", "world-class", "cutting-edge"],
    "required_disclosures": [],          # e.g. ["#ad"] for sponsored
    "banned_claims": ["guaranteed", "get rich", "overnight", "no risk"],
}


def brand_profile(co, unit) -> dict:
    p = unit_dir(co, unit) / "brand.yaml"
    if p.exists():
        return {**DEFAULT_BRAND, **(yaml.safe_load(p.read_text()) or {})}
    p.write_text(yaml.safe_dump(DEFAULT_BRAND, sort_keys=False))
    return DEFAULT_BRAND


def _grade_level(text: str) -> float:
    # Flesch-Kincaid grade (rough): 0.39(words/sent) + 11.8(syll/word) - 15.59
    sents = max(1, len(re.findall(r"[.!?]+", text)))
    words = re.findall(r"[A-Za-z]+", text)
    if not words:
        return 0.0
    syl = sum(max(1, len(re.findall(r"[aeiouy]+", w.lower()))) for w in words)
    return round(0.39 * len(words) / sents + 11.8 * syl / len(words) - 15.59, 1)


def brand_check(co, unit, run) -> int:
    rd = run_dir(co, unit, run)
    if not rd.exists():
        print(f"❌ run not found: {rd}"); return 1
    prof = brand_profile(co, unit)
    scripts = list((rd / "01-scripts").glob("*.md"))
    if not scripts:
        print(f"  (no scripts in {run}/01-scripts/)"); return 0
    issues = 0
    print(f"Brand check: {co}/{unit}/{run}  (profile: {unit_dir(co,unit).name}/brand.yaml)")
    for sc in scripts:
        text = sc.read_text(encoding="utf-8", errors="ignore")
        low = text.lower()
        found = [t for t in prof["forbidden_terms"] if re.search(rf"\b{re.escape(t)}\b", low)]
        claims = [t for t in prof["banned_claims"] if t in low]
        missing = [d for d in prof.get("required_disclosures", []) if d.lower() not in low]
        grade = _grade_level(text)
        over = grade > prof["reading_level_max_grade"]
        n = len(found) + len(claims) + len(missing) + (1 if over else 0)
        issues += n
        mark = "\033[32m✓\033[0m" if n == 0 else "\033[33m⚠\033[0m"
        print(f"  {mark} {sc.name}  (grade {grade}, max {prof['reading_level_max_grade']})")
        for t in found:
            print(f"      • forbidden term: '{t}'")
        for t in claims:
            print(f"      • banned claim: '{t}'")
        for d in missing:
            print(f"      • missing required disclosure: '{d}'")
        if over:
            print(f"      • reading level {grade} exceeds max {prof['reading_level_max_grade']}")
    print(f"\n  {issues} brand issue(s) across {len(scripts)} script(s). Voice target: {prof['voice']}")
    return 0


def i18n(co, unit, run, langs) -> int:
    rd = run_dir(co, unit, run)
    if not rd.exists():
        print(f"❌ run not found: {rd}"); return 1
    scripts = list((rd / "01-scripts").glob("*.md"))
    plan = {"run": run, "source_scripts": [s.name for s in scripts], "languages": {}}
    for lang in langs:
        (rd / "06-audio" / lang).mkdir(parents=True, exist_ok=True)
        (rd / "08-subtitles" / lang).mkdir(parents=True, exist_ok=True)
        plan["languages"][lang] = {
            "subtitles_dir": f"08-subtitles/{lang}/",
            "audio_dir": f"06-audio/{lang}/",
            "dub_engine": "XTTS v2 (via bridge /voiceover with company/unit/run routing)",
            "status": "scaffolded",
        }
    out = rd / ".pipeline" / "i18n_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2))
    print(f"✅ i18n scaffolded for {', '.join(langs)} — per-language audio/subtitle slots + plan")
    print(f"   {out.relative_to(ROOT)}")
    print("   Seam: dispatch each (script, lang) to XTTS dubbing + subtitle gen; outputs land in the slots above.")
    return 0


def _omlx_titles(topic, n, timeout=25):
    """Generate titles via the local MLX server, with a hard timeout + fallback."""
    import urllib.request
    body = {
        "model": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        "messages": [
            {"role": "system", "content": "You write clear, accurate educational video titles. No hype words."},
            {"role": "user", "content": f"Generate {n} concise, non-clickbait video titles for: {topic}. "
                                        f"One per line, no numbering."},
        ],
        "temperature": 0.4, "max_tokens": 200,
    }
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = json.loads(r.read().decode())["choices"][0]["message"]["content"]
        lines = [l.strip("-•0123456789. ").strip() for l in txt.splitlines() if l.strip()]
        return [l for l in lines if l][:n] or None
    except Exception:
        return None  # MLX slow/offline → deterministic fallback titles


def ab(co, unit, run, n_titles) -> int:
    rd = run_dir(co, unit, run)
    if not rd.exists():
        print(f"❌ run not found: {rd}"); return 1
    scripts = list((rd / "01-scripts").glob("*.md"))
    topic = run
    if scripts:
        m = re.search(r"^#\s+(.+)$", scripts[0].read_text(encoding="utf-8", errors="ignore"), re.M)
        topic = m.group(1) if m else run
    titles = _omlx_titles(topic, n_titles) or [f"{topic} — variant {i+1}" for i in range(n_titles)]
    variants = {
        "run": run, "topic": topic,
        "title_variants": [{"id": f"T{i+1}", "title": t, "impressions": 0, "ctr": None}
                           for i, t in enumerate(titles)],
        "thumbnail_variants": [{"id": f"TH{i+1}", "path": f"09-deliver/thumbnails/variant_{i+1}.png",
                                "impressions": 0, "ctr": None} for i in range(min(3, n_titles))],
        "note": "Log impressions/ctr after publishing to pick a winner.",
    }
    out = rd / ".pipeline" / "ab_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(variants, indent=2))
    (rd / "09-deliver" / "thumbnails").mkdir(parents=True, exist_ok=True)
    print(f"✅ A/B harness for '{topic}': {len(titles)} title + {len(variants['thumbnail_variants'])} thumbnail slots")
    for v in variants["title_variants"]:
        print(f"   {v['id']}: {v['title']}")
    print(f"   tracking → {out.relative_to(ROOT)}")
    print("   Seam: render thumbnail variants via ComfyUI into 09-deliver/thumbnails/; log CTR to pick a winner.")
    return 0


def trends(channel) -> int:
    feed = ROOT / "00_CORE" / "trends.yaml"
    if not feed.exists():
        feed.write_text(yaml.safe_dump({
            "_note": "Populate from platform trend APIs / the China-market skills, or by hand.",
            "youtube": ["(no signals yet)"],
            "tiktok": ["(no signals yet)"],
            "bilibili": ["(no signals yet)"],
        }, sort_keys=False))
    data = yaml.safe_load(feed.read_text()) or {}
    print(f"Trend signals (source: 00_CORE/trends.yaml — integration seam for live feeds)")
    for plat, items in data.items():
        if plat.startswith("_") or (channel and plat != channel):
            continue
        print(f"  {plat}:")
        for it in (items if isinstance(items, list) else [items]):
            print(f"    • {it}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="creative")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("brand-check", "i18n", "ab"):
        p = sub.add_parser(c); p.add_argument("company"); p.add_argument("unit"); p.add_argument("run")
        if c == "i18n":
            p.add_argument("--langs", default="es,zh")
        if c == "ab":
            p.add_argument("--titles", type=int, default=5)
    pt = sub.add_parser("trends"); pt.add_argument("--channel")
    a = ap.parse_args(argv)
    if a.cmd == "brand-check":
        return brand_check(a.company, a.unit, a.run)
    if a.cmd == "i18n":
        return i18n(a.company, a.unit, a.run, [l.strip() for l in a.langs.split(",") if l.strip()])
    if a.cmd == "ab":
        return ab(a.company, a.unit, a.run, a.titles)
    if a.cmd == "trends":
        return trends(a.channel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
