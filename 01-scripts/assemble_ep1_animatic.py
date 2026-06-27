#!/usr/bin/env python3
"""Assemble the Episode 1 animatic: per-character VO drives the edit — each panel gets
a Ken Burns move for its line's duration; B-roll cues show the Manim stat clip. Concat
+ a music bed under it. Output → production/S01E01/09-deliver/ep1_animatic.mp4.
"""
import json, math, pathlib, subprocess, tempfile, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
EP = ROOT / "business_units/deparadigm-media/ap-stats/production/S01E01"
PANELS = EP / "02-storyboards"
VO_MAN = EP / "06-audio" / "vo" / "vo_manifest.json"
OUT = EP / "09-deliver" / "ep1_animatic.mp4"
BROLL = ROOT / "03_ASSETS/animation_pilots/media/videos/manim_meanmedian/720p30/MeanVsMedian.mp4"
W, H, FPS = 1920, 1080, 24


def ken_burns(panel, vo, dur, seg, idx):
    frames = max(1, math.ceil(dur * FPS))
    zin = idx % 2 == 0  # alternate zoom-in / zoom-out for variety
    z = ("min(zoom+0.0012,1.18)" if zin else "if(eq(on,0),1.18,max(zoom-0.0012,1.0))")
    vf = (f"[0:v]scale=2304:1536,zoompan=z='{z}':d={frames}:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},format=yuv420p[v]")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-loop", "1", "-i", str(panel), "-i", str(vo), "-t", f"{dur}",
                    "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
                    "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(seg)], check=True, capture_output=True)


def broll_seg(vo, dur, seg, start=0.0):
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS},setpts=PTS-STARTPTS,format=yuv420p[v]")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-stream_loop", "-1", "-ss", f"{start}", "-i", str(BROLL),
                    "-i", str(vo), "-t", f"{dur}", "-filter_complex", vf,
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(seg)], check=True, capture_output=True)


def main():
    man = json.loads(VO_MAN.read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        segs = []
        broll_start = {"BROLL1": 0.0, "BROLL2": 5.0}
        for i, m in enumerate(man):
            seg = tmp / f"seg_{i:02d}.mp4"
            cue, vo, dur = m["cue"], pathlib.Path(m["file"]), m["dur"]
            if cue.startswith("BROLL"):
                broll_seg(vo, dur, seg, broll_start.get(cue, 0.0))
            else:
                panel = PANELS / f"{cue}.png"
                if not panel.exists():
                    print(f"  WARN missing panel {panel.name}; skipping segment"); continue
                ken_burns(panel, vo, dur, seg, i)
            segs.append(seg)
            print(f"  seg {i:02d} {cue} ({dur}s)")
        if not segs:
            print("no segments"); return 1

        cl = tmp / "list.txt"; cl.write_text("\n".join(f"file '{s}'" for s in segs))
        joined = tmp / "joined.mp4"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
                        "-safe", "0", "-i", str(cl), "-c", "copy", str(joined)], check=True, capture_output=True)

        # total duration → music bed
        total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                      "-of", "csv=p=0", str(joined)], capture_output=True, text=True).stdout.strip())
        music = tmp / "music.wav"
        try:
            import logic_pro_scorer as M
            M.synthesize_music_bed(["calm", "academic"], total, music)
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-i", str(joined), "-i", str(music), "-filter_complex",
                            "[1:a]volume=0.11[m];[0:a][m]amix=inputs=2:duration=first[a]",
                            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                            "-b:a", "192k", "-shortest", str(OUT)], check=True, capture_output=True)
        except Exception as e:
            print("music skipped:", e)
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-i", str(joined), "-c", "copy", str(OUT)], check=True, capture_output=True)

    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(OUT)], capture_output=True, text=True).stdout.strip()
    print(f"EP1_ANIMATIC_DONE {OUT}  ({d}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
