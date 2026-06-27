#!/usr/bin/env python3
"""Synthesize Episode 1 per-character dialogue (one Kokoro voice per role) and write
a timing manifest the animatic assembler uses. Model loads once (in-process)."""
import json, pathlib, sys, wave, contextlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
import kokoro_tts as K

VO_DIR = ROOT / "business_units/deparadigm-media/ap-stats/production/S01E01/06-audio/vo"

# (id, speaker, kokoro voice, line, panel-or-broll cue for the assembler)
VOICES = {"maya": "af_bella", "nina": "af_nicole", "okafor": "bm_george", "investor": "am_adam"}
LINES = [
    ("01", "maya", "Because our average user earns ninety-two thousand dollars, advertisers reach a premium audience.", "p1_pitch_night"),
    ("02", "nina", "Average of what, though? You added everyone up. Including whoever's at the very top.", "p2_nina_doubt"),
    ("03", "maya", "Most rows, thirty, forty thousand. And then... four and a half million dollars. A few big fish.", "p3_whale_screen"),
    ("04", "nina", "Whales. You have whales.", "BROLL1"),
    ("05", "maya", "The mean adds every income and splits it evenly. Three whales worth eleven million, shared across eight thousand people on paper. The average isn't lying. It's answering a question nobody asked.", "p4_whiteboard"),
    ("06", "okafor", "So don't ask what everyone earns on average. Line them up, poorest to richest, and find who's standing in the middle. The median. Half earn less, half earn more.", "p5_cafe_mentor"),
    ("07", "okafor", "Your data is skewed right. A long tail of money, pulling the mean toward it. The median doesn't flinch.", "BROLL2"),
    ("08", "maya", "Thirty-eight thousand dollars. The honest number.", "p6_slide_rebuild"),
    ("09", "maya", "Ninety-two is the mean. Three ultra-earners drag it up. Thirty-eight is the median, the user actually in the middle. I'd rather you trust the number than the headline.", "p7_pitch_room"),
    ("10", "investor", "Most founders show me the ninety-two and hope I don't ask. Send me the cohort breakdown. Let's talk terms.", "p8_investor_nod"),
]


def wav_dur(p):
    with contextlib.closing(wave.open(str(p), "rb")) as w:
        return w.getnframes() / float(w.getframerate())


def main():
    VO_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for lid, speaker, text, cue in LINES:
        out = VO_DIR / f"{lid}_{speaker}.wav"
        r = K.speak(text, str(out), voice=VOICES[speaker], speed=0.98)
        if r.get("status") != "ok" or not out.exists():
            print(f"  FAILED {lid} {speaker}: {r.get('message','?')}")
            continue
        d = round(wav_dur(out), 2)
        manifest.append({"id": lid, "speaker": speaker, "cue": cue, "file": str(out), "dur": d})
        print(f"  {lid} {speaker} ({d}s) cue={cue}")
    (VO_DIR / "vo_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"EP1_VO_DONE {len(manifest)}/{len(LINES)}  total={round(sum(m['dur'] for m in manifest),1)}s")
    return 0 if manifest else 1


if __name__ == "__main__":
    sys.exit(main())
