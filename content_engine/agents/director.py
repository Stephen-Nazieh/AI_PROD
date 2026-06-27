#!/usr/bin/env python3
"""Content Engine — MOVIE DIRECTOR agent.

approved script + studio assets  ->  producer-ready show_bible.json (casting + sets).
Craft lives in director.skill.md. Casting/staging decisions are made by the local LLM.

Usage:
  env/bin/python3 content_engine/agents/director.py --script <approved.md> --out <show_bible.json>
"""
import argparse, json, os, re, sys
ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE); sys.path.insert(0, os.path.join(ENGINE, "memory"))
import llm
import memory

SKILL = os.path.join(ENGINE, "agents", "director.skill.md")
ASSETS = json.load(open(os.path.join(ENGINE, "config", "assets.json")))
CHARDIR = os.path.join(ROOT, "06_SHARED_ASSETS/external-assets/characters")

# ── PER-FORMAT PRODUCERS (staging + coverage presets) ──────────────────────
# 16:9 widescreen (movie/explainer/talking-head)
BLOCKING_WIDE = {"2": [{"pos": [-0.7, 0.05, 0.0], "rot": -65}, {"pos": [0.7, 0.05, 0.0], "rot": 65}],
                 "1": [{"pos": [0.3, -0.2, 0.0], "rot": 0}]}
COVERAGE_WIDE = {"establish2": {"tgt": "two", "off": [0.0, 2.95, 0.30], "lens": 34, "fstop": 4.0, "push": 0.28, "look_dz": -0.05},
                 "single2": {"off": [0.85, 1.95, 0.10], "lens": 72, "fstop": 2.2, "push": 0.18, "look": 0.82},
                 "single1": {"off": [0.12, 2.0, 0.04], "lens": 55, "fstop": 2.0, "push": 0.30, "look": 0.78}}
# 9:16 vertical (social/shorts): subjects fill the tall frame — closer + longer lens, tighter
# two-shot (the wide establish reads small in vertical), faces framed high.
BLOCKING_VERT = {"2": [{"pos": [-0.55, 0.05, 0.0], "rot": -72}, {"pos": [0.55, 0.05, 0.0], "rot": 72}],
                 "1": [{"pos": [0.0, -0.1, 0.0], "rot": 0}]}
COVERAGE_VERT = {"establish2": {"tgt": "two", "off": [0.0, 2.1, 0.22], "lens": 48, "fstop": 2.8, "push": 0.18, "look_dz": 0.0},
                 "single2": {"off": [0.55, 1.5, 0.14], "lens": 90, "fstop": 2.0, "push": 0.12, "look": 0.88},
                 "single1": {"off": [0.04, 1.55, 0.12], "lens": 80, "fstop": 2.0, "push": 0.16, "look": 0.88}}
# talking-head: single presenter, clean medium, direct-to-camera (reuse wide single1, centered)
PRODUCERS = {
    "movie":        (BLOCKING_WIDE, COVERAGE_WIDE),
    "explainer":    (BLOCKING_WIDE, COVERAGE_WIDE),
    "talking_head": (BLOCKING_WIDE, COVERAGE_WIDE),
    "social":       (BLOCKING_VERT, COVERAGE_VERT),
}
MUSIC = {"dark": "dark", "warm": "warm", "tense": "tense", "neutral": "neutral", "none": None}  # → 06_SHARED_ASSETS/music-beds/<mood>.wav

# ── CASTING VARIETY ────────────────────────────────────────────────────────
# Gender-consistent (avatar, voice) presenter identities, visibly distinct, so a
# channel batch doesn't reuse one face/voice. Rotated by a per-run seed.
import hashlib
PRESENTER_POOL = [
    ("1954612987776852107", "af_heart"),    # purple ponytail · warm F
    ("8590256991748008892", "af_sarah"),    # brown bob, cardigan · calm F
    ("6258096374260045189", "af_nova"),     # pink streetwear · bright F
    ("24386148582032405",   "bf_emma"),     # blonde, blue dress · poised British F
    ("3955039427104616066", "af_aoede"),    # yellow coat · soft F
    ("8329890252317737768", "am_onyx"),     # dark jacket (reads male) · deep M
    ("3361246599912172955", "am_michael"),  # blue hair, glasses (androgynous) · clear M
    ("6493143135142452442", "af_nicole"),   # purple uniform · intimate F
    ("7441299522613423042", "af_bella"),    # black striped dress · expressive F
    ("481828024975048142",  "af_nova"),     # cat-ears, playful · bright F
]
NARRATOR = {"HOST", "NARRATOR", "VO", "V.O.", "VOICE", "YOU", "ANNOUNCER", "PRESENTER"}

def _seed_ordinal(seed):
    """Prefer the run's numeric index (e.g. '...-04-...') so a batch spreads evenly across the
    pool; fall back to a content hash for ad-hoc runs with no index."""
    m = re.search(r"-(\d{1,3})-", seed)
    if m: return int(m.group(1))
    m = re.search(r"\d+", seed)
    if m: return int(m.group())
    return int(hashlib.md5(seed.encode()).hexdigest(), 16)

def pick_presenter(seed, offset=0):
    return PRESENTER_POOL[(_seed_ordinal(seed) + offset) % len(PRESENTER_POOL)]

def clean_hook(h):
    """Strip cheesy filler suffixes the small model tacks on (— WOW!/REALLY?/INSANE!)."""
    h = re.sub(r"\s*[—\-:,]\s*(wow|really|insane|mind[ -]?blown|amazing|shocking|crazy|whoa|"
               r"no way|unbelievable|incredible|wild|so cool)[!?.\s]*$", "", h or "", flags=re.I)
    return h.strip().rstrip(",")

def extract(script_text):
    """Heuristic extraction of locations + character cues from a screenplay (no predefined list)."""
    locs = []
    for m in re.finditer(r"^###\s+(INT\.|EXT\.)\s*(.+)$", script_text, re.M):
        s = m.group(2).strip()
        parts = [p.strip() for p in re.split(r"\s+—\s+|\s+-\s+", s)]
        key = f"{' — '.join(parts[:-1])}|{parts[-1]}" if len(parts) >= 2 else f"{s}|DAY"
        if key not in locs: locs.append(key)
    cues, bad = [], {"INT", "EXT", "B-ROLL", "BROLL", "CONT'D", "O.S.", "V.O.", "FADE", "CUT", "SMASH"}
    for line in script_text.splitlines():
        t = re.sub(r"\s*\(.*?\)\s*$", "", line.strip())
        if re.fullmatch(r"[A-Z][A-Z'.\- ]{1,22}", t) and t not in bad and len(t.split()) <= 3:
            if t not in cues: cues.append(t)
    return locs, cues

def spoken_lines(script_text):
    """The actual spoken/narration lines — what the title + hook must be derived FROM."""
    out, cue = [], False
    for line in script_text.splitlines():
        t = line.strip()
        if not t or t.startswith("#") or t.startswith(">") or t.startswith("<"):
            cue = False; continue
        if re.fullmatch(r"[A-Z][A-Z'.\- ]{1,22}", re.sub(r"\s*\(.*?\)\s*$", "", t)):
            cue = True; continue                       # a character cue → next non-empty line is dialogue
        if cue or not re.match(r"(INT\.|EXT\.)", t):
            out.append(t)
    return [l for l in out if len(l.split()) > 1][:12]

def direct(script_text):
    locs, chars = extract(script_text)
    lines = spoken_lines(script_text)
    system = (open(SKILL).read()
              + "\n\n## STUDIO ASSETS (cast/stage only from these)\n"
              + "AVATARS:\n" + "\n".join(f"  {k}: {v}" for k, v in ASSETS["avatars"].items())
              + "\nVOICES:\n" + "\n".join(f"  {k}: {v}" for k, v in ASSETS["voices"].items())
              + "\nSETS:\n" + "\n".join(f"  {k}: {v}" for k, v in ASSETS["sets"].items())
              + memory.learnings_for("director"))
    user = ("THE SCRIPT'S ACTUAL LINES (derive the title + hook from the single most surprising fact "
            "HERE — never from the location, never copy an example from the skill):\n"
            + "\n".join(f"  • {l}" for l in lines)
            + f"\n\nCHARACTERS to cast: {chars}\nLOCATIONS to stage: {locs}\n\n"
            "Make the casting + staging decisions. Output STRICT JSON only.")
    raw = llm.chat(system, user, tier="smart", temperature=0.4, max_tokens=1500)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise SystemExit(f"director: LLM did not return JSON:\n{raw[:300]}")
    plan = json.loads(m.group(0))
    return plan, locs, chars

# format → render shape + producer hint (native vertical for social, etc.)
FORMAT_RES = {"social": [1080, 1920], "talking_head": [1920, 1080], "movie": [1920, 1080], "explainer": [1920, 1080]}

def build_bible(plan, fmt="movie", seed=""):
    chars = {}
    plan_chars = plan.get("characters", {})
    single = len(plan_chars) <= 1
    for i, (name, c) in enumerate(plan_chars.items()):
        av = c.get("avatar"); voice = c.get("voice", "af_heart")
        # Rotate narrators / single-host pieces through the presenter pool for batch variety.
        # Named multi-character casts keep the LLM's gender-matched choices.
        if seed and (single or name.upper() in NARRATOR):
            av, voice = pick_presenter(seed, i)
        vrm = os.path.join("06_SHARED_ASSETS/external-assets/characters", f"{av}.vrm.glb")
        chars[name.upper()] = {"vrm": vrm, "voice": voice,
                               "gesture": float(c.get("gesture", 0.8))}
    locs = {}
    for key, l in plan.get("locations", {}).items():
        setid = l.get("set", "studio")
        if setid not in ASSETS["sets"]: setid = "studio"
        entry = {"set": setid}
        bed = MUSIC.get(l.get("music", "neutral"))
        if bed: entry["music"] = bed
        locs[key] = entry
    blocking, coverage = PRODUCERS.get(fmt, PRODUCERS["movie"])
    visuals = [str(v).strip() for v in plan.get("visuals", []) if str(v).strip()]
    return {"show": plan.get("title", "Untitled"), "hook": clean_hook(plan.get("hook", "")), "tagline": "", "format": fmt,
            "resolution": FORMAT_RES.get(fmt, [1920, 1080]), "fps": 24,
            "characters": chars, "locations": locs, "visuals": visuals,
            "subject": str(plan.get("subject", "")).strip(),
            "blocking": blocking, "coverage": coverage, "brolls": {}}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", default=os.path.join(ENGINE, "config", "show_bible.json"))
    a = ap.parse_args()
    text = open(a.script).read()
    metap = os.path.join(os.path.dirname(a.script), "meta.json")
    fmt = json.load(open(metap)).get("format", "movie") if os.path.exists(metap) else "movie"
    print(f"[director] casting + staging via local Qwen-32B… (format={fmt})")
    plan, locs, chars = direct(text)
    seed = os.path.basename(os.path.dirname(os.path.abspath(a.script)))   # run name → stable per-piece variety
    bible = build_bible(plan, fmt, seed=seed)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(bible, open(a.out, "w"), indent=2)
    print(f"[director] {len(chars)} characters, {len(locs)} locations → {a.out}")
    for nm, c in bible["characters"].items():
        print(f"    {nm:12s} → avatar {os.path.basename(c['vrm']).replace('.vrm.glb','')[:8]}… "
              f"voice={c['voice']} gesture={c['gesture']}")
    for k, v in bible["locations"].items():
        print(f"    {k[:38]:38s} → set={v['set']}")

if __name__ == "__main__":
    main()
