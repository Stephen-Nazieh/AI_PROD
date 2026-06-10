#!/usr/bin/env python3
"""
Publishing & business tools (Phase 6).

  publish     <co> <unit> <run> [--platform youtube] [--apply]   # stage/push a publish package
  dedup       [--company C] [--apply]                            # find/symlink duplicate artifacts (local)
  revenue     [--set "channel=amount"] [--target 6000]           # per-channel revenue vs target
  experiments <add|list|result> ...                             # monetization experiment tracker

dedup is fully local. publish stages a complete manifest and leaves a clean seam
for the platform upload (needs your YouTube/TikTok API creds). revenue/experiments
are local ledgers (00_CORE/revenue.yaml, 00_CORE/experiments.json) — the CRO/CAO
data layer, ready for live-analytics ingestion.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
import studio_lib as S  # noqa: E402
import yaml

CORE = ROOT / "00_CORE"


# ── publish ──────────────────────────────────────────────────────────────────

def publish(co, unit, run, platform, apply) -> int:
    rd = S.unit_folder(co, unit) / "production" / run
    if not rd.exists():
        print(f"❌ run not found: {rd}"); return 1
    masters = list((rd / "09-deliver" / "masters").glob("*")) + list((rd / "09-deliver").glob("*.mp4"))
    masters = [m for m in masters if m.is_file()]
    # title from the A/B test if present, else the screenplay heading
    title = run
    ab = rd / ".pipeline" / "ab_test.json"
    if ab.exists():
        tv = json.loads(ab.read_text()).get("title_variants", [])
        if tv:
            title = max(tv, key=lambda v: (v.get("ctr") or 0)).get("title", run)
    thumbs = list((rd / "09-deliver" / "thumbnails").glob("*.png"))
    manifest = {
        "company": co, "unit": unit, "run": run, "platform": platform,
        "title": title,
        "video": str(masters[0].relative_to(ROOT)) if masters else None,
        "thumbnail": str(thumbs[0].relative_to(ROOT)) if thumbs else None,
        "description": f"{title}\n\nProduced by DeParadigm Media.",
        "tags": [unit, co],
        "ready": bool(masters),
        "staged_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    out = rd / ".pipeline" / "publish_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    print(f"📤 Publish package staged for {platform}: '{title}'")
    print(f"   video: {manifest['video'] or '⚠️ no master in 09-deliver/'}")
    print(f"   manifest → {out.relative_to(ROOT)}")
    if not manifest["ready"]:
        print("   ⛔ not ready — produce a master in 09-deliver/masters/ first")
        return 1
    if apply:
        if platform != "youtube":
            print(f"   🔌 {platform} client not wired yet (only youtube). Manifest is ready.")
            return 0
        try:
            import youtube_client as yt
            vid = yt.upload(str(ROOT / manifest["video"]), manifest["title"],
                            manifest["description"], manifest["tags"], privacy="private")
            manifest["youtube_id"] = vid
            manifest["url"] = f"https://youtu.be/{vid}"
            manifest["published_privacy"] = "private"
            out.write_text(json.dumps(manifest, indent=2))
            print(f"   ✅ uploaded to YouTube as PRIVATE: {manifest['url']}")
            print("      (review it, then flip to public in YouTube Studio when ready)")
            if manifest["thumbnail"]:
                print(f"      thumbnail to set: {manifest['thumbnail']}")
        except Exception as e:
            print(f"   ❌ upload failed: {e}")
            return 1
    else:
        print("   (staged only — pass --apply to upload to YouTube as private)")
    return 0


# ── dedup (fully local) ──────────────────────────────────────────────────────

def _sha(p: pathlib.Path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def dedup(company, apply) -> int:
    seen: dict[str, pathlib.Path] = {}
    dupes: list[tuple[pathlib.Path, pathlib.Path]] = []
    saved = 0
    roots = []
    for cslug, cdata in S.companies().items():
        if company and cslug != company:
            continue
        for uslug in (cdata.get("units") or {}):
            roots.append(S.unit_folder(cslug, uslug) / "production")
    for base in roots:
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.is_symlink() or f.name in S._IGNORE or ".pipeline" in f.parts:
                continue
            if f.stat().st_size < 4096:   # ignore tiny files
                continue
            key = _sha(f)
            if key in seen:
                dupes.append((f, seen[key]))
                saved += f.stat().st_size
            else:
                seen[key] = f
    if not dupes:
        print(f"  ✅ no duplicate artifacts found ({len(seen)} unique files scanned)")
        return 0
    print(f"  Found {len(dupes)} duplicate artifact(s), {S.human_bytes(saved)} reclaimable:")
    for dup, orig in dupes[:20]:
        print(f"    {dup.relative_to(ROOT)}  ==  {orig.relative_to(ROOT)}")
    if len(dupes) > 20:
        print(f"    … and {len(dupes)-20} more")
    if apply:
        n = 0
        for dup, orig in dupes:
            try:
                dup.unlink()
                dup.symlink_to(orig.resolve())
                n += 1
            except OSError:
                pass
        print(f"  ✅ replaced {n} duplicate(s) with symlinks → reclaimed {S.human_bytes(saved)}")
    else:
        print("  (dry run — pass --apply to replace duplicates with symlinks)")
    return 0


# ── revenue ──────────────────────────────────────────────────────────────────

def revenue(set_kv, target) -> int:
    p = CORE / "revenue.yaml"
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    data = data or {}
    if set_kv:
        ch, _, amt = set_kv.partition("=")
        data[ch.strip()] = float(amt)
        p.write_text(yaml.safe_dump(data, sort_keys=False))
        print(f"  ✅ set {ch.strip()} = ${float(amt):.2f}/mo")
    total = sum(v for v in data.values() if isinstance(v, (int, float)))
    print(f"\n  Monthly revenue by channel (target ${target:.0f}/mo)")
    if not data:
        print("    (no data — set with: studio business revenue --set \"dev-cloud=250\")")
    for ch, amt in sorted(data.items(), key=lambda x: -x[1] if isinstance(x[1], (int, float)) else 0):
        if not isinstance(amt, (int, float)):
            continue
        bar = "█" * int(20 * min(1, amt / max(target, 1)))
        print(f"    {ch:18} ${amt:8.2f}  {bar}")
    pct = 100 * total / target if target else 0
    print(f"    {'TOTAL':18} ${total:8.2f}  ({pct:.0f}% of ${target:.0f} target)")
    return 0


# ── experiments ──────────────────────────────────────────────────────────────

def experiments(action, args) -> int:
    p = CORE / "experiments.json"
    data = json.loads(p.read_text()) if p.exists() else {"experiments": []}
    if action == "add":
        data["experiments"].append({
            "id": f"E{len(data['experiments'])+1}", "hypothesis": args.get("hypothesis", ""),
            "channel": args.get("channel", ""), "started": datetime.date.today().isoformat(),
            "status": "running", "lift": None, "result": None})
        p.write_text(json.dumps(data, indent=2))
        print(f"  ✅ logged experiment E{len(data['experiments'])}")
    elif action == "result":
        for e in data["experiments"]:
            if e["id"] == args.get("id"):
                e["status"] = "done"; e["lift"] = args.get("lift"); e["result"] = args.get("result")
        p.write_text(json.dumps(data, indent=2))
        print(f"  ✅ recorded result for {args.get('id')}")
    else:  # list
        if not data["experiments"]:
            print("  (no experiments — add with: studio business experiments add --hypothesis '...' --channel ...)")
        for e in data["experiments"]:
            print(f"  {e['id']} [{e['status']:7}] {e['channel']:12} {e['hypothesis'][:50]} "
                  f"{('lift '+str(e['lift'])) if e.get('lift') else ''}")
    return 0


def analytics() -> int:
    try:
        import youtube_client as yt
        s = yt.channel_stats()
    except Exception as e:
        print(f"  ⚠️ YouTube analytics unavailable: {e}")
        return 1
    print(f"  YouTube channel: {s.get('channel','?')}")
    print(f"    {s.get('subscribers',0):,} subscribers")
    print(f"    {s.get('views',0):,} total views")
    print(f"    {s.get('videos',0)} videos published")
    print("  Note: revenue ($) auto-fill needs the yt-analytics-monetary scope (re-consent) + AdSense;")
    print("        until then, log income via:  studio business revenue --set \"channel=amount\"")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="business")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("publish")
    pp.add_argument("company"); pp.add_argument("unit"); pp.add_argument("run")
    pp.add_argument("--platform", default="youtube"); pp.add_argument("--apply", action="store_true")
    pd = sub.add_parser("dedup"); pd.add_argument("--company"); pd.add_argument("--apply", action="store_true")
    pr = sub.add_parser("revenue"); pr.add_argument("--set"); pr.add_argument("--target", type=float, default=6000)
    sub.add_parser("analytics")
    pe = sub.add_parser("experiments"); pe.add_argument("action", choices=["add", "list", "result"])
    pe.add_argument("--hypothesis"); pe.add_argument("--channel"); pe.add_argument("--id"); pe.add_argument("--lift"); pe.add_argument("--result")
    a = ap.parse_args(argv)
    if a.cmd == "publish":
        return publish(a.company, a.unit, a.run, a.platform, a.apply)
    if a.cmd == "dedup":
        return dedup(a.company, a.apply)
    if a.cmd == "analytics":
        return analytics()
    if a.cmd == "revenue":
        return revenue(a.set, a.target)
    if a.cmd == "experiments":
        return experiments(a.action, {"hypothesis": a.hypothesis, "channel": a.channel,
                                      "id": a.id, "lift": a.lift, "result": a.result})
    return 0


if __name__ == "__main__":
    sys.exit(main())
