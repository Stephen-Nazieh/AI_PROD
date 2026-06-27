#!/usr/bin/env python3
"""Assemble the 'Median Detective' proof scene into (a) a watchable rough-cut mp4
and (b) an FCPXML timeline to open/finish in Final Cut Pro / Motion.

Editorial order: office (establish) → ledger (the numbers) → Manim B-roll (the
stat reveal) → realization. Narration over the whole thing + a quiet noir music bed.
"""
import subprocess, pathlib, tempfile, sys, wave, contextlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
SCENE = ROOT / "03_ASSETS" / "animation_pilots" / "median_detective"
CLIPS = SCENE / "clips"
AUDIO = SCENE / "audio"
OUT = SCENE / "median_detective_roughcut.mp4"
FCPXML = SCENE / "median_detective.fcpxml"
W, H, FPS = 1920, 1080, 24
BROLL = next((ROOT / "03_ASSETS/animation_pilots/median_detective/media").rglob("CaseFile.mp4"), None)


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def norm_segment(src, dst, trim=None):
    """Scale+pad any clip to 1920x1080@24 with a silent stereo track; optional trim (s)."""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS},format=yuv420p")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if trim:
        cmd += ["-t", str(trim)]
    cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", vf, "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-map", "0:v", "-map", "1:a", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    if not BROLL or not BROLL.exists():
        print("B-roll not found"); return 1
    seq = [
        (CLIPS / "01_office.mp4", None),
        (CLIPS / "02_ledger.mp4", None),
        (BROLL, 8.0),                       # trim the 12s B-roll to a tight insert
        (CLIPS / "03_realization.mp4", None),
    ]
    seq = [(p, t) for p, t in seq if p and p.exists()]
    if len(seq) < 2:
        print("not enough clips to assemble:", [str(p) for p, _ in seq]); return 1

    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        segs = []
        for i, (src, trim) in enumerate(seq):
            s = tmp / f"seg_{i:02d}.mp4"
            norm_segment(src, s, trim)
            segs.append(s)
        # concat normalized segments
        cl = tmp / "concat.txt"; cl.write_text("\n".join(f"file '{s}'" for s in segs))
        joined = tmp / "joined.mp4"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
                        "-safe", "0", "-i", str(cl), "-c", "copy", str(joined)], check=True, capture_output=True)
        total = dur(joined)

        # noir music bed sized to the cut
        music = AUDIO / "music_bed.wav"
        try:
            import logic_pro_scorer as M
            M.synthesize_music_bed(["tense", "dark"], total, music)
        except Exception as e:
            print("music synth skipped:", e); music = None

        narr = AUDIO / "narration.wav"
        # mix: narration full + music ducked under, video from the joined cut
        amix_inputs = ["-i", str(joined)]
        filt, maps = "", ["-map", "0:v"]
        if narr.exists() and music and music.exists():
            amix_inputs += ["-i", str(narr), "-i", str(music)]
            filt = "[2:a]volume=0.16[m];[1:a][m]amix=inputs=2:duration=longest[a]"
            maps += ["-map", "[a]"]
        elif narr.exists():
            amix_inputs += ["-i", str(narr)]; maps += ["-map", "1:a"]
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *amix_inputs]
        if filt:
            cmd += ["-filter_complex", filt]
        cmd += [*maps, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(OUT)]
        subprocess.run(cmd, check=True, capture_output=True)

    # ---- FCPXML timeline (clips on spine, narration + music on connected lanes) ----
    def frames(sec):
        return int(round(sec * FPS))
    def t(sec):
        return f"{frames(sec)*100}/{FPS*100}s"
    fmt = f'<format id="r1" name="FFVideoFormat1080p{FPS}" frameDuration="100/{FPS*100}s" width="{W}" height="{H}"/>'
    assets, spine, offset, rid = [], [], 0.0, 2
    asset_ids = {}
    for src, trim in seq:
        d = trim or dur(src)
        aid = f"r{rid}"; rid += 1
        assets.append(f'<asset id="{aid}" name="{src.stem}" start="0s" duration="{t(d)}" '
                      f'hasVideo="1" hasAudio="1" format="r1"><media-rep kind="original-media" '
                      f'src="{src.resolve().as_uri()}"/></asset>')
        spine.append(f'<asset-clip name="{src.stem}" ref="{aid}" offset="{t(offset)}" '
                     f'duration="{t(d)}" start="0s"/>')
        offset += d
    total = offset
    # narration as a connected clip on lane -1 from t=0
    extra = ""
    narr = AUDIO / "narration.wav"
    if narr.exists():
        nid = f"r{rid}"; rid += 1
        nd = dur(narr)
        assets.append(f'<asset id="{nid}" name="narration" start="0s" duration="{t(nd)}" '
                      f'hasAudio="1"><media-rep kind="original-media" src="{narr.resolve().as_uri()}"/></asset>')
        extra = f'<asset-clip name="narration" ref="{nid}" lane="-1" offset="0s" duration="{t(nd)}" start="0s"/>'
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
  <resources>
    {fmt}
    {''.join(assets)}
  </resources>
  <library>
    <event name="Median Detective">
      <project name="Median Detective — rough cut">
        <sequence duration="{t(total)}" format="r1" tcStart="0s">
          <spine>
            {''.join(spine)}
            {extra}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>'''
    FCPXML.write_text(xml, encoding="utf-8")

    print(f"ROUGHCUT {OUT}  ({dur(OUT):.1f}s)")
    print(f"FCPXML   {FCPXML}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
