#!/usr/bin/env python3
"""CONTENT ENGINE — SOCIAL FINISHER.

Turns a rendered episode into social-ready content: BURNED-IN captions (social is watched
sound-off — the #1 quality lever), a hook text card, and a vertical thumbnail. This ffmpeg
build has no drawtext/subtitles/libass, so text is rendered with PIL and overlaid.

  finish_social(video, srt, out_video, thumb, title) -> writes captioned video + thumbnail
"""
import os, re, subprocess, sys

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

def _ff(args):
    return subprocess.run(["ffmpeg", "-nostdin", "-y", *args], capture_output=True, text=True)

def _dims(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", v], capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split(","); return int(w), int(h)
    except Exception:
        return 1080, 1920

def parse_srt(srt):
    if not srt or not os.path.exists(srt):
        return []
    out, blocks = [], open(srt).read().strip().split("\n\n")
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 2:
            continue
        m = re.search(r"(\d+):(\d+):([\d.,]+)\s*-->\s*(\d+):(\d+):([\d.,]+)", lines[1])
        if not m:
            continue
        def sec(h, mn, s): return int(h) * 3600 + int(mn) * 60 + float(s.replace(",", "."))
        s0 = sec(m.group(1), m.group(2), m.group(3)); s1 = sec(m.group(4), m.group(5), m.group(6))
        txt = " ".join(lines[2:]).strip()
        txt = re.sub(r"^[A-Z][A-Z' .]{0,18}:\s*", "", txt)   # drop "NAME:" speaker prefix
        txt = re.sub(r"[*_`]+", "", txt).strip()             # strip leaked markdown emphasis (**word**)
        if txt:
            out.append((s0, s1, txt))
    return out

def chunk_captions(caps, max_words=4):
    """Split each caption into 3-4 word 'karaoke' phrases, timed proportionally — far easier to
    read sound-off than a full sentence dumped on screen."""
    out = []
    for s, e, txt in caps:
        words = txt.split()
        if len(words) <= max_words:
            out.append((s, e, txt)); continue
        groups = [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]
        span = e - s; t = s
        for g in groups:
            seg = span * len(g.split()) / len(words)
            out.append((round(t, 2), round(min(e, t + seg), 2), g)); t += seg
    return out

def _font(sz):
    from PIL import ImageFont
    try: return ImageFont.truetype(ARIAL, sz)
    except Exception: return ImageFont.load_default()

def _wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textbbox((0, 0), t, font=font)[2] <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def _text_png(text, W, H, out, y_frac, size_frac, color=(255, 255, 255, 255), upper=True):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    fs = int(W * size_frac); font = _font(fs)
    lines = _wrap(d, text.upper() if upper else text, font, int(W * 0.86))
    lh = int(fs * 1.22); y = int(H * y_frac) - (lh * len(lines)) // 2
    stroke = max(3, fs // 11)
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=font); x = (W - (bb[2] - bb[0])) // 2
        d.text((x, y), ln, font=font, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        y += lh
    img.save(out)

def finish_social(video, srt, out_video, thumb=None, title="", hook=""):
    W, H = _dims(video)
    caps = chunk_captions(parse_srt(srt))    # karaoke-style short phrases
    work = os.path.join(os.path.dirname(out_video) or ".", "_cap"); os.makedirs(work, exist_ok=True)
    # caption PNGs (lower third, big bold) + a hook card (upper third, first ~2.4s)
    inputs, fc, cur = ["-i", video], "", "[0:v]"
    idx = 1
    pngs = []
    if hook or title:
        hp = os.path.join(work, "hook.png"); _text_png(hook or title, W, H, hp, 0.20, 0.072, (255, 230, 90, 255))
        pngs.append((hp, 0.0, 2.4)); inputs += ["-i", hp]
    for i, (s, e, t) in enumerate(caps):
        p = os.path.join(work, f"c{i}.png"); _text_png(t, W, H, p, 0.72, 0.068)
        pngs.append((p, s, e)); inputs += ["-i", p]
    for (p, s, e) in pngs:
        nxt = f"[v{idx}]"
        fc += f"{cur}[{idx}:v]overlay=0:0:enable='between(t,{s:.2f},{e:.2f})'{nxt};"
        cur = nxt; idx += 1
    if not pngs:
        _ff(["-i", video, "-c", "copy", out_video])
    else:
        _ff([*inputs, "-filter_complex", fc.rstrip(";"), "-map", cur, "-map", "0:a",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-c:a", "copy", out_video])
    # vertical thumbnail: a strong frame + the title/hook overlaid
    if thumb:
        frame = thumb + ".f.png"
        _ff(["-ss", str(min(3.0, (caps[0][0] if caps else 1.0))), "-i", video, "-vframes", "1", frame])
        try:
            from PIL import Image, ImageDraw
            im = Image.open(frame).convert("RGBA")
            tp = thumb + ".t.png"; _text_png(title or hook, W, H, tp, 0.82, 0.07, (255, 255, 255, 255))
            im.alpha_composite(Image.open(tp)); im.convert("RGB").save(thumb)
            for f in (frame, tp):
                if os.path.exists(f): os.remove(f)
        except Exception:
            pass
    return out_video

if __name__ == "__main__":
    a = sys.argv
    finish_social(a[1], a[2] if len(a) > 2 else None, a[3] if len(a) > 3 else a[1].replace(".mp4", "_social.mp4"),
                  thumb=a[1].replace(".mp4", "_thumb.jpg"), title=(a[4] if len(a) > 4 else ""))
    print("finished:", a[3] if len(a) > 3 else "social")
