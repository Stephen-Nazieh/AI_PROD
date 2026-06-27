#!/usr/bin/env python3
"""SIGNIFICANT — PRODUCE: screenplay + show bible -> finished scene/episode video.

Pipeline:  parse screenplay -> plan coverage -> Kokoro VO -> render shots (generic engine)
           -> render B-rolls (manim) -> assemble (cut + music) -> stitch.

Usage:
  env/bin/python3 02-pipeline/produce.py --script <screenplay.md> [--scene "<heading substr>"] [--out <dir>]
  (no --scene = produce every mapped scene and stitch the episode)
"""
import argparse, json, os, re, subprocess, sys, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "01-scripts"))
from bl_anim_lib import emotion_from_paren   # pure-python (no bpy at import)
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
ENGINE = os.path.join(ROOT, "01-scripts/bl_scene_engine.py")
AUDDIR = os.path.join(ROOT, "06_SHARED_ASSETS/ai-models/kokoro")
PY = sys.executable
FPS = 24

# ── platform integration: business-unit run folders + production ledger ──────
def resolve_run(company, unit, run):
    """Resolve business_units/<company>/<unit>/production/<run>/ (validated against the
    registry) and return the canonical-tree paths. Returns None if not a BU run."""
    if not (company and unit and run):
        return None
    base = os.path.join(ROOT, "business_units", company, unit, "production", run)
    d = {
        "base": base,
        "script": os.path.join(base, "01-scripts", "screenplay.md"),
        "audio": os.path.join(base, "06-audio", "dialogue"),
        "work": os.path.join(base, "07-editing"),
        "srt": os.path.join(base, "08-subtitles"),
        "masters": os.path.join(base, "09-deliver", "masters"),
    }
    for k in ("audio", "work", "srt", "masters"):
        os.makedirs(d[k], exist_ok=True)
    return d

def ledger_log(company, unit, run, episode_path, n_scenes, seconds):
    """Best-effort write to the Postgres production ledger (:5432). No-op if unavailable."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "01_SKILLS"))
        from solocorn_media_bridge import production_db_params
        import psycopg2
        conn = psycopg2.connect(**production_db_params()); conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS production_tracks(
            id SERIAL PRIMARY KEY, slug TEXT, company TEXT, unit TEXT, mode TEXT,
            scenes INT, seconds REAL, output TEXT, created_at TIMESTAMP DEFAULT now())""")
        cur.execute("""INSERT INTO production_tracks(slug,company,unit,mode,scenes,seconds,output)
                       VALUES(%s,%s,%s,'3d',%s,%s,%s)""",
                    (run, company, unit, n_scenes, round(seconds, 1), episode_path))
        conn.close()
        print(f"  ledger: logged run '{run}' ({n_scenes} scenes, {seconds:.0f}s) to :5432")
        return True
    except Exception as e:
        print(f"  ledger: skipped ({str(e)[:60]})"); return False

# ───────────────────────── screenplay parser ─────────────────────────
def parse(path, char_names):
    scenes, cur = [], None
    lines = open(path).read().splitlines()
    i = 0
    namekeys = sorted(char_names, key=len, reverse=True)
    def is_cue(s):
        t = re.sub(r"\s*\(.*?\)\s*$", "", s.strip())          # drop (CONT'D)/(O.S.)
        for nm in namekeys:
            if t.upper() == nm.upper():
                return nm
        return None
    while i < len(lines):
        ln = lines[i]
        h = ln.strip()
        if h.startswith("###") and ("INT." in h or "EXT." in h):
            head = h.lstrip("#").strip()
            cur = {"heading": head, "beats": []}
            scenes.append(cur); i += 1; continue
        if cur is not None:
            mb = re.search(r"B-?ROLL\s*#?(\d+)", h, re.I)
            if mb:
                cur["beats"].append({"type": "broll", "id": mb.group(1)}); i += 1; continue
            cue = is_cue(h)
            if cue:
                i += 1
                paren = ""
                if i < len(lines) and lines[i].strip().startswith("("):
                    paren = lines[i].strip(); i += 1
                txt = []
                while i < len(lines) and lines[i].strip() and not lines[i].startswith("###") \
                        and not is_cue(lines[i]) and not lines[i].strip().startswith(">"):
                    txt.append(lines[i].strip()); i += 1
                body = " ".join(txt).strip().strip('"')
                if body:
                    cur["beats"].append({"type": "line", "char": cue, "paren": paren, "text": body})
                continue
        i += 1
    return scenes

def loc_key(heading):
    m = re.search(r"(INT\.|EXT\.)\s*(.*)", heading.strip())   # handles "TAG — INT. ...", "COLD OPEN" etc.
    s = m.group(2) if m else heading.strip()
    parts = [p.strip() for p in re.split(r"\s+—\s+|\s+-\s+", s)]
    if len(parts) < 2:
        return None
    return f"{' — '.join(parts[:-1])}|{parts[-1]}"

# ───────────────────────── Kokoro VO ─────────────────────────
_KOK = None
def vo(text, voice, out):
    global _KOK
    if _KOK is None:
        from kokoro_onnx import Kokoro
        _KOK = Kokoro(os.path.join(AUDDIR, "kokoro-v1.0.onnx"), os.path.join(AUDDIR, "voices-v1.0.bin"))
    s, sr = _KOK.create(text, voice=voice, speed=1.0, lang="en-us")
    s = np.asarray(s, np.float32); s = s / (np.abs(s).max() + 1e-9) * 0.95
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(sr)); w.writeframes((s * 32767).astype(np.int16).tobytes())
    with wave.open(out) as w:
        return w.getnframes() / w.getframerate()

# ───────────────────────── coverage planner ─────────────────────────
def plan(scene, bible, present, blocking):
    """present = ordered canonical char names (1 or 2). Returns list of segments."""
    cov, segs = bible["coverage"], []
    npc = len(present)
    if npc >= 2:
        segs.append({"kind": "shot", "cov": "establish2", "spk": None, "silent": 2.2})
    for b in scene["beats"]:
        if b["type"] == "broll":
            segs.append({"kind": "broll", "id": b["id"]})
        elif b["type"] == "line" and b["char"] in present:
            segs.append({"kind": "shot", "cov": "single2" if npc >= 2 else "single1",
                         "spk": b["char"], "text": b["text"], "paren": b.get("paren", "")})
    return segs

def shot_cfg(seg, bible, present, blocking, set_cfg, vo_path):
    cov = dict(bible["coverage"][seg["cov"]])
    chars = []
    for idx, nm in enumerate(present):
        cd = resolve_char(nm, bible)
        bl = blocking[idx]
        chars.append({"name": nm, "vrm": os.path.join(ROOT, cd["vrm"]),
                      "pos": bl["pos"], "rot": bl["rot"], "gesture": cd["gesture"]})
    shot = {"lens": cov["lens"], "fstop": cov["fstop"], "push": cov["push"]}
    if seg["spk"] is None:                                   # establish
        shot["tgt"] = cov.get("tgt", "two"); shot["off"] = cov["off"]; shot["look_dz"] = cov.get("look_dz", 0)
        shot["spk"] = None
    else:
        spk = seg["spk"]; sidx = present.index(spk)
        px = blocking[sidx]["pos"][0]
        off = list(cov["off"])
        if len(present) >= 2:
            off[0] = -1 * (1 if px > 0 else -1) * abs(off[0])   # camera over the OTHER shoulder
        shot["tgt"] = spk; shot["off"] = off; shot["look"] = cov.get("look", 0.82); shot["spk"] = spk
        shot["emotion"] = emotion_from_paren(seg.get("paren", ""))   # acting
    return {"set": set_cfg["set"], "props": set_cfg.get("props", {}), "characters": chars,
            "shot": shot, "vo": vo_path or "null", "res": bible["resolution"], "fps": FPS,
            "silent_sec": seg.get("silent", 2.2)}

def resolve_char(nm, bible):
    c = bible["characters"].get(nm) or bible["characters"].get(nm.upper())
    if c and "alias" in c:
        c = bible["characters"][c["alias"]]
    return c

# ───────────────────────── render + assemble ─────────────────────────
import hashlib

def _frame_black(png):
    """True if a frame is (near) black/empty — a render failure signal."""
    try:
        from PIL import Image, ImageStat
        st = ImageStat.Stat(Image.open(png).convert("L"))
        return st.mean[0] < 3.0
    except Exception:
        return os.path.getsize(png) < 8000   # fallback: tiny PNG ≈ empty

def render_shot(cfg, work, key):
    cfgp = os.path.join(work, f"{key}.json"); outd = os.path.join(work, key)
    os.makedirs(outd, exist_ok=True); cfg["out"] = outd
    cfg_for_hash = {k: v for k, v in cfg.items() if k != "out"}
    h = hashlib.md5(json.dumps(cfg_for_hash, sort_keys=True).encode()).hexdigest()[:12]
    hashf = os.path.join(outd, ".cfghash")
    have = [f for f in os.listdir(outd) if f.endswith(".png")]
    # CACHE: identical config + frames already present -> skip the render
    if have and os.path.exists(hashf) and open(hashf).read().strip() == h:
        return outd, len(have), "cached"
    json.dump(cfg, open(cfgp, "w"))
    status = "rendered"
    for attempt in (1, 2):                                  # QUALITY GATE: 1 retry on failure
        for f in have:
            try: os.remove(os.path.join(outd, f))
            except Exception: pass
        subprocess.run([BLENDER, "-b", "--python", ENGINE, "--", cfgp], cwd=ROOT, capture_output=True, text=True)
        have = sorted(f for f in os.listdir(outd) if f.endswith(".png"))
        mid = have[len(have) // 2] if have else None
        if have and mid and not _frame_black(os.path.join(outd, mid)):
            break
        status = f"RETRY{attempt}" if attempt == 1 else "FAILED(black/empty)"
    if have and not status.startswith("FAILED"):    # only cache a genuine success — never poison
        open(hashf, "w").write(h)
    return outd, len(have), status

def render_broll(bid, bible, work):
    b = bible["brolls"][bid]; mediadir = os.path.join(work, "manim")
    subprocess.run([os.path.join(ROOT, "env/bin/manim"), "-qh", "--fps", str(FPS),
                    "-r", f"{bible['resolution'][0]},{bible['resolution'][1]}",
                    "--media_dir", mediadir, os.path.join(ROOT, b["file"]), b["scene"]],
                   cwd=ROOT, capture_output=True, text=True)
    mp4 = os.path.join(mediadir, "videos", os.path.splitext(os.path.basename(b["file"]))[0],
                       "1080p24", b["scene"] + ".mp4")
    return mp4, b.get("trim", 9.0)

def ff(args):
    subprocess.run(["ffmpeg", "-nostdin", "-y", *args], capture_output=True, text=True)

def _shot_dims(frames):
    f0 = os.path.join(frames, "f_0001.png")
    try:
        from PIL import Image
        return Image.open(f0).size
    except Exception:
        return 1080, 1920

def clip_from_frames(frames, n, vo_path, out, fade_in=False, motion=None):
    base = ["-framerate", "24", "-i", os.path.join(frames, "f_%04d.png")]
    if vo_path and vo_path != "null":
        base += ["-i", vo_path, "-af", "apad"]
    else:
        base += ["-f", "lavfi", "-t", "12", "-i", "anullsrc=r=48000:cl=stereo"]
    chain = []
    if motion is not None:                       # subtle punch-in, alternating direction per shot
        W, H = _shot_dims(frames); sw = int(W * 1.2) // 2 * 2; sh = int(H * 1.2) // 2 * 2
        z = "min(1.0+0.0011*on,1.10)" if motion % 2 == 0 else "max(1.10-0.0011*on,1.0)"
        chain.append(f"scale={sw}:{sh},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':"
                     f"y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps=24")
    if fade_in: chain.append("fade=t=in:d=0.6")
    chain.append("setsar=1")                      # uniform SAR so clips concat with image B-roll
    vf = ["-vf", ",".join(chain)]
    ff([*base, *vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", "-crf", "18",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", out])

def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nk=1:nw=1", p], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except Exception: return 0.0

def assemble(clips, music_bed, out):
    inp, fc = [], ""
    for i, c in enumerate(clips):
        inp += ["-i", c]; fc += f"[{i}:v][{i}:a]"
    fc += f"concat=n={len(clips)}:v=1:a=1[v][a]"
    comb = out + ".comb.mp4"
    ff([*inp, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-r", "24", "-crf", "18", "-c:a", "aac", "-ar", "48000", "-ac", "2", comb])
    if not os.path.exists(comb) or os.path.getsize(comb) < 2000:   # concat failed (e.g. SAR mismatch → 0-byte)
        raise RuntimeError(f"assemble: concat produced no/empty output from {len(clips)} clips → {out}")
    if music_bed and os.path.exists(music_bed):
        D = dur(comb); fo = max(0.1, D - 1.3)
        ff(["-i", comb, "-stream_loop", "-1", "-i", music_bed, "-filter_complex",
            f"[0:a]asplit=2[v1][v2];[1:a]atrim=0:{D},volume=0.45,afade=t=out:st={fo}:d=1.3[m];"
            f"[m][v1]sidechaincompress=threshold=0.04:ratio=7:attack=14:release=320[md];"
            f"[v2][md]amix=inputs=2:normalize=0:duration=first[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2", out])
        if os.path.exists(out) and os.path.getsize(out) > 2000:    # music mix OK → drop comb
            os.remove(comb)
        else:                                                      # music mix failed → keep silent concat
            os.replace(comb, out)
    else:
        os.replace(comb, out)

# ───────────────────────── graphic beats (title / seed / tag) ─────────────────────────
def _font(p, s):
    from PIL import ImageFont
    try: return ImageFont.truetype(p, s)
    except Exception: return ImageFont.load_default()

def make_title(show, sub, out_png, W=1920, H=1080):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), (8, 9, 12)); d = ImageDraw.Draw(img)
    t = show.upper(); ls = max(8, W // 110)
    size = int(H * 0.13); w = []                       # auto-fit the title to the frame width
    while size > 20:
        big = _font("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", size)
        w = [d.textbbox((0, 0), c, font=big)[2] for c in t]
        if sum(w) + ls * (len(t) - 1) <= W * 0.86: break
        size -= 6
    sm = _font("/System/Library/Fonts/Supplemental/Georgia.ttf", max(20, size // 4))
    x = (W - (sum(w) + ls * (len(t) - 1))) // 2; y = H // 2 - size
    for c, cw in zip(t, w): d.text((x, y), c, font=big, fill=(238, 240, 245)); x += cw + ls
    yb = y + int(size * 1.4)
    d.rectangle([(W // 2 - 160, yb), (W // 2 + 160, yb + 3)], fill=(120, 140, 180))
    tb = d.textbbox((0, 0), sub, font=sm); d.text(((W - tb[2]) // 2, yb + 25), sub, font=sm, fill=(150, 165, 195))
    img.save(out_png)

def img_clip(png, dur, out, vo=None, music=None, fade_in=True, fade_out=False, kenburns=False):
    args = ["-loop", "1", "-t", str(dur), "-i", png]
    if vo: args += ["-i", vo]
    if music: args += ["-stream_loop", "-1", "-i", music]
    vf = []
    if kenburns:
        vf.append(f"scale=3000:-1,zoompan=z='min(1.0+0.0009*on,1.14)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=24")
    if fade_in: vf.append("fade=t=in:d=0.6")
    if fade_out: vf.append(f"fade=t=out:st={max(0.1,dur-0.8)}:d=0.8")
    fc = f"[0:v]{','.join(vf) if vf else 'null'}[v];"
    ai = 1
    amix = []
    if vo: fc += f"[{ai}:a]adelay=250|250,apad[vo];"; amix.append("[vo]"); ai += 1
    if music: fc += f"[{ai}:a]atrim=0:{dur},volume=0.4,afade=t=out:st={max(0.1,dur-1.0)}:d=1.0[m];"; amix.append("[m]")
    if amix:
        fc += f"{''.join(amix)}amix=inputs={len(amix)}:normalize=0:duration=first[a]"
    else:
        fc = f"[0:v]{','.join(vf) if vf else 'null'}[v]"
    cmd = [*args, "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo"]
    if amix:
        ff([*cmd, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-r", "24", "-crf", "18", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-t", str(dur), out])
    else:
        sidx = ai
        ff([*cmd, "-filter_complex", fc, "-map", "[v]", "-map", f"{sidx}:a", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-r", "24", "-crf", "18", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-t", str(dur), out])

def srt_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int((s%1)*1000):03d}"

def write_srt(caps, out):
    lines = []
    for i, (t0, t1, txt, who) in enumerate(caps, 1):
        lines.append(f"{i}\n{srt_time(t0)} --> {srt_time(t1)}\n{who}: {txt}\n")
    open(out, "w").write("\n".join(lines))

MUSICDIR = os.path.join(ROOT, "06_SHARED_ASSETS/music-beds")   # shared, purge-proof bed library

# ───────────────────────── main ─────────────────────────
def produce_scene(scene, bible, work, audpath):
    """Returns (scene_mp4 | None, caps). caps = [(start, end, text, who)] in scene time."""
    lk = loc_key(scene["heading"])
    set_cfg = bible["locations"].get(lk)
    if not set_cfg:
        print(f"  SKIP (no set mapped for '{lk}')"); return None, []
    # ----- GRAPHIC beat (title/season-seed/tag) -----
    if "graphic" in set_cfg:
        g = set_cfg["graphic"]; img = os.path.join(ROOT, g["image"])
        vp = None
        if g.get("vo_from_beat"):
            line = next((b for b in scene["beats"] if b["type"] == "line"), None)
            if line:
                cd = resolve_char(line["char"], bible)
                vp = os.path.join(audpath, "g_vo.wav"); vo(line["text"], cd["voice"], vp)
        music = os.path.join(MUSICDIR, set_cfg["music"] + ".wav") if set_cfg.get("music") else None
        out = os.path.join(work, "SCENE.mp4")
        img_clip(img, g.get("dur", 5.0), out, vo=vp, music=music,
                 fade_in=True, fade_out=g.get("fade_out", False), kenburns=g.get("kenburns", False))
        print(f"  [graphic] {os.path.basename(img)} dur={g.get('dur', 5.0)}")
        return out, []
    # ----- DIALOGUE scene -----
    present, seen = [], set()
    for b in scene["beats"]:
        if b["type"] == "line" and b["char"] not in seen:
            cn = b["char"] if b["char"] in bible["characters"] else b["char"].upper()
            present.append(cn); seen.add(b["char"])
    present = present[:2]
    if not present:
        print("  SKIP (no dialogue)"); return None, []
    blocking = bible["blocking"]["2" if len(present) >= 2 else "1"]
    segs = plan(scene, bible, present, blocking)
    fmt = bible.get("format"); visuals = bible.get("visuals", []); RES = bible.get("resolution", [1920, 1080])
    subj = (bible.get("subject") or "").strip()        # anchor weak B-roll queries on the core subject
    clips, caps, t, spoken_i = [], [], 0.0, -1
    for si, seg in enumerate(segs):
        key = f"s{si:02d}"
        if seg["kind"] == "broll":
            if seg["id"] not in bible.get("brolls", {}):
                print(f"  [skip broll #{seg['id']} — no Manim module registered]"); continue
            mp4, trim = render_broll(seg["id"], bible, work)
            if not os.path.exists(mp4):
                print(f"  broll {seg['id']} FAILED"); continue
            clip = os.path.join(work, key + ".mp4")
            ff(["-i", mp4, "-t", str(trim), "-f", "lavfi", "-t", str(trim),
                "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", "-crf", "18",
                "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", clip])
            clips.append(clip); print(f"  [{key}] broll #{seg['id']}")
        else:
            vp, vdur = None, 0.0
            if seg["spk"]:
                spoken_i += 1
                cd = resolve_char(seg["spk"], bible)
                vp = os.path.join(audpath, f"{key}_{seg['spk']}.wav")
                vdur = vo(seg["text"], cd["voice"], vp)
            clip = os.path.join(work, key + ".mp4")
            # SOCIAL B-ROLL: show the subject on alternating lines (keep the hook on the presenter)
            q = visuals[spoken_i] if 0 <= spoken_i < len(visuals) else ""
            if subj and (not q or subj.lower() not in q.lower()):   # keep the query on-topic
                q = (subj + " " + q).strip()
            use_img = (fmt == "social" and seg.get("spk") and spoken_i >= 1
                       and spoken_i % 2 == 1 and bool(q))
            if use_img:
                try:
                    import broll_images
                    img = os.path.join(work, key + "_img.jpg")
                    if broll_images.fetch_image(q, img) and \
                       broll_images.image_clip(img, max(2.0, vdur + 0.3), clip, vo=vp,
                                               W=RES[0], H=RES[1], motion=si):
                        clips.append(clip); print(f"  [{key}] B-ROLL image '{q}' ({vdur:.1f}s)")
                    else:
                        use_img = False
                except Exception as e:
                    print(f"  [{key}] broll image failed ({str(e)[:50]}) → avatar"); use_img = False
            if not use_img:
                cfg = shot_cfg(seg, bible, present, blocking, set_cfg, vp)
                frames, n, status = render_shot(cfg, work, key)
                clip_from_frames(frames, n, vp, clip, fade_in=(si == 0), motion=si)
                clips.append(clip)
                emo = (cfg["shot"].get("emotion") or "-")
                print(f"  [{key}] {seg['cov']:11s} spk={seg['spk']} emo={emo:9s} frames={n} ({status})")
        d = dur(clips[-1])
        if seg["kind"] == "shot" and seg.get("spk") and seg.get("text"):
            cap_txt = re.sub(r"[*_`]+", "", seg["text"]).strip()   # clean markdown for captions
            caps.append((t + 0.15, t + d, cap_txt, seg["spk"]))
        t += d
    if not clips:
        return None, []
    music = os.path.join(MUSICDIR, set_cfg["music"] + ".wav") if set_cfg.get("music") else None
    out = os.path.join(work, "SCENE.mp4")
    assemble(clips, music if (music and os.path.exists(music)) else None, out)
    return out, caps

def main():
    import time as _time
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default=None, help="screenplay path (or resolved from the BU run)")
    ap.add_argument("--bible", default=os.path.join(ROOT, "02-pipeline/show_bible.json"))
    ap.add_argument("--scene", default=None, help="produce only scenes whose heading contains this")
    ap.add_argument("--out", default=os.path.join(ROOT, "03_ASSETS/pipeline_out"))
    ap.add_argument("--episode", default="EPISODE", help="output basename for the stitched episode")
    ap.add_argument("--company", default=None); ap.add_argument("--unit", default=None)
    ap.add_argument("--run", default=None, help="business-unit run slug (with --company/--unit)")
    a = ap.parse_args()

    rd = resolve_run(a.company, a.unit, a.run)   # platform mode → canonical production tree
    if rd:
        script = a.script or rd["script"]
        work_root, aud_root, masters, srt_dir = rd["work"], rd["audio"], rd["masters"], rd["srt"]
        if a.episode == "EPISODE": a.episode = a.run
        print(f"[platform] run home: {rd['base']}")
    else:
        if not a.script:
            ap.error("--script required (or pass --company/--unit/--run for a business-unit run)")
        script = a.script
        os.makedirs(a.out, exist_ok=True)
        work_root = aud_root = masters = srt_dir = a.out

    t0_all = _time.time()
    bible = json.load(open(a.bible))
    scenes = parse(script, list(bible["characters"].keys()))
    print(f"parsed {len(scenes)} scenes  → masters: {masters}")
    full = a.scene is None
    ep_clips, ep_caps, t_off = [], [], 0.0
    RES = bible.get("resolution", [1920, 1080])              # match title aspect to the episode
    # social/shorts open DIRECTLY on content (a title-card intro kills retention); the finisher
    # adds a hook over the first shot instead. Longer formats keep the title card.
    if full and bible.get("format") != "social":             # title card opens the episode
        tpng = os.path.join(work_root, "_title.png")
        make_title(bible["show"], bible.get("tagline", "A SERIES").upper(), tpng, W=RES[0], H=RES[1])
        tclip = os.path.join(work_root, "_title.mp4")
        img_clip(tpng, 2.6, tclip, fade_in=True, fade_out=True)
        ep_clips.append(tclip); t_off += dur(tclip)
    outputs = []
    for idx, scene in enumerate(scenes):
        if a.scene and a.scene.lower() not in scene["heading"].lower():
            continue
        print(f"[{idx:02d}] {scene['heading']}")
        work = os.path.join(work_root, f"scene_{idx:02d}"); os.makedirs(work, exist_ok=True)
        audp = os.path.join(aud_root, f"scene_{idx:02d}"); os.makedirs(audp, exist_ok=True)
        res, caps = produce_scene(scene, bible, work, audp)
        if res:
            final = os.path.join(masters, f"scene_{idx:02d}.mp4"); os.replace(res, final)
            outputs.append(final); print(f"  -> {final}")
            if full:
                ep_clips.append(final)
                for (t0, t1, txt, who) in caps:
                    ep_caps.append((t_off + t0, t_off + t1, txt, who))
                t_off += dur(final)
    print(f"DONE: {len(outputs)} scenes produced")
    if full and ep_clips:                                    # stitch episode + captions
        ep = os.path.join(masters, f"{a.episode}.mp4")
        assemble(ep_clips, None, ep)
        write_srt(ep_caps, os.path.join(srt_dir, f"{a.episode}.srt"))
        secs = dur(ep)
        print(f"EPISODE: {ep}  ({secs:.1f}s)  + {a.episode}.srt ({len(ep_caps)} captions)")
        if rd:
            ledger_log(a.company, a.unit, a.run, ep, len(outputs), secs)

if __name__ == "__main__":
    main()
