#!/usr/bin/env python3
"""CONTENT ENGINE — idea → content, with a human vet gate. The one command surface.

  # 1. idea → script (then YOU review/edit content_engine/runs/<run>/script.md)
  engine.py write   --run <name> --idea "…" --format movie|talking_head|social|explainer [--channel X]
  # 2. approved script → cast (director) → produce video → distribute
  engine.py produce --run <name> [--channel X] [--no-distribute]
  # one-shot (skips the vet gate — use when you trust it)
  engine.py make    --run <name> --idea "…" --format movie [--channel X]
  # status of the brain + tools (transparency)
  engine.py health
"""
import argparse, json, os, subprocess, sys
ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
PY = os.path.join(ROOT, "env/bin/python3")
sys.path.insert(0, ENGINE); sys.path.insert(0, os.path.join(ENGINE, "memory"))
import llm
import memory

def run_dir(run):
    d = os.path.join(ENGINE, "runs", run); os.makedirs(d, exist_ok=True); return d

def sh(cmd, **kw):
    print("   $", " ".join(os.path.basename(c) if c.startswith("/") else c for c in cmd[:3]), "…")
    return subprocess.run(cmd, cwd=ROOT, **kw)

def step_write(run, idea, fmt, platform, channel, length, notes):
    d = run_dir(run); script = os.path.join(d, "script.md")
    json.dump({"format": fmt, "channel": channel, "platform": platform, "idea": idea},
              open(os.path.join(d, "meta.json"), "w"), indent=2)
    sh([PY, "content_engine/agents/scriptwriter.py", "--idea", idea, "--format", fmt,
        "--platform", platform, "--length", length, "--notes", notes, "--out", script]
       + (["--channel", channel] if channel else []))
    return script

def step_produce(run, channel, distribute=True):
    d = run_dir(run); script = os.path.join(d, "script.md")
    if not os.path.exists(script):
        sys.exit(f"no script at {script} — run `engine.py write --run {run} …` first")
    bible = os.path.join(d, "show_bible.json"); out = os.path.join(d, "out")
    print("\n▶ DIRECTOR — casting + staging")
    sh([PY, "content_engine/agents/director.py", "--script", script, "--out", bible])
    print("\n▶ PRODUCE — render + assemble")
    import time; t0 = time.time()
    pr = sh([PY, "02-pipeline/produce.py", "--script", script, "--bible", bible, "--out", out, "--episode", run])
    if pr.returncode != 0:
        print(f"   ⚠ produce.py exited {pr.returncode}")
    # only accept a FRESH episode (mtime >= produce start) — never fall back to a stale render
    def _fresh(p): return os.path.exists(p) and os.path.getmtime(p) >= t0 - 2
    ep = next((p for p in [os.path.join(out, "masters", run + ".mp4"),
                           os.path.join(out, run + ".mp4")] if _fresh(p)), None)
    if not ep and os.path.isdir(out):
        cand = sorted((f for f in os.listdir(out) if f.endswith(".mp4") and not f.startswith("scene_")),
                      key=lambda f: os.path.getmtime(os.path.join(out, f)), reverse=True)
        ep = next((os.path.join(out, f) for f in cand if _fresh(os.path.join(out, f))), None)
    if not ep:
        print("   ✗ no fresh episode produced — aborting finish (not using stale output)")
        memory.record_run(run, "", "", channel, "no-output", "")
        return None
    # SOCIAL FINISH: burn captions + hook + thumbnail (sound-off ready) for social runs
    is_social = False; qa_failed = None
    if ep and os.path.exists(ep):
        try:
            bj = json.load(open(bible)) if os.path.exists(bible) else {}
            if bj.get("format") == "social":
                is_social = True
                import finish
                srt = os.path.join(out, run + ".srt")
                fin = os.path.join(out, run + "_social.mp4")
                print("\n▶ SOCIAL FINISH — burned captions + hook + thumbnail")
                finish.finish_social(ep, srt if os.path.exists(srt) else None, fin,
                                     thumb=os.path.join(out, run + "_thumb.jpg"),
                                     title=bj.get("show", ""), hook=bj.get("hook", ""))
                print(f"   → {fin}")
                ep = fin
                try:                                 # QUALITY GATE — verify the deliverable
                    import qa
                    caps = len(open(srt).read().strip().split("\n\n")) if os.path.exists(srt) else None
                    rep = qa.verify_social(fin, captions=caps)
                    if rep["ok"]:
                        print(f"   ✓ QA pass {rep['stats']}")
                    else:
                        print(f"   ✗ QA FAIL — {rep['issues']}  {rep['stats']}")
                        qa_failed = rep["issues"]
                except Exception as e:
                    print(f"   (QA skipped: {str(e)[:80]})")
        except Exception as e:
            print(f"   (social finish skipped: {str(e)[:80]})")
    if distribute and not is_social and ep and os.path.exists(ep):
        print("\n▶ DISTRIBUTE — vertical + thumbnail + captions")
        srt = os.path.join(out, "masters", run + ".srt")
        cmd = [PY, "02-pipeline/distribute.py", ep, "--title", run]
        if os.path.exists(srt): cmd += ["--srt", srt]
        sh(cmd)
    memory.record_run(run, "", "", channel, "produced" if ep else "no-output", ep or "")
    if is_social and ep and not qa_failed:       # posting-ready manifest only if QA passed
        try:
            import publish
            man = publish.make_manifest(d, channel or "", "tiktok")
            if man: print(f"   publish manifest → {os.path.join(out, 'publish.json')}  ({len(man['hashtags'])} tags)")
        except Exception as e:
            print(f"   (publish prep skipped: {str(e)[:80]})")
    elif is_social and qa_failed:
        print(f"   ⚠ held from publish queue (QA failed: {qa_failed})")
    if channel:                                  # surface the run to Paperclip oversight
        status = ("qa-failed" if (is_social and qa_failed) else
                  "ready-to-publish" if (is_social and ep) else
                  "produced" if ep else "no-output")
        try:
            import paperclip_sync
            paperclip_sync.report_run(channel, run, status, ep or "")
        except Exception:
            pass
    print(f"\n✅ run '{run}' done → {ep or out}")
    return ep

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write"); w.add_argument("--run", required=True); w.add_argument("--idea", required=True)
    w.add_argument("--format", default="movie"); w.add_argument("--platform", default="youtube")
    w.add_argument("--channel", default=None); w.add_argument("--length", default="2-3 min")
    w.add_argument("--notes", default="")
    p = sub.add_parser("produce"); p.add_argument("--run", required=True); p.add_argument("--channel", default=None)
    p.add_argument("--no-distribute", action="store_true")
    m = sub.add_parser("make"); m.add_argument("--run", required=True); m.add_argument("--idea", required=True)
    m.add_argument("--format", default="movie"); m.add_argument("--platform", default="youtube")
    m.add_argument("--channel", default=None); m.add_argument("--length", default="2-3 min")
    m.add_argument("--notes", default=""); m.add_argument("--no-distribute", action="store_true")
    c = sub.add_parser("chat", help="natural-language → action (local intent router)")
    c.add_argument("request", nargs="+")
    b = sub.add_parser("batch", help="produce many pieces for a channel (one idea per line in --file)")
    b.add_argument("--channel", required=True); b.add_argument("--file", required=True)
    b.add_argument("--format", default="movie"); b.add_argument("--length", default="1 min")
    sub.add_parser("health")
    a = ap.parse_args()

    if a.cmd == "batch":
        ideas = [l.strip() for l in open(a.file) if l.strip() and not l.startswith("#")]
        print(f"[batch] {len(ideas)} pieces for '{a.channel}' (sequential — renders are GPU-bound)")
        for i, idea in enumerate(ideas, 1):
            import re as _re
            run = f"{a.channel}-{i:02d}-" + _re.sub(r"\W+", "-", idea[:24]).strip("-").lower()
            print(f"\n=== [{i}/{len(ideas)}] {run} ===")
            step_write(run, idea, a.format, "youtube", a.channel, a.length, "")
            step_produce(run, a.channel, distribute=True)
        print(f"\n[batch] done — {len(ideas)} pieces in content_engine/runs/")
        return

    if a.cmd == "chat":
        import router
        print(router.chat(" ".join(a.request)))
        return

    if a.cmd == "health":
        print("BRAIN:", json.dumps(llm.health(), indent=2))
        for t in ("ffmpeg", "node"):
            print(f"TOOL {t}:", subprocess.run(["which", t], capture_output=True, text=True).stdout.strip() or "—")
        print("TOOL blender:", "/Applications/Blender.app (use .app path)")
        return
    if a.cmd == "write":
        s = step_write(a.run, a.idea, a.format, a.platform, a.channel, a.length, a.notes)
        print(f"\n★ VET GATE — review/edit:  {s}\n   then:  engine.py produce --run {a.run}")
    elif a.cmd == "produce":
        step_produce(a.run, a.channel, distribute=not a.no_distribute)
    elif a.cmd == "make":
        step_write(a.run, a.idea, a.format, a.platform, a.channel, a.length, a.notes)
        print("\n(make: skipping the vet gate)\n")
        step_produce(a.run, a.channel, distribute=not a.no_distribute)

if __name__ == "__main__":
    main()
