#!/usr/bin/env python3
"""CONTENT ENGINE — autonomous SCHEDULER.

One run = pick the next channel (round-robin), have the brain invent fresh non-repeating ideas for
its niche, produce a batch (script → cast → render → B-roll → captions → QA → manifest → queue),
and log it. Content is auto-GENERATED but not auto-POSTED — finished shorts land in the channel's
PUBLISH_QUEUE.md for your review (until you wire credentials + opt into auto-post).

Designed to be cron-safe: if the local LLM servers are down it logs and exits 0 (no crash).

  env/bin/python3 content_engine/scheduler.py            # one cycle (default 2 shorts, next channel)
  env/bin/python3 content_engine/scheduler.py --count 3 --channel weird-history
"""
import argparse, datetime, json, os, re, subprocess, sys
ENGINE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(ENGINE)
PY = os.path.join(ROOT, "env/bin/python3")
sys.path.insert(0, ENGINE); sys.path.insert(0, os.path.join(ENGINE, "memory"))
import llm
CHAN_DIR = os.path.join(ENGINE, "channels")
STATE = os.path.join(ENGINE, "memory", "scheduler_state.json")
LOGDIR = os.path.join(ENGINE, "logs"); os.makedirs(LOGDIR, exist_ok=True)

def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(os.path.join(LOGDIR, f"scheduler-{datetime.date.today():%Y%m}.log"), "a") as f:
        f.write(line + "\n")

def channels():
    if not os.path.isdir(CHAN_DIR): return []
    return sorted(d for d in os.listdir(CHAN_DIR) if os.path.isfile(os.path.join(CHAN_DIR, d, "channel.json")))

def next_channel(override=None):
    chans = channels()
    if not chans: return None
    if override and override in chans: return override
    st = {}
    if os.path.exists(STATE):
        try: st = json.load(open(STATE))
        except Exception: pass
    i = (st.get("last_index", -1) + 1) % len(chans)
    st["last_index"] = i; json.dump(st, open(STATE, "w"), indent=2)
    return chans[i]

def brand(slug):
    try: return json.load(open(os.path.join(CHAN_DIR, slug, "channel.json")))
    except Exception: return {"name": slug, "niche": "", "pillars": []}

def used_topics(slug):
    p = os.path.join(CHAN_DIR, slug, "topics_used.txt")
    return [l.strip() for l in open(p)] if os.path.exists(p) else []

def remember_topics(slug, ideas):
    p = os.path.join(CHAN_DIR, slug, "topics_used.txt")
    with open(p, "a") as f:
        for i in ideas: f.write(i.strip() + "\n")

def seed_ideas(slug, n, recent_keys):
    """Curated, hand-verified ideas (channels/<slug>/idea_seeds.txt) take priority over the LLM —
    the reliable source of factually-true content. Returns unused seeds, up to n."""
    p = os.path.join(CHAN_DIR, slug, "idea_seeds.txt")
    if not os.path.exists(p): return []
    out = []
    for line in open(p):
        t = line.strip()
        if not t or t.startswith("#"): continue
        if re.sub(r"\W+", "", t.lower())[:40] in recent_keys: continue
        out.append(t)
        if len(out) >= n: break
    return out

def fresh_ideas(slug, n):
    b = brand(slug); recent = used_topics(slug)[-60:]
    recent_keys = {re.sub(r"\W+", "", t.lower())[:40] for t in recent}
    seeded = seed_ideas(slug, n, recent_keys)        # verified seeds first
    if len(seeded) >= n:
        return seeded[:n]
    n_llm = n - len(seeded)
    sysmsg = (f"You are the content strategist for '{b.get('name', slug)}'. Niche: {b.get('niche','')}. "
              f"Pillars: {', '.join(b.get('pillars', []))}. Propose {n} FRESH short-video ideas. "
              "CRITICAL: each must be a REAL, well-documented, verifiable fact or true historical event "
              "— NEVER an invented claim, fake statistic, or made-up story. Pick a genuinely true thing "
              "most people don't know, surprising enough to stop a scroll. Each ONE line, no numbering, "
              "one idea per line, no preamble.")
    usr = "Already used (do NOT repeat or rephrase these):\n" + "\n".join(f"- {t}" for t in recent[-40:]) \
          if recent else "Give bold, scroll-stopping ideas."
    raw = llm.chat(sysmsg, usr, tier="smart", temperature=0.9, max_tokens=400)
    ideas = list(seeded)
    seen = set(recent_keys) | {re.sub(r"\W+", "", s.lower())[:40] for s in seeded}
    for line in raw.splitlines():
        t = re.sub(r"^[\-\d.)\s]+", "", line).strip()
        if len(t.split()) < 4: continue
        k = re.sub(r"\W+", "", t.lower())[:40]
        if k and k not in seen:
            seen.add(k); ideas.append(t)
        if len(ideas) >= n: break
    return ideas[:n]

def run_cycle(count, channel_override=None, fmt="social", length="30s"):
    health = {}
    try: health = llm.health()
    except Exception: pass
    if not health.get("smart"):
        log("SKIP — local LLM (smart) not reachable; start the mlx servers."); return
    slug = next_channel(channel_override)
    if not slug:
        log("SKIP — no channels found."); return
    ideas = fresh_ideas(slug, count)
    if not ideas:
        log(f"SKIP — no fresh ideas generated for {slug}."); return
    remember_topics(slug, ideas)
    log(f"CYCLE → channel={slug} · {len(ideas)} ideas: " + " | ".join(i[:50] for i in ideas))
    env = dict(os.environ); env.setdefault("BROLL_BACKEND", "auto")
    made = 0
    for idx, idea in enumerate(ideas, 1):
        run = f"{slug}-auto-{datetime.datetime.now():%Y%m%d-%H%M%S}-{idx}"
        try:
            r = subprocess.run([PY, "content_engine/engine.py", "make", "--run", run, "--idea", idea,
                                "--format", fmt, "--channel", slug, "--length", length],
                               cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=2400)
            ok = "✅ run" in r.stdout
            made += 1 if ok else 0
            log(f"  [{idx}/{len(ideas)}] {'OK ' if ok else 'FAIL'} {run} — {idea[:60]}")
        except subprocess.TimeoutExpired:
            log(f"  [{idx}/{len(ideas)}] TIMEOUT {run}")
    # refresh the channel publish queue
    try:
        subprocess.run([PY, "content_engine/publish.py", os.path.join("content_engine/runs", slug + "-*"),
                        "--channel", slug, "--platform", brand(slug).get("platform", "tiktok")],
                       cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    except Exception:
        pass
    log(f"CYCLE DONE → {made}/{len(ideas)} produced for {slug}. Review: channels/{slug}/PUBLISH_QUEUE.md")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--channel", default=None)
    ap.add_argument("--format", default="social"); ap.add_argument("--length", default="30s")
    a = ap.parse_args()
    run_cycle(a.count, a.channel, a.format, a.length)
