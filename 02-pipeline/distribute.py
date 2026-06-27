#!/usr/bin/env python3
"""SIGNIFICANT — DISTRIBUTE (reach). Turn a finished 16:9 episode into platform deliverables:
  - 9:16 vertical (Shorts/TikTok/Reels) with a blurred-fill background
  - a thumbnail (hero frame + title bar)
  - optional burned-in captions from the .srt

Usage:
  env/bin/python3 02-pipeline/distribute.py <episode.mp4> [--srt X.srt] [--title "..."] [--out DIR]
"""
import argparse, os, subprocess, sys

def ff(args):
    return subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)

def has_filter(name):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return name in r.stdout

def vertical(src, out):
    """16:9 -> 1080x1920: blurred zoomed bg + the fit clip centered."""
    ff(["-i", src, "-filter_complex",
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24[bgb];"
        "[fg]scale=1080:-2[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[v]",
        "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "20", "-c:a", "aac", "-ar", "48000", "-ac", "2", out])

def thumbnail(src, out, title, t=2.0):
    frame = out + ".frame.png"
    ff(["-ss", str(t), "-i", src, "-vframes", "1", frame])
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        im = Image.open(frame).convert("RGB").resize((1280, 720))
        # darken bottom third for the title bar
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        d.rectangle([(0, 540), (1280, 720)], fill=(8, 9, 12, 200))
        im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
        d = ImageDraw.Draw(im)
        try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 64)
        except Exception: f = ImageFont.load_default()
        d.text((48, 576), title, font=f, fill=(238, 240, 245))
        d.rectangle([(48, 556), (260, 562)], fill=(120, 140, 180))
        im.save(out)
    finally:
        if os.path.exists(frame): os.remove(frame)

def burn_captions(src, srt, out):
    if not has_filter("subtitles"):
        print("  (subtitles filter unavailable — keeping sidecar .srt only)"); return False
    style = "FontName=Georgia,FontSize=15,PrimaryColour=&H00F5F0E9,OutlineColour=&H00101010,BorderStyle=1,Outline=2,Shadow=0,MarginV=40"
    ff(["-i", src, "-vf", f"subtitles={srt}:force_style='{style}'", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "copy", out])
    return os.path.exists(out)

def main():
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default=None)
    ap.add_argument("--srt", default=None)
    ap.add_argument("--title", default="SIGNIFICANT")
    ap.add_argument("--out", default=None)
    ap.add_argument("--company", default=None); ap.add_argument("--unit", default=None)
    ap.add_argument("--run", default=None, help="business-unit run (resolves episode + out tree)")
    a = ap.parse_args()
    # platform mode: resolve episode + deliverable folders from the business-unit run
    if a.company and a.unit and a.run:
        base = os.path.join(ROOT, "business_units", a.company, a.unit, "production", a.run)
        a.src = a.src or os.path.join(base, "09-deliver", "masters", a.run + ".mp4")
        a.srt = a.srt or os.path.join(base, "08-subtitles", a.run + ".srt")
        a.out = a.out or os.path.join(base, "09-deliver", "web")
    if not a.src or not os.path.exists(a.src):
        ap.error(f"episode not found: {a.src}")
    out = a.out or os.path.dirname(os.path.abspath(a.src))
    os.makedirs(out, exist_ok=True)
    name = os.path.splitext(os.path.basename(a.src))[0]
    print("DISTRIBUTE", a.src)
    # only make a 9:16 reframe if the source is widescreen; social is already vertical
    dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                           "-show_entries", "stream=width,height", "-of", "csv=p=0", a.src],
                          capture_output=True, text=True).stdout.strip().split(",")
    w, h = (int(dims[0]), int(dims[1])) if len(dims) == 2 else (1920, 1080)
    if w > h:
        v = os.path.join(out, name + "_vertical.mp4"); vertical(a.src, v); print("  vertical ->", v)
    else:
        print("  (already vertical — no reframe)")
    thumbs = os.path.join(os.path.dirname(out), "thumbnails") if a.run else out
    os.makedirs(thumbs, exist_ok=True)
    th = os.path.join(thumbs, name + "_thumb.jpg"); thumbnail(a.src, th, a.title); print("  thumbnail ->", th)
    if a.srt and os.path.exists(a.srt):
        b = os.path.join(out, name + "_captioned.mp4")
        if burn_captions(a.src, a.srt, b): print("  captioned ->", b)

if __name__ == "__main__":
    main()
