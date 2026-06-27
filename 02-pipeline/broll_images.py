#!/usr/bin/env python3
"""Topical B-ROLL images for the content engine.

Curiosity shorts need to SHOW the subject, not just narrate it over an avatar. Given a search
term this fetches a relevant image (Openverse CC API → Wikimedia Commons fallback) and builds a
vertical Ken-Burns clip — blurred fill background + sharp centered subject + slow push — synced
to a voice-over. Network-optional: if a fetch fails the caller keeps the avatar shot.

  fetch_image(query, out_path) -> path | None
  image_clip(img, dur, out, vo, W, H, motion) -> writes a vertical clip
"""
import hashlib, json, os, subprocess, time, urllib.parse, urllib.request

UA = "AI-PRODUCER-ContentEngine/1.0 (local; research)"

# B-roll source: "comfyui" (local gen, always on-topic), "stock" (Openverse/Wikimedia), or
# "auto" (try ComfyUI, fall back to stock). Env override: BROLL_BACKEND.
BACKEND = os.environ.get("BROLL_BACKEND", "auto")
COMFY = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
COMFY_CKPT = os.environ.get("COMFYUI_CKPT", "dreamshaper_8.safetensors")  # SD1.5: fast, photoreal-ish

def _ff(args):
    return subprocess.run(["ffmpeg", "-nostdin", "-y", *args], capture_output=True, text=True)

def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _openverse(query):
    # category=photograph excludes digitized book pages / diagrams; gather several candidates
    q = urllib.parse.urlencode({"q": query, "page_size": 12, "license_type": "all-cc",
                                "category": "photograph", "size": "large", "mature": "false"})
    try:
        data = json.loads(_get(f"https://api.openverse.org/v1/images/?{q}"))
        return [r.get("url") for r in data.get("results", []) if r.get("url")]
    except Exception:
        return []

def _wikimedia(query):
    try:
        s = urllib.parse.urlencode({"action": "query", "format": "json", "generator": "search",
                                    "gsrsearch": query + " filetype:bitmap", "gsrnamespace": 6,
                                    "gsrlimit": 12, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 1280})
        data = json.loads(_get(f"https://commons.wikimedia.org/w/api.php?{s}"))
        out = []
        for p in (data.get("query", {}).get("pages", {}) or {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            u = ii.get("thumburl") or ii.get("url")
            if u and u.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp"):
                out.append(u)
        return out
    except Exception:
        return []

def _quality_ok(im):
    """Reject document scans / near-black / blown-out images: needs reasonable brightness AND color."""
    if min(im.size) < 360:
        return False
    small = im.resize((64, 64))
    px = list(small.getdata())
    n = len(px)
    luma = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in px) / n
    if not (45 <= luma <= 232):                       # too dark (book spine) or blown white
        return False
    sat = sum(max(r, g, b) - min(r, g, b) for r, g, b in px) / n
    return sat >= 16                                  # near-grayscale → likely a document/diagram scan

def _comfy_up():
    try:
        urllib.request.urlopen(urllib.request.Request(COMFY + "/system_stats"), timeout=4).read()
        return True
    except Exception:
        return False

# Abstract/microscopic subjects: artistic SD models default to a creepy human face. Frame them as
# microscopy and hard-negative people out.
SCIENCE = {"bacteria", "bacterial", "cell", "cells", "microbe", "microbes", "microbiome", "virus",
           "viruses", "molecule", "molecules", "atom", "atoms", "dna", "gene", "genes", "germ",
           "germs", "organism", "protein", "enzyme", "particle", "isotope", "radiation", "neuron",
           "plasma", "fungus", "mold", "spore"}

def _comfy_graph(prompt, seed, w=512, h=768):
    low = prompt.lower()
    is_science = any(w_ in SCIENCE for w_ in low.replace(",", " ").split())
    if is_science:
        pos = (f"{prompt}, microscope photography, scientific macro photo, extreme close-up, "
               f"petri dish, vivid colors, high detail, sharp focus")
    else:
        pos = f"{prompt}, professional photograph, photorealistic, high detail, sharp focus, natural lighting"
    neg = ("person, face, human, portrait, people, man, woman, body, skin, hands, eyes, text, "
           "watermark, caption, letters, illustration, drawing, cartoon, blurry, low quality, "
           "deformed, frame, border, signature")
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": COMFY_CKPT}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": pos}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": neg}},
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 22, "cfg": 6.5,
              "sampler_name": "euler", "scheduler": "karras", "denoise": 1.0,
              "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "broll"}},
    }

def generate_comfyui(query, out_path, timeout=150):
    """Generate a topical image locally via ComfyUI (always on-topic). Returns path or None."""
    if not _comfy_up():
        return None
    try:
        seed = int(hashlib.md5(query.encode()).hexdigest(), 16) % (2 ** 31)
        body = json.dumps({"prompt": _comfy_graph(query, seed)}).encode()
        req = urllib.request.Request(COMFY + "/prompt", data=body,
                                     headers={"Content-Type": "application/json"})
        pid = json.loads(urllib.request.urlopen(req, timeout=15).read())["prompt_id"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(1.5)
            h = json.loads(_get(f"{COMFY}/history/{pid}", timeout=10) or b"{}")
            if pid in h:
                outs = h[pid].get("outputs", {})
                imgs = (outs.get("9", {}) or {}).get("images", [])
                if imgs:
                    im = imgs[0]
                    q = urllib.parse.urlencode({"filename": im["filename"],
                                                "subfolder": im.get("subfolder", ""), "type": im.get("type", "output")})
                    raw = _get(f"{COMFY}/view?{q}", timeout=20)
                    from PIL import Image
                    tmp = out_path + ".gen"
                    open(tmp, "wb").write(raw)
                    Image.open(tmp).convert("RGB").save(out_path, "JPEG", quality=92)
                    os.remove(tmp)
                    return out_path
                return None      # finished with no image
    except Exception:
        return None
    return None

def fetch_image(query, out_path):
    """Best topical image for `query`. ComfyUI local-gen (on-topic) → stock fallback, per BACKEND."""
    if BACKEND in ("comfyui", "auto"):
        p = generate_comfyui(query, out_path)
        if p:
            return p
        if BACKEND == "comfyui":
            return None                      # explicit local-only: don't fall back to stock
    return _fetch_stock(query, out_path)

def _fetch_stock(query, out_path):
    """Download the first GOOD topical image for `query` (photos only, not dark/grayscale scans)."""
    from PIL import Image
    seen = set()
    for url in (_openverse(query) + _wikimedia(query)):
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            tmp = out_path + ".dl"
            with open(tmp, "wb") as f:
                f.write(_get(url, timeout=15))
            im = Image.open(tmp).convert("RGB")
            if _quality_ok(im):
                im.save(out_path, "JPEG", quality=92); os.remove(tmp)
                return out_path
            os.remove(tmp)
        except Exception:
            continue
    return None

def _vertical_still(img, out, W, H):
    """Blurred-fill background + sharp centered subject → a full-bleed vertical still."""
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=24:2,eq=brightness=-0.06[bg];"
          f"[0:v]scale={W}:-1:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    r = _ff(["-i", img, "-filter_complex", fc, "-frames:v", "1", out])
    return os.path.exists(out)

def image_clip(img, dur, out, vo=None, W=1080, H=1920, motion=0):
    """Vertical Ken-Burns clip from a still image, synced to `vo` (or silent for `dur`)."""
    base = os.path.splitext(out)[0] + "_base.png"
    if not _vertical_still(img, base, W, H):
        return False
    sw = int(W * 1.2) // 2 * 2; sh = int(H * 1.2) // 2 * 2
    z = "min(1.0+0.0011*on,1.10)" if motion % 2 == 0 else "max(1.10-0.0011*on,1.0)"
    kb = (f"scale={sw}:{sh},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          f"d=1:s={W}x{H}:fps=24,setsar=1,fade=t=in:d=0.4")   # setsar=1: concat needs uniform SAR
    inp = ["-loop", "1", "-t", str(dur), "-i", base]
    if vo and vo != "null":
        inp += ["-i", vo]
        a = ["-map", "1:a", "-af", "apad", "-c:a", "aac", "-ar", "48000", "-ac", "2"]
    else:
        inp += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo"]
        a = ["-map", "1:a", "-c:a", "aac", "-ar", "48000", "-ac", "2"]
    r = _ff([*inp, "-vf", kb, "-map", "0:v", *a, "-pix_fmt", "yuv420p", "-r", "24",
             "-crf", "18", "-shortest", out])
    try: os.remove(base)
    except Exception: pass
    return os.path.exists(out)

if __name__ == "__main__":
    import sys
    p = fetch_image(sys.argv[1], "/tmp/broll_test.jpg")
    print("image:", p)
    if p and len(sys.argv) > 2:
        ok = image_clip(p, 3.0, sys.argv[2], W=1080, H=1920)
        print("clip:", ok, sys.argv[2])
