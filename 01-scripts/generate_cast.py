#!/usr/bin/env python3
"""Generate the 'Significant' recurring-cast design lineup via ComfyUI SDXL — one
character sheet per role, in a SHARED stylized look so the ensemble reads as one show.
This is the look-lock artifact every animation method (3D / 2D rig / AI LoRA) references.
Output → business_units/deparadigm-media/ap-stats/assets/cast/.
"""
import json, time, urllib.request, pathlib, shutil, sys

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "ComfyUI" / "output"
DEST = ROOT / "business_units" / "deparadigm-media" / "ap-stats" / "assets" / "cast"

# Shared house style → ensemble cohesion. Tweak this one line to restyle the whole cast.
STYLE = ("character design model sheet, stylized 2D animated television series, "
         "semi-realistic proportions, clean confident linework, soft cel shading, "
         "cinematic key lighting, neutral slate-gray studio backdrop, upper body, "
         "expressive face, highly detailed, consistent art style")
NEG = ("photorealistic, photograph, 3d render, cgi, deformed, extra fingers, mutated, "
       "text, watermark, signature, blurry, lowres, ugly, inconsistent style")

CAST = [
    ("01_maya", "MAYA, a sharp driven startup founder in her early 30s, South-Asian, "
     "warm intense eyes, dark hair tied back, smart-casual blazer over a tee, confident"),
    ("02_nina", "NINA, an investigative journalist in her 30s, East-Asian, observant "
     "watchful expression, practical cool style, slightly rumpled jacket, press lanyard"),
    ("03_dev", "DEV, a composed defense attorney in his late 30s, Black, principled calm "
     "presence, crisp tailored suit and tie, steady gaze"),
    ("04_sam", "SAM, a warm clinical researcher and doctor in her 30s, Latina, kind "
     "thoughtful face, layered smart-casual under an open lab coat, stethoscope"),
    ("05_okafor", "PROFESSOR OKAFOR, a distinguished mentor in his 60s, Nigerian, "
     "salt-and-pepper hair, gentle wise smile, tweed jacket with elbow patches, round glasses"),
    ("06_vance", "COLE VANCE, a magnetic data-celebrity in his 40s, white, charismatic "
     "slightly slick confidence, expensive minimalist dark turtleneck, polished TED-stage look"),
]


def workflow(prompt, seed):
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": f"{STYLE}, {prompt}", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": seed, "steps": 32, "cfg": 7.0,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "cast"}},
    }


def post(p, d):
    r = urllib.request.Request(f"{COMFY}{p}", data=json.dumps(d).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())


def get(p):
    return json.loads(urllib.request.urlopen(f"{COMFY}{p}", timeout=30).read())


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
    for i, (name, prompt) in enumerate(CAST):
        print(f"designing {name} ...")
        d = run_one(name, prompt, 4200 + i * 13)
        print("  ->", d if d else "FAILED")
        if d:
            made.append(name)
    print(f"CAST_DONE {len(made)}/{len(CAST)}")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
