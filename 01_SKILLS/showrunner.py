#!/usr/bin/env python3
"""Showrunner — auto-generate a content calendar (episode briefs) per channel.

Grounds idea generation in the channel's STYLE (voice/goal) + KB (topics) and avoids
recent titles, then files each brief as a Paperclip issue assigned to the channel's
writer — so the dispatcher → writer → pipeline → publish chain runs itself.

  showrunner.py plan <co> <unit> [n]     # n fresh briefs for one channel (default 3)
  showrunner.py plan-all [n]             # n briefs for every unit in the company

Ideas use the local model (free); the actual scripts use the writers' Kimi tier.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import studio_lib as S  # noqa: E402

COMPANY_ID = "15041ee2-b1c5-43ac-b488-04934bfa1806"
API = "http://127.0.0.1:3100"


def _agents() -> list:
    try:
        with urllib.request.urlopen(f"{API}/api/companies/{COMPANY_ID}/agents", timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return []


def _writer_for(unit: str, agents: list) -> dict | None:
    """The unit's dedicated writer (best name-token match), else the shared script agent."""
    toks = set(unit.split("-"))
    best = None
    for a in agents:
        name = (a.get("name") or "").lower()
        if "writer" in name or "script" in name:
            score = sum(1 for t in toks if t in name)
            if score and (best is None or score > best[0]):
                best = (score, a)
    if best:
        return best[1]
    return next((a for a in agents if "script agent" in (a.get("name") or "").lower()), None)


def _recent_titles(co: str, unit: str, pid: str | None) -> list[str]:
    titles = []
    try:
        with urllib.request.urlopen(f"{API}/api/companies/{COMPANY_ID}/issues", timeout=10) as r:
            iss = json.loads(r.read())
        iss = iss if isinstance(iss, list) else iss.get("data", [])
        titles += [i.get("title", "") for i in iss if i.get("projectId") == pid]
    except Exception:
        pass
    prod = S.unit_folder(co, unit) / "production"
    if prod.is_dir():
        titles += [p.name for p in prod.iterdir() if p.is_dir()]
    return [t for t in titles if t][:40]


def _channel_context(co: str, unit: str) -> str:
    folder = S.unit_folder(co, unit)
    style = (folder / "STYLE.md")
    ctx = style.read_text(encoding="utf-8", errors="ignore")[:1200] if style.exists() else ""
    notes = sorted((folder / "knowledge" / "notes").glob("*.md")) if (folder / "knowledge" / "notes").is_dir() else []
    if notes:
        ctx += "\n\nKB topics: " + ", ".join(n.stem for n in notes[:12])
    return ctx


def _performance_signals(co: str, unit: str) -> str:
    """What's working (our published videos' views) + what's trending — the learning
    loop's input to topic selection. Graceful: returns a note if there's no data yet."""
    lines = []
    prod = S.unit_folder(co, unit) / "production"
    published = []
    if prod.is_dir():
        for mf in prod.glob("*/09-deliver/publish_manifest.json"):
            try:
                m = json.loads(mf.read_text())
                if m.get("status") == "uploaded" and m.get("videoId"):
                    published.append(m["videoId"])
            except Exception:
                pass
    if published:
        try:
            import youtube_client
            stats = [youtube_client.video_stats(v) for v in published[:25]]
            stats = sorted([s for s in stats if s], key=lambda x: -x.get("views", 0))[:5]
            if stats:
                lines.append("OUR TOP PERFORMERS (views): "
                             + "; ".join(f"{s['title']} ({s['views']}v/{s['likes']}♥)" for s in stats))
        except Exception:
            pass
    try:
        import youtube_client
        tr = youtube_client.trending(n=8)
        if tr:
            lines.append("TRENDING ON YOUTUBE NOW: " + "; ".join(tr[:8]))
    except Exception:
        pass
    return "\n".join(lines) or "(no performance/trend data yet — use the channel KB + judgment)"


def plan(co: str, unit: str, n: int = 3) -> int:
    rec = S.units(co).get(unit)
    if rec is None:
        print(f"❌ unknown unit {co}/{unit}"); return 1
    pid = rec.get("paperclip_project_id")
    import cost_ledger
    if cost_ledger.over_budget(co, unit):
        print(f"🚫 {rec.get('name', unit)} is over its daily budget — skipping (no briefs filed).")
        return 0
    agents = _agents()
    writer = _writer_for(unit, agents)
    if not writer:
        print(f"❌ no writer agent resolvable for {unit}"); return 1
    ctx = _channel_context(co, unit)
    recent = _recent_titles(co, unit, pid)
    signals = _performance_signals(co, unit)
    msg = [
        {"role": "system", "content":
         f"You are the showrunner for the '{rec.get('name', unit)}' channel. Each episode is a "
         f"SHORT-FORM video (~60-90 seconds) — keep every idea's scope TIGHT (one focused angle, "
         f"not a comprehensive deep-dive). Using the channel context below, propose {n} FRESH, "
         f"specific, on-brand episode ideas. Lean into what's working and ride relevant trends; "
         f"avoid anything similar to the recent titles. For each: a punchy title and a 2-3 "
         f"sentence brief (topic, angle, key beats). Reply with "
         f"ONLY a JSON array: [{{\"title\":\"...\",\"brief\":\"...\"}}].\n\n"
         f"CHANNEL CONTEXT:\n{ctx}\n\nPERFORMANCE & TRENDS:\n{signals}\n\n"
         f"RECENT TITLES (avoid): {recent}"},
        {"role": "user", "content": f"Give me {n} episode ideas."},
    ]
    out = S.mlx_chat(msg, big=True, max_tokens=1400, temperature=0.7) or ""
    m = re.search(r"\[.*\]", out, re.S)
    ideas = []
    if m:
        try:
            ideas = json.loads(m.group(0))
        except Exception:
            ideas = []
    ideas = [i for i in ideas if isinstance(i, dict) and i.get("title")][:n]
    if not ideas:
        print(f"⚠️ no ideas generated for {unit} (model returned nothing parseable)"); return 1
    filed = 0
    print(f"🎬 {rec.get('name', unit)} → {writer.get('name')}:")
    for idea in ideas:
        title = re.sub(r"^\s*EP:\s*", "", str(idea["title"]), flags=re.I)[:90]
        brief = str(idea.get("brief", ""))
        body = {"title": f"EP: {title}",
                "description": f"{brief}\n\nKeep the script TIGHT — ~60-90 seconds (≈150-220 "
                               f"words), a single complete segment (no multi-act), finishing with "
                               f"a clean closing line. Write it in the channel voice and save it to "
                               f"01-scripts/screenplay.md.",
                "status": "backlog", "assigneeAgentId": writer["id"]}
        if pid:
            body["projectId"] = pid
        try:
            r = urllib.request.Request(f"{API}/api/companies/{COMPANY_ID}/issues",
                                       data=json.dumps(body).encode(), method="POST")
            r.add_header("Content-Type", "application/json")
            urllib.request.urlopen(r, timeout=10)
            print(f"   + EP: {title}")
            filed += 1
        except Exception as e:
            print(f"   ✗ {title[:40]}: {str(e)[:60]}")
    print(f"  filed {filed} brief(s); the dispatcher will pick them up.")
    return 0


def plan_all(co: str, n: int = 2) -> int:
    for unit in S.units(co):
        plan(co, unit, n)
    return 0


def main() -> int:
    a = sys.argv[1:]
    if a and a[0] == "plan" and len(a) >= 3:
        return plan(a[1], a[2], int(a[3]) if len(a) > 3 else 3)
    if a and a[0] == "plan-all":
        co = a[1] if len(a) > 1 and not a[1].isdigit() else "deparadigm-media"
        n = int(a[-1]) if a[-1].isdigit() else 2
        return plan_all(co, n)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
