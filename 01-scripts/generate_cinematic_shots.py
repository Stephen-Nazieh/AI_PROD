#!/usr/bin/env python3
"""Generate cinematic key-frame stills for the 'Median Detective' proof scene via
ComfyUI SDXL (reliable + fast on Mac). Output → 03_ASSETS/animation_pilots/
median_detective/shots/. These become the inputs SVD animates into moving shots.
"""
import json, time, urllib.request, pathlib, shutil, sys

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "ComfyUI" / "output"
DEST = ROOT / "03_ASSETS" / "animation_pilots" / "median_detective" / "shots"
NEG = "blurry, lowres, deformed, text, watermark, cartoon, oversaturated, ugly"

# cinematic noir shots — 16:9-ish SDXL resolution
SHOTS = [
    ("01_office", "cinematic film noir detective office at night, heavy rain streaking down a "
     "tall window, single desk lamp, volumetric haze, chiaroscuro lighting, 1940s, film grain, "
     "moody atmospheric wide establishing shot, anamorphic, highly detailed"),
    ("02_ledger", "extreme close-up of an open ledger filled with handwritten income figures on "
     "a worn wooden desk, dim warm lamplight, a magnifying glass, film noir, shallow depth of "
     "field, cinematic, dramatic shadows, film grain"),
    ("03_realization", "silhouette of a detective standing at a rain-streaked window, backlit by "
     "cold blue city lights, dramatic rim light, swirling cigarette smoke, film noir, cinematic, "
     "moody, a moment of quiet realization, anamorphic"),
]


def workflow(prompt, seed):
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 1216, "height": 832, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": seed, "steps": 30, "cfg": 7.0,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "cine"}},
    }


def post(path, payload):
    req = urllib.request.Request(f"{COMFY}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def get(path):
    return json.loads(urllib.request.urlopen(f"{COMFY}{path}", timeout=30).read())


def run_one(name, prompt, seed):
    pid = post("/prompt", {"prompt": workflow(prompt, seed)})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < 600:
        h = get(f"/history/{pid}")
        if pid in h and h[pid].get("outputs"):
            imgs = h[pid]["outputs"].get("7", {}).get("images", [])
            if imgs:
                src = OUT / (imgs[0].get("subfolder") or "") / imgs[0]["filename"]
                dst = DEST / f"{name}.png"
                shutil.copy(src, dst)
                return dst
        time.sleep(4)
    return None


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    made = []
    for i, (name, prompt) in enumerate(SHOTS):
        print(f"generating {name} ...")
        d = run_one(name, prompt, 1000 + i * 7)
        print("  ->", d if d else "FAILED")
        if d:
            made.append(str(d))
    print(f"CINEMATIC_SHOTS_DONE {len(made)}/{len(SHOTS)}")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
