#!/usr/bin/env python3
"""CONTENT ENGINE — final-output QUALITY GATE.

A finished short can be technically "produced" yet broken (no audio, mostly black, truncated,
wrong aspect). This verifies the deliverable before it's marked ready-to-publish, so a bad
render never reaches the posting queue silently.

  verify_social(video) -> {"ok": bool, "issues": [...], "stats": {...}}
"""
import json, os, re, subprocess, sys

def _probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height:format=duration",
                        "-of", "json", video], capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except Exception: return {}

def _mean_volume(video):
    r = subprocess.run(["ffmpeg", "-nostdin", "-i", video, "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None

def _luma(video, t):
    f = video + f".qa{int(t)}.png"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-ss", str(t), "-i", video, "-vframes", "1", f],
                   capture_output=True, text=True)
    try:
        from PIL import Image, ImageStat
        v = ImageStat.Stat(Image.open(f).convert("L")).mean[0]
    except Exception:
        v = 128.0
    finally:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass
    return v

def verify_social(video, min_sec=5.0, max_sec=180.0, expect_portrait=True, captions=None):
    issues, stats = [], {}
    if not os.path.exists(video) or os.path.getsize(video) < 20000:
        return {"ok": False, "issues": ["missing or tiny file"], "stats": {}}
    info = _probe(video)
    vs = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    a_s = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    stats["duration"] = round(dur, 1)
    if not vs:
        issues.append("no video stream")
    else:
        w, h = vs[0].get("width", 0), vs[0].get("height", 0); stats["dims"] = f"{w}x{h}"
        if expect_portrait and not (h > w):
            issues.append(f"not portrait ({w}x{h})")
    if dur < min_sec: issues.append(f"too short ({dur:.1f}s < {min_sec}s)")
    if dur > max_sec: issues.append(f"too long ({dur:.1f}s)")
    if not a_s:
        issues.append("no audio stream")
    else:
        mv = _mean_volume(video); stats["mean_volume_db"] = mv
        if mv is not None and mv < -50:
            issues.append(f"audio effectively silent ({mv} dB)")
    # luma: sample three points; flag if all near-black
    lumas = [_luma(video, t) for t in (min(1.0, dur / 4), dur / 2, dur * 3 / 4)] if dur else []
    stats["luma"] = [round(x, 1) for x in lumas]
    if lumas and max(lumas) < 12:
        issues.append("frames mostly black")
    if captions is not None and captions == 0:
        issues.append("no captions burned")
    return {"ok": len(issues) == 0, "issues": issues, "stats": stats}

if __name__ == "__main__":
    for v in sys.argv[1:]:
        r = verify_social(v)
        flag = "PASS" if r["ok"] else "FAIL"
        print(f"[{flag}] {os.path.basename(v)}  {r['stats']}" + (f"  ISSUES={r['issues']}" if not r["ok"] else ""))
