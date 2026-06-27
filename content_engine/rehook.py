#!/usr/bin/env python3
"""Regenerate title + hook from each run's ACTUAL script lines and re-burn the social
finish — no re-render. Fixes shorts whose director hook was hallucinated/empty/copied.

  env/bin/python3 content_engine/rehook.py content_engine/runs/daily-curiosities-*
"""
import glob, json, os, re, sys
ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE); sys.path.insert(0, os.path.join(ENGINE, "agents"))
import llm
from director import spoken_lines, clean_hook

SYS = ("You are a viral short-form editor. Given the actual spoken lines of a 30s vertical short, "
       "return STRICT JSON {\"title\":\"<punchy 2-4 word curiosity title>\",\"hook\":\"<one "
       "scroll-stopping line drawn from the SINGLE most surprising fact in THESE lines>\"}. "
       "The hook must restate the script's own shocking fact in <=7 words (e.g. lines about honey "
       "never spoiling -> \"Honey never spoils\"). State the fact CLEANLY — NO tacked-on filler "
       "like '— wow!', '— really?', '— insane!', 'mind blown'. Never use the location/setting. "
       "Never copy this example. JSON only.")

def regen(run_dir):
    script = os.path.join(run_dir, "script.md"); bp = os.path.join(run_dir, "show_bible.json")
    if not (os.path.exists(script) and os.path.exists(bp)):
        return None
    lines = spoken_lines(open(script).read())
    raw = llm.chat(SYS, "LINES:\n" + "\n".join(f"- {l}" for l in lines), tier="fast",
                   temperature=0.5, max_tokens=120)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    b = json.load(open(bp)); b["show"] = d.get("title", b["show"]); b["hook"] = clean_hook(d.get("hook", ""))
    json.dump(b, open(bp, "w"), indent=2)
    return b

def refinish(run_dir):
    import finish
    run = os.path.basename(run_dir.rstrip("/")); out = os.path.join(run_dir, "out")
    ep = os.path.join(out, run + ".mp4"); srt = os.path.join(out, run + ".srt")
    b = json.load(open(os.path.join(run_dir, "show_bible.json")))
    if not os.path.exists(ep):
        return None
    finish.finish_social(ep, srt if os.path.exists(srt) else None,
                         os.path.join(out, run + "_social.mp4"),
                         thumb=os.path.join(out, run + "_thumb.jpg"),
                         title=b.get("show", ""), hook=b.get("hook", ""))
    return b.get("hook", "")

if __name__ == "__main__":
    dirs = sorted(d for p in sys.argv[1:] for d in glob.glob(p) if os.path.isdir(d))
    for d in dirs:
        b = regen(d)
        if not b:
            print(f"  SKIP {os.path.basename(d)}"); continue
        hook = refinish(d)
        print(f"  ✓ {os.path.basename(d)[:42]:42s} title={b['show']!r}  hook={hook!r}")
    print(f"done — {len(dirs)} runs re-hooked + re-finished")
