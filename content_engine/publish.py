#!/usr/bin/env python3
"""CONTENT ENGINE — PUBLISH PREP.

Turns a finished run into a posting-ready package: a per-run `publish.json`
(title, hook, caption, hashtags, video + thumbnail paths, platform, duration) and a
human-readable `PUBLISH_QUEUE.md` per channel. The LLM writes the caption + hashtags
from the script. Also surfaces the run to Paperclip oversight.

  env/bin/python3 content_engine/publish.py content_engine/runs/<run> --channel <slug> --platform tiktok
  env/bin/python3 content_engine/publish.py 'content_engine/runs/daily-curiosities-*' --channel daily-curiosities
"""
import argparse, glob, json, os, re, subprocess, sys
ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE); sys.path.insert(0, os.path.join(ENGINE, "agents"))
import llm
from director import spoken_lines
try:
    import paperclip_sync
except Exception:
    paperclip_sync = None

CAP_SYS = ("You write social captions for a short-form curiosity channel. Given the title and the "
           "short's spoken lines, return STRICT JSON {\"caption\":\"<1-2 sentence caption, ends with a "
           "question or CTA, no hashtags inside>\",\"hashtags\":[\"#tag\", ...8 lowercase, no spaces]}. "
           "Caption is punchy and sound-off friendly. JSON only.")

def _dur(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nk=1:nw=1", v], capture_output=True, text=True)
    try: return round(float(r.stdout.strip()), 1)
    except Exception: return 0.0

def _caption(title, lines):
    raw = llm.chat(CAP_SYS, f"TITLE: {title}\nLINES:\n" + "\n".join(f"- {l}" for l in lines),
                   tier="fast", temperature=0.6, max_tokens=160)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        d = json.loads(m.group(0))
        ht = d.get("hashtags", [])
        if isinstance(ht, str):                       # LLM sometimes returns a string, not a list
            ht = re.split(r"[\s,]+", ht)
        tags = []
        for t in ht:
            t = str(t).strip().lstrip("#")
            if len(t) >= 2:                           # drop empty / single-char fragments
                tags.append("#" + t)
        tags = tags[:8] or ["#curiosity", "#didyouknow", "#facts", "#shorts"]
        return d.get("caption", title), tags
    except Exception:
        return title, ["#curiosity", "#didyouknow", "#facts", "#shorts", "#learnontiktok"]

def make_manifest(run_dir, channel="", platform="tiktok"):
    run = os.path.basename(run_dir.rstrip("/")); out = os.path.join(run_dir, "out")
    bp = os.path.join(run_dir, "show_bible.json"); script = os.path.join(run_dir, "script.md")
    video = os.path.join(out, run + "_social.mp4")
    if not (os.path.exists(bp) and os.path.exists(video)):
        return None
    b = json.load(open(bp))
    lines = spoken_lines(open(script).read()) if os.path.exists(script) else []
    caption, hashtags = _caption(b.get("show", run), lines)
    thumb = os.path.join(out, run + "_thumb.jpg")
    man = {"run": run, "channel": channel, "platform": platform,
           "title": b.get("show", run), "hook": b.get("hook", ""),
           "caption": caption, "hashtags": hashtags,
           "video": os.path.abspath(video), "thumbnail": os.path.abspath(thumb) if os.path.exists(thumb) else "",
           "format": b.get("format", "social"), "resolution": b.get("resolution", [1080, 1920]),
           "duration_sec": _dur(video), "status": "ready"}
    json.dump(man, open(os.path.join(out, "publish.json"), "w"), indent=2)
    return man

def write_queue(channel, mans):
    """A human-readable posting queue for the channel."""
    qdir = os.path.join(ENGINE, "channels", channel); os.makedirs(qdir, exist_ok=True)
    lines = [f"# Publish queue — {channel}", "", f"{len(mans)} ready to post.", ""]
    for m in mans:
        lines += [f"## {m['title']}  ({m['duration_sec']}s · {m['platform']})",
                  f"- **Hook:** {m['hook']}",
                  f"- **Caption:** {m['caption']} {' '.join(m['hashtags'])}",
                  f"- **Video:** `{m['video']}`",
                  f"- **Thumb:** `{m['thumbnail']}`", ""]
    open(os.path.join(qdir, "PUBLISH_QUEUE.md"), "w").write("\n".join(lines))
    return os.path.join(qdir, "PUBLISH_QUEUE.md")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--channel", default="")
    ap.add_argument("--platform", default="tiktok")
    a = ap.parse_args()
    dirs = sorted(d for p in a.runs for d in glob.glob(p) if os.path.isdir(d))
    mans = []
    for d in dirs:
        m = make_manifest(d, a.channel, a.platform)
        if not m:
            print(f"  SKIP {os.path.basename(d)} (no finished video)"); continue
        if paperclip_sync:
            paperclip_sync.report_run(a.channel or "content-engine", m["run"], "ready-to-publish", m["video"])
        mans.append(m)
        print(f"  ✓ {m['title'][:34]:34s} {m['duration_sec']:>5}s  {' '.join(m['hashtags'][:4])}")
    if a.channel and mans:
        q = write_queue(a.channel, mans)
        if paperclip_sync:                       # one canonical project, rolled-up summary
            paperclip_sync.cleanup_duplicates(a.channel)
            paperclip_sync.set_channel_summary(
                a.channel, f"Content Engine channel · {len(mans)} shorts ready to publish "
                           f"({a.platform}) · see channels/{a.channel}/PUBLISH_QUEUE.md")
        print(f"\nqueue → {q}   ({len(mans)} ready, surfaced to Paperclip)")
