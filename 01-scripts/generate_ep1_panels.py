#!/usr/bin/env python3
"""Generate Episode 1 ("The Whale") scene panels in the show's house style (same
prefix as the cast, for cohesion) for the animatic. Output → production/S01E01/02-storyboards/.
"""
import json, time, urllib.request, pathlib, shutil, sys

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "ComfyUI" / "output"
DEST = ROOT / "business_units/deparadigm-media/ap-stats/production/S01E01/02-storyboards"

STYLE = ("stylized 2D animated television series, semi-realistic proportions, clean "
         "confident linework, soft cel shading, cinematic lighting, highly detailed, "
         "consistent art style, widescreen film still")
NEG = ("photorealistic, photograph, 3d render, cgi, deformed, extra fingers, text, "
       "watermark, blurry, lowres, ugly")

PANELS = [
    ("p1_pitch_night", "a driven South-Asian woman founder in a blazer alone in a modern "
     "open-plan startup office at night, rehearsing to a huge glowing presentation screen "
     "reading '$92,000', single desk lamp, moody wide shot"),
    ("p2_nina_doubt", "an East-Asian woman journalist in a casual jacket in an office "
     "kitchenette, holding a phone, skeptical raised eyebrow, morning light"),
    ("p3_whale_screen", "close-up of a laptop spreadsheet of incomes, most rows around "
     "thirty to forty thousand, one row glowing red reading $4,500,000, dim office"),
    ("p4_whiteboard", "the South-Asian founder writing the word MEAN on a glass whiteboard "
     "while the journalist watches with arms crossed, modern office"),
    ("p5_cafe_mentor", "a distinguished Nigerian professor in tweed and round glasses "
     "stirring tea at a cozy waterfront cafe, the young founder across the table with a laptop, warm light"),
    ("p6_slide_rebuild", "the founder at night editing a glowing presentation slide that "
     "now reads 'Typical user: $38,000', determined expression, dark office"),
    ("p7_pitch_room", "the founder presenting confidently to a sharp investor in a polished "
     "glass conference room, a chart on the wall, daytime city skyline view"),
    ("p8_investor_nod", "close-up of a sharp investor setting down a pen with a small "
     "approving nod, modern conference room, soft daylight"),
]


def workflow(prompt, seed):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": f"{STYLE}, {prompt}", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1216, "height": 832, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": seed, "steps": 30, "cfg": 7.0,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "ep1"}},
    }


def post(p, d):
    r = urllib.request.Request(f"{COMFY}{p}", data=json.dumps(d).encode(), headers={"Content-Type": "application/json"})
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
                shutil.copy(OUT / (imgs[0].get("subfolder") or "") / imgs[0]["filename"], DEST / f"{name}.png")
                return True
        time.sleep(4)
    return False


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, (name, prompt) in enumerate(PANELS):
        print(f"panel {name} ...")
        if run_one(name, prompt, 7000 + i * 17):
            n += 1; print("  ok")
        else:
            print("  FAILED")
    print(f"EP1_PANELS_DONE {n}/{len(PANELS)}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
