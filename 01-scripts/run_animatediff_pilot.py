#!/usr/bin/env python3
"""AnimateDiff pilot — generate one short animated clip via the ComfyUI API so the
real AI-animation quality can be judged against the Manim pilot.

DreamShaper-8 (SD1.5) + mm_sd_v15_v2 motion module → 16 frames → mp4.
"""
import json, time, urllib.request, subprocess, pathlib, sys

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "ComfyUI" / "output"
DEST = ROOT / "03_ASSETS" / "animation_pilots" / "animatediff_pilot.mp4"
PREFIX = "ad_pilot"

POS = ("masterpiece, best quality, anime style, a friendly young teacher character "
       "gesturing while explaining at a chalkboard, classroom, expressive, smooth motion")
NEG = "blurry, low quality, lowres, static, watermark, text, deformed, extra limbs"

WORKFLOW = {
    "1": {"class_type": "CheckpointLoaderSimple",
          "inputs": {"ckpt_name": "dreamshaper_8.safetensors"}},
    "2": {"class_type": "ADE_AnimateDiffLoaderGen1",
          "inputs": {"model": ["1", 0], "model_name": "mm_sd_v15_v2.ckpt",
                     "beta_schedule": "sqrt_linear (AnimateDiff)"}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": POS, "clip": ["1", 1]}},
    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
    "5": {"class_type": "EmptyLatentImage",
          "inputs": {"width": 512, "height": 512, "batch_size": 16}},
    "6": {"class_type": "KSampler",
          "inputs": {"model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                     "latent_image": ["5", 0], "seed": 12345, "steps": 20, "cfg": 8.0,
                     "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
    "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
    "8": {"class_type": "SaveImage",
          "inputs": {"images": ["7", 0], "filename_prefix": PREFIX}},
}


def post(path, payload):
    req = urllib.request.Request(f"{COMFY}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def get(path):
    return json.loads(urllib.request.urlopen(f"{COMFY}{path}", timeout=30).read())


def main():
    print("submitting AnimateDiff workflow ...")
    pid = post("/prompt", {"prompt": WORKFLOW})["prompt_id"]
    print("prompt_id:", pid)
    # poll history until the prompt completes
    t0 = time.time()
    outputs = None
    while time.time() - t0 < 1800:
        hist = get(f"/history/{pid}")
        if pid in hist:
            status = hist[pid].get("status", {})
            if status.get("completed") or status.get("status_str") == "success":
                outputs = hist[pid].get("outputs", {})
                break
            if status.get("status_str") == "error":
                print("WORKFLOW ERROR:", json.dumps(hist[pid].get("status"), indent=2)[:800])
                return 1
        time.sleep(5)
    if not outputs:
        print("TIMEOUT or no outputs"); return 1

    # gather saved frames from the SaveImage node
    imgs = outputs.get("8", {}).get("images", [])
    if not imgs:
        print("no images in outputs:", json.dumps(outputs)[:400]); return 1
    frames = []
    for im in imgs:
        p = OUT_DIR / (im.get("subfolder") or "") / im["filename"]
        if p.exists():
            frames.append(p)
    frames.sort()
    print(f"generated {len(frames)} frames")
    if not frames:
        return 1

    # stage gap-free sequence + encode (8fps native; also a 24fps smooth version)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        st = pathlib.Path(td)
        for i, f in enumerate(frames):
            (st / f"f_{i:04d}.png").symlink_to(f.resolve())
        # 8fps base, upscaled to 1024 with smooth minterpolate to 24fps
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-framerate", "8", "-i", str(st / "f_%04d.png"),
                        "-vf", "scale=1024:1024:flags=lanczos,minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc",
                        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                        str(DEST)], check=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(DEST)], capture_output=True, text=True).stdout.strip()
    print(f"PILOT_DONE {DEST}  duration={dur}s  frames={len(frames)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
