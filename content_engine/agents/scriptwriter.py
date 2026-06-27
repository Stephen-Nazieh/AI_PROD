#!/usr/bin/env python3
"""Content Engine — SCRIPTWRITER agent.

idea + spec  ->  production-ready script (Markdown screenplay the producers parse).
Craft lives in scriptwriter.skill.md (edit that to improve quality — no code change).

Usage:
  env/bin/python3 content_engine/agents/scriptwriter.py \
      --idea "a detective who interrogates a number" \
      --format movie --platform youtube --channel <name> --length "3 min" --out script.md
"""
import argparse, os, sys
ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ENGINE); sys.path.insert(0, os.path.join(ENGINE, "memory"))
import llm
import memory

SKILL = os.path.join(ENGINE, "agents", "scriptwriter.skill.md")

FORMAT_GUIDES = {
    "movie": "## Format: SHORT FILM / SCENE\nWrite a story with 1–4 scenes, real characters with "
             "distinct voices, dialogue, and a turn. Use B-ROLL only at genuine beats. Aim for "
             "drama that carries the idea.",
    "talking_head": "## Format: TALKING-HEAD\nWrite a single-presenter piece. ONE scene heading "
             "(e.g. `### INT. STUDIO — DAY`), a character named `HOST`, and the whole piece as the "
             "HOST's spoken lines (break into short paragraphs as separate HOST cues). Conversational, "
             "direct-to-camera. B-ROLL marks where a cutaway/graphic supports a point.",
    "social": "## Format: SOCIAL / SHORT (vertical 9:16, 15–60s)\nMaximum hook density. ONE scene, a "
             "`HOST` (or 2 quick characters). The FIRST spoken line must stop the scroll — a concrete "
             "image, bold claim, or question (NOT 'In this video…' or any preamble). One idea, one "
             "turn, one button.\n"
             "WRITTEN FOR SOUND-OFF: the audience reads burned-in captions, so every spoken line is "
             "ALSO a caption. Keep each HOST/character cue to ONE short sentence (≤12 words) that reads "
             "cleanly on screen; split a long thought into separate consecutive cues. No stage prose the "
             "viewer can't see. 5–9 punchy lines total. End on one line that lands.",
    "explainer": "## Format: EXPLAINER\nTeach ONE concept through a concrete story or example. A "
             "`HOST` narrates; B-ROLL inserts visualize the key 'aha' beats. Accuracy is non-"
             "negotiable. End on the single takeaway.",
}

def load_channel(channel):
    if not channel:
        return ""
    p = os.path.join(ENGINE, "channels", channel, "channel.json")
    if os.path.exists(p):
        import json
        c = json.load(open(p))
        return (f"\n## Channel: {c.get('name', channel)}\nVoice/tone: {c.get('voice','')}\n"
                f"Audience: {c.get('audience','')}\nDo: {c.get('do','')}\nAvoid: {c.get('avoid','')}\n")
    return f"\n## Channel: {channel}\n"

def write_script(idea, fmt, platform, channel, length, extra=""):
    system = (open(SKILL).read() + "\n\n" + FORMAT_GUIDES.get(fmt, FORMAT_GUIDES["movie"])
              + load_channel(channel) + memory.learnings_for("scriptwriter"))
    user = (f"IDEA: {idea}\n\nFORMAT: {fmt}\nPLATFORM: {platform or 'youtube'}\n"
            f"LENGTH TARGET: {length or '2-3 min'}\n{extra}\n\n"
            "Write the production-ready script now, in the strict Markdown screenplay format. "
            "Output ONLY the script.")
    return llm.chat(system, user, tier="smart", temperature=0.75, max_tokens=2200)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--idea", required=True)
    ap.add_argument("--format", default="movie", choices=list(FORMAT_GUIDES))
    ap.add_argument("--platform", default="youtube")
    ap.add_argument("--channel", default=None)
    ap.add_argument("--length", default="2-3 min")
    ap.add_argument("--notes", default="", help="extra direction for the writer")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    print(f"[scriptwriter] idea→script  (format={a.format}, brain=smart/Qwen-32B)…")
    script = write_script(a.idea, a.format, a.platform, a.channel, a.length, a.notes)
    if script.startswith("ERROR"):
        print(script); sys.exit(1)
    out = a.out or os.path.join(ENGINE, "config", "draft_script.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(script)
    print(f"[scriptwriter] wrote {out}  ({len(script.split())} words)\n")
    print("──── DRAFT (vet / edit before producing) " + "─" * 30)
    print(script[:1400] + ("\n…\n" if len(script) > 1400 else ""))

if __name__ == "__main__":
    main()
