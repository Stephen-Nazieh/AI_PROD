#!/usr/bin/env python3
"""CONTENT ENGINE — CHANNEL FACTORY. Spin up a new YouTube (or any) channel in one command.

A channel = a brand + voice + audience + format defaults the agents use. The local LLM drafts
the brief from a name + niche; you can edit channels/<slug>/channel.json afterward.

  env/bin/python3 content_engine/new_channel.py <slug> --name "…" --niche "…" \
        [--format movie|talking_head|social|explainer] [--platform youtube]
  env/bin/python3 content_engine/new_channel.py --list
"""
import argparse, json, os, re, sys
ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE)
import llm

CHANNELS = os.path.join(ENGINE, "channels")

def draft(name, niche):
    system = ("You are a YouTube channel strategist. Given a channel name and niche, define its "
              "brand voice and audience crisply. Output STRICT JSON only with keys: "
              "voice (tone/register in one sentence), audience (who it's for), "
              "do (a comma-list of things to always do), avoid (a comma-list of things to never do), "
              "pillars (3-5 recurring content pillars as a comma-list).")
    raw = llm.chat(system, f"Channel: {name}\nNiche: {niche}\nOutput the JSON.",
                   tier="fast", temperature=0.6, max_tokens=600)
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)) if m else {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--name", default=None); ap.add_argument("--niche", default="")
    ap.add_argument("--format", default="movie"); ap.add_argument("--platform", default="youtube")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        os.makedirs(CHANNELS, exist_ok=True)
        for c in sorted(os.listdir(CHANNELS)):
            p = os.path.join(CHANNELS, c, "channel.json")
            if os.path.exists(p):
                d = json.load(open(p)); print(f"  {c:18s} {d.get('name','')} — {d.get('niche','')}")
        return
    if not a.slug:
        ap.error("provide a channel <slug> (or --list)")
    name = a.name or a.slug.replace("-", " ").title()
    print(f"[channel-factory] drafting brand for '{name}' via local LLM…")
    brief = draft(name, a.niche)
    cfg = {"slug": a.slug, "name": name, "niche": a.niche,
           "platform": a.platform, "default_format": a.format, **brief}
    # register as a Paperclip project (business oversight) — best-effort
    try:
        import paperclip_sync
        pid = paperclip_sync.register_channel(a.slug, name, a.niche)
        if pid: cfg["paperclip_project_id"] = pid
    except Exception:
        pid = None
    d = os.path.join(CHANNELS, a.slug); os.makedirs(d, exist_ok=True)
    json.dump(cfg, open(os.path.join(d, "channel.json"), "w"), indent=2)
    print(f"[channel-factory] created channels/{a.slug}/channel.json"
          + (f"  +  Paperclip project {pid[:8]}…" if pid else "  (Paperclip offline)"))
    print(f"    voice:    {cfg.get('voice','')}")
    print(f"    audience: {cfg.get('audience','')}")
    print(f"    pillars:  {cfg.get('pillars','')}")
    print(f"\n  Make content for it:\n    engine.py write --run <name> --idea \"…\" --channel {a.slug}")

if __name__ == "__main__":
    main()
