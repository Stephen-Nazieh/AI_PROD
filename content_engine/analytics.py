#!/usr/bin/env python3
"""CONTENT ENGINE — ANALYTICS → MEMORY (close the self-improvement loop).

Craft learnings alone don't tell the system what actually WORKS. This ingests per-post metrics
(views, watch-time, likes — exported from TikTok/YouTube), joins them to each run's production
choices (avatar, voice, hook, length, B-roll), and turns the aggregate into learnings the
scriptwriter + director read on the next run. Revenue follows retention, so the default KPI is
completion rate.

  analytics.py record --run <run> --views 1200 --completion 0.61 --likes 90
  analytics.py import <metrics.csv|json>      # bulk ingest (column/key: run + kpis)
  analytics.py analyze [--kpi completion]     # aggregate → write learnings
"""
import argparse, glob, json, os, statistics, sys
ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE); sys.path.insert(0, os.path.join(ENGINE, "memory"))
import memory
METRICS = os.path.join(ENGINE, "memory", "metrics.jsonl")
RUNS = os.path.join(ENGINE, "runs")
KPIS = ("views", "completion", "watch_time", "likes", "shares", "comments")

def record(run, channel="", platform="", **kpis):
    rec = {"run": run, "channel": channel, "platform": platform}
    for k, v in kpis.items():
        if v is not None:
            try: rec[k] = float(v)
            except (TypeError, ValueError): rec[k] = v
    with open(METRICS, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec

def _load():
    if not os.path.exists(METRICS): return []
    out = []
    for line in open(METRICS):
        line = line.strip()
        if line:
            try: out.append(json.loads(line))
            except Exception: pass
    # last record per run wins (re-ingest overwrites)
    by_run = {}
    for r in out: by_run[r.get("run")] = {**by_run.get(r.get("run"), {}), **r}
    return list(by_run.values())

def _dims(run):
    """Production choices for a run, for correlation."""
    d = os.path.join(RUNS, run)
    bib = os.path.join(d, "show_bible.json")
    if not os.path.exists(bib): return {}
    b = json.load(open(bib))
    ch = b.get("characters", {}); first = next(iter(ch.values()), {}) if ch else {}
    pj = os.path.join(d, "out", "publish.json")
    man = json.load(open(pj)) if os.path.exists(pj) else {}
    hook = b.get("hook", "")
    return {"avatar": os.path.basename(first.get("vrm", "")).replace(".vrm.glb", "")[:8],
            "voice": first.get("voice", ""),
            "hook_words": len(hook.split()),
            "hook_is_question": hook.strip().endswith("?"),
            "duration": man.get("duration_sec", 0),
            "has_broll": bool(b.get("visuals"))}

def _bucket(v, edges, labels):
    for e, l in zip(edges, labels):
        if v <= e: return l
    return labels[-1]

def analyze(kpi="completion", min_n=8):
    rows = [{**r, **_dims(r["run"])} for r in _load() if kpi in r]
    if len(rows) < min_n:
        print(f"[analytics] only {len(rows)} posts have '{kpi}' — need {min_n} for reliable signal. "
              "Ingest more (analytics.py import …).")
        return []
    learnings = []
    def group(keyfn, name, render):
        buckets = {}
        for r in rows:
            try: k = keyfn(r)
            except Exception: continue
            if k is None or k == "": continue
            buckets.setdefault(k, []).append(r[kpi])
        buckets = {k: v for k, v in buckets.items() if len(v) >= 2}
        if len(buckets) < 2: return
        avg = {k: statistics.mean(v) for k, v in buckets.items()}
        best = max(avg, key=avg.get); worst = min(avg, key=avg.get)
        if avg[best] - avg[worst] < 0.05 * (avg[worst] or 1): return    # spread too small to trust
        learnings.append(render(best, worst, avg, buckets))
    group(lambda r: r["voice"], "voice",
          lambda b, w, a, n: f"VOICE signal: '{b}' averages {a[b]:.2f} {kpi} vs '{w}' at {a[w]:.2f} "
                             f"(n={len(n[b])}/{len(n[w])}). Prefer '{b}'-register voices for this channel.")
    group(lambda r: r["avatar"], "avatar",
          lambda b, w, a, n: f"AVATAR signal: presenter {b} averages {a[b]:.2f} {kpi} vs {w} at {a[w]:.2f}. "
                             f"Favor {b}-type looks.")
    group(lambda r: "question-hook" if r["hook_is_question"] else "statement-hook", "hook",
          lambda b, w, a, n: f"HOOK signal: {b} outperforms {w} on {kpi} ({a[b]:.2f} vs {a[w]:.2f}). "
                             f"Lead with {b.split('-')[0]} hooks.")
    group(lambda r: _bucket(r["duration"], [12, 20, 35], ["<12s", "12-20s", "20-35s", ">35s"]), "length",
          lambda b, w, a, n: f"LENGTH signal: {b} shorts average {a[b]:.2f} {kpi} vs {w} at {a[w]:.2f}. "
                             f"Target ~{b} runtime.")
    group(lambda r: "with-broll" if r["has_broll"] else "no-broll", "broll",
          lambda b, w, a, n: f"B-ROLL signal: {b} averages {a[b]:.2f} {kpi} vs {w} at {a[w]:.2f}. "
                             f"{'Keep topical B-roll.' if b=='with-broll' else 'Reconsider B-roll use.'}")
    for L in learnings:
        agent = "director" if L.startswith(("VOICE", "AVATAR")) else "scriptwriter"
        memory.add_learning(agent, "[data] " + L)
        print(f"  → ({agent}) {L}")
    print(f"[analytics] wrote {len(learnings)} data-driven learning(s) from {len(rows)} posts.")
    return learnings

def _import(path):
    rows = []
    if path.endswith(".json"):
        data = json.load(open(path)); rows = data if isinstance(data, list) else data.get("rows", [])
    else:
        import csv
        rows = list(csv.DictReader(open(path)))
    n = 0
    for r in rows:
        run = r.get("run") or r.get("Run") or r.get("id")
        if not run: continue
        kpis = {k: r[k] for k in KPIS if k in r and r[k] not in ("", None)}
        record(run, r.get("channel", ""), r.get("platform", ""), **kpis); n += 1
    print(f"[analytics] imported {n} rows → {METRICS}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record"); rec.add_argument("--run", required=True)
    rec.add_argument("--channel", default=""); rec.add_argument("--platform", default="")
    for k in KPIS: rec.add_argument(f"--{k}", default=None)
    imp = sub.add_parser("import"); imp.add_argument("path")
    an = sub.add_parser("analyze"); an.add_argument("--kpi", default="completion"); an.add_argument("--min-n", type=int, default=8)
    a = ap.parse_args()
    if a.cmd == "record":
        print(record(a.run, a.channel, a.platform, **{k: getattr(a, k) for k in KPIS}))
    elif a.cmd == "import":
        _import(a.path)
    elif a.cmd == "analyze":
        analyze(a.kpi, a.min_n)
