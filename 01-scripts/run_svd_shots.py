#!/usr/bin/env python3
"""Animate the Median-Detective key-frame stills into moving cinematic clips via
Stable Video Diffusion (img2vid) in ComfyUI. Each shot PNG → ~25-frame clip → mp4
(6fps base, motion-interpolated to 24fps). Output → .../median_detective/clips/.
"""
import json, time, urllib.request, pathlib, subprocess, tempfile, sys
from PIL import Image

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = ROOT / "03_ASSETS" / "animation_pilots" / "median_detective" / "shots"
CLIPS = ROOT / "03_ASSETS" / "animation_pilots" / "median_detective" / "clips"
COMFY_IN = ROOT / "ComfyUI" / "input"
COMFY_OUT = ROOT / "ComfyUI" / "output"
W, H, FRAMES, FPS = 1024, 576, 25, 6


def stage_init(png: pathlib.Path) -> str:
    """Center-crop to 16:9 and copy into ComfyUI/input for LoadImage."""
    im = Image.open(png).convert("RGB")
    tw, th = W, H
    scale = max(tw / im.width, th / im.height)
    im = im.resize((int(im.width*scale), int(im.height*scale)), Image.Resampling.LANCZOS)
    left = (im.width - tw) // 2; top = (im.height - th) // 2
    im = im.crop((left, top, left+tw, top+th))
    COMFY_IN.mkdir(parents=True, exist_ok=True)
    name = f"svdin_{png.stem}.png"
    im.save(COMFY_IN / name)
    return name


def workflow(init_name, seed):
    return {
        "1": {"class_type": "ImageOnlyCheckpointLoader",
              "inputs": {"ckpt_name": "svd_xt.safetensors"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": init_name}},
        "3": {"class_type": "SVD_img2vid_Conditioning",
              "inputs": {"clip_vision": ["1", 1], "init_image": ["2", 0], "vae": ["1", 2],
                         "width": W, "height": H, "video_frames": FRAMES,
                         "motion_bucket_id": 110, "fps": FPS, "augmentation_level": 0.0}},
        "4": {"class_type": "VideoLinearCFGGuidance", "inputs": {"model": ["1", 0], "min_cfg": 1.0}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["4", 0], "positive": ["3", 0], "negative": ["3", 1],
                         "latent_image": ["3", 2], "seed": seed, "steps": 20, "cfg": 2.5,
                         "sampler_name": "euler", "scheduler": "karras", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "svd"}},
    }


def post(p, d):
    r = urllib.request.Request(f"{COMFY}{p}", data=json.dumps(d).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())


def get(p):
    return json.loads(urllib.request.urlopen(f"{COMFY}{p}", timeout=30).read())


def animate(png, seed):
    init = stage_init(png)
    pid = post("/prompt", {"prompt": workflow(init, seed)})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < 1800:
        h = get(f"/history/{pid}")
        if pid in h and h[pid].get("outputs"):
            imgs = h[pid]["outputs"].get("7", {}).get("images", [])
            if imgs:
                return [COMFY_OUT / (i.get("subfolder") or "") / i["filename"] for i in imgs]
        if pid in h and h[pid].get("status", {}).get("status_str") == "error":
            print("  ERROR", json.dumps(h[pid]["status"])[:300]); return None
        time.sleep(5)
    return None


def encode(frames, dst):
    frames = [f for f in frames if f.exists()]
    if not frames:
        return False
    with tempfile.TemporaryDirectory() as td:
        st = pathlib.Path(td)
        for i, f in enumerate(sorted(frames)):
            (st / f"f_{i:04d}.png").symlink_to(f.resolve())
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-framerate", str(FPS), "-i", str(st / "f_%04d.png"),
                        "-vf", "minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc,format=yuv420p",
                        "-c:v", "libx264", "-crf", "18", str(dst)], check=True)
    return True


def main():
    CLIPS.mkdir(parents=True, exist_ok=True)
    pngs = sorted(SHOTS.glob("*.png"))
    made = []
    for i, png in enumerate(pngs):
        print(f"animating {png.name} (SVD) ...")
        frames = animate(png, 2000 + i*11)
        if frames:
            dst = CLIPS / f"{png.stem}.mp4"
            if encode(frames, dst):
                print("  ->", dst); made.append(str(dst))
        else:
            print("  FAILED", png.name)
    print(f"SVD_CLIPS_DONE {len(made)}/{len(pngs)}")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
