#!/usr/bin/env python3
"""Back-apply subject-anchored B-roll to already-rendered runs WITHOUT re-rendering avatars.

Sets bible['subject'] (derived from the run slug) so the producer prepends it to weak B-roll
queries, then re-runs produce.py (avatars are cached → no Blender, just re-fetches images +
reassembles), re-finishes, QA-gates, and refreshes the publish manifest.

  env/bin/python3 content_engine/anchor_broll.py 'content_engine/runs/daily-curiosities-*'
"""
import glob, json, os, subprocess, sys
ENGINE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(ENGINE)
PY = os.path.join(ROOT, "env/bin/python3")
sys.path.insert(0, ENGINE)
import finish, qa, publish, llm

SUBJ_SYS = ("Return ONLY the single core photographable subject noun of this short — 1-2 words, "
            "lowercase, no punctuation. Examples: 'honey', 'venus', 'octopus', 'banana', 'eiffel "
            "tower', 'water'. Just the noun, nothing else.")

def subject_for(script_text, run):
    try:
        raw = llm.chat(SUBJ_SYS, script_text[:1200], tier="fast", temperature=0.0, max_tokens=12)
        s = raw.strip().strip('".\n').lower()
        s = " ".join(s.split()[:2])
        if 2 <= len(s) <= 24:
            return s
    except Exception:
        pass
    return run.split("-")[2] if len(run.split("-")) > 2 else ""   # crude slug fallback

def fix(run_dir):
    run = os.path.basename(run_dir.rstrip("/")); out = os.path.join(run_dir, "out")
    bp = os.path.join(run_dir, "show_bible.json"); script = os.path.join(run_dir, "script.md")
    if not (os.path.exists(bp) and os.path.exists(script)): return None
    b = json.load(open(bp))
    if b.get("format") != "social": return None
    subj = subject_for(open(script).read(), run)
    b["subject"] = subj; json.dump(b, open(bp, "w"), indent=2)
    # re-run produce (cached avatars → no Blender) then finish + QA + manifest
    r = subprocess.run([PY, "02-pipeline/produce.py", "--script", script, "--bible", bp,
                        "--out", out, "--episode", run], cwd=ROOT, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    ep = os.path.join(out, run + ".mp4"); srt = os.path.join(out, run + ".srt")
    if not os.path.exists(ep):
        print(f"  ✗ {run[:34]:34s} produce failed: {r.stderr[-120:]}"); return None
    fin = os.path.join(out, run + "_social.mp4")
    finish.finish_social(ep, srt if os.path.exists(srt) else None, fin,
                         thumb=os.path.join(out, run + "_thumb.jpg"), title=b.get("show", ""), hook=b.get("hook", ""))
    rep = qa.verify_social(fin)
    publish.make_manifest(run_dir, b.get("channel", "daily-curiosities"), "tiktok")
    flag = "✓" if rep["ok"] else "✗ QA:" + str(rep["issues"])
    print(f"  {flag} {run[:34]:34s} subject='{subj}'  {rep['stats'].get('duration')}s")
    return rep["ok"]

if __name__ == "__main__":
    dirs = sorted(d for p in sys.argv[1:] for d in glob.glob(p) if os.path.isdir(d))
    ok = sum(1 for d in dirs if fix(d))
    print(f"done — {ok}/{len(dirs)} re-anchored")
