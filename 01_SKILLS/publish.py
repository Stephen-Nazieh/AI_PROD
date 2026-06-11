#!/usr/bin/env python3
"""Publish loop with a human-approval gate.

  publish.py prep  <co> <unit> <run>    # stage a publish manifest (title/desc/tags
                                          # from the script) — does NOT upload
  publish.py apply <co> <unit> <run>    # upload the master to YouTube as PRIVATE
                                          # (the human approval = choosing to run this)

The pipeline auto-runs `prep` after delivery and files an approval issue; nothing
goes live until a human runs `apply` (and even then it uploads PRIVATE, so you flip
it public on YouTube only when you're happy).
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
import studio_lib as S  # noqa: E402


def _run_dir(co: str, unit: str, run: str) -> pathlib.Path:
    return S.unit_folder(co, unit) / "production" / run


def _script(rd: pathlib.Path) -> str:
    d = rd / "01-scripts"
    f = d / "screenplay.md"
    if f.exists():
        return f.read_text(encoding="utf-8", errors="ignore")
    mds = sorted(d.glob("*.md")) if d.is_dir() else []
    return mds[0].read_text(encoding="utf-8", errors="ignore") if mds else ""


def _metadata(rd: pathlib.Path, run: str) -> dict:
    script = _script(rd)
    msg = [
        {"role": "system", "content":
         "From this short video script, write YouTube metadata. Reply with ONLY JSON: "
         "{\"title\":\"catchy, <=70 chars\",\"description\":\"2-3 sentence hook + what it "
         "covers\",\"tags\":[\"6-10 lowercase tags\"]}."},
        {"role": "user", "content": script[:2500]},
    ]
    import re
    out = S.mlx_chat(msg, big=True, max_tokens=400, temperature=0.3) or ""
    m = re.search(r"\{.*\}", out, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            return {"title": str(d.get("title") or run)[:100],
                    "description": str(d.get("description") or ""),
                    "tags": [str(t) for t in (d.get("tags") or [])][:12]}
        except Exception:
            pass
    return {"title": run, "description": "", "tags": []}


def prep(co: str, unit: str, run: str) -> int:
    rd = _run_dir(co, unit, run)
    master = rd / "09-deliver" / "master.mp4"
    if not master.exists():
        print(f"❌ no master.mp4 in {rd}/09-deliver — deliver the run first"); return 1
    thumb = rd / "09-deliver" / "thumbnail.jpg"
    meta = _metadata(rd, run)
    manifest = {
        "company": co, "unit": unit, "run": run,
        "title": meta["title"], "description": meta["description"], "tags": meta["tags"],
        "privacy": "private", "category": "27",
        "video": str(master.relative_to(ROOT)),
        "thumbnail": str(thumb.relative_to(ROOT)) if thumb.exists() else None,
        "status": "staged", "videoId": None,
    }
    out = rd / "09-deliver" / "publish_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"📤 staged publish manifest → {out.relative_to(ROOT)}")
    print(f"   title: {meta['title']}")
    _file_approval_issue(co, unit, run, meta["title"])
    print(f"   ⏸  awaiting approval — review the master, then: studio publish {co} {unit} {run} --apply")
    return 0


def _file_approval_issue(co: str, unit: str, run: str, title: str) -> None:
    """File an unassigned Paperclip issue so a human signs off before publishing.
    Unassigned → the agent dispatcher ignores it (it's a human task, not agent work)."""
    import urllib.request
    pid = (S.units(co).get(unit) or {}).get("paperclip_project_id")
    body = {"title": f"📤 Approve & publish: {title}"[:120],
            "description": (f"Auto-produced & delivered: {co}/{unit}/{run}. Review "
                            f"`09-deliver/master.mp4`, then run `studio publish {co} {unit} "
                            f"{run} --apply` to upload (PRIVATE). Manifest: "
                            f"`09-deliver/publish_manifest.json`."),
            "status": "backlog"}
    if pid:
        body["projectId"] = pid
    try:
        r = urllib.request.Request(
            f"http://127.0.0.1:3100/api/companies/{S.company_id()}/issues",
            data=json.dumps(body).encode(), method="POST")
        r.add_header("Content-Type", "application/json")
        urllib.request.urlopen(r, timeout=10)
        print("   📋 filed approval issue in Paperclip")
    except Exception:
        pass


def apply(co: str, unit: str, run: str) -> int:
    rd = _run_dir(co, unit, run)
    mf = rd / "09-deliver" / "publish_manifest.json"
    if not mf.exists():
        print("❌ no publish_manifest.json — run `prep` first"); return 1
    m = json.loads(mf.read_text())
    if m.get("status") == "uploaded":
        print(f"✅ already uploaded: https://youtu.be/{m.get('videoId')}"); return 0
    video = ROOT / m["video"]
    if not video.exists():
        print(f"❌ master missing: {video}"); return 1
    try:
        import youtube_client
        print(f"📡 uploading PRIVATE → YouTube: {m['title']}")
        vid = youtube_client.upload(str(video), m["title"], m.get("description", ""),
                                    m.get("tags"), privacy="private", category=m.get("category", "27"))
    except Exception as e:
        print(f"❌ upload failed: {e}"); return 1
    m["status"] = "uploaded"; m["videoId"] = vid
    mf.write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(f"✅ uploaded (private): https://youtu.be/{vid}")
    print("   flip to public on YouTube when you're happy with it.")
    return 0


def main(argv=None) -> int:
    a = sys.argv[1:] if argv is None else argv
    if len(a) < 4 or a[0] not in ("prep", "apply"):
        print(__doc__); return 1
    cmd, co, unit, run = a[0], a[1], a[2], a[3]
    return prep(co, unit, run) if cmd == "prep" else apply(co, unit, run)


if __name__ == "__main__":
    sys.exit(main())
