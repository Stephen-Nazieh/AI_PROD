#!/usr/bin/env python3
"""
Production pipeline orchestrator — advances a run through the canonical 01..09
stages with QA gates between them, dispatching each stage to its handler and
recording a per-run cost/time ledger.

A run's plan lives in `<run>/.pipeline/plan.yaml` (auto-created from DEFAULT_PLAN
on first use). Each stage declares:
    handler: manual | command | bridge | agent
    gate:    list of glob patterns that must exist in the stage dir to pass
             (empty list = optional/skippable stage)
    ...handler-specific keys (cmd / endpoint / role)

CLI (also via `studio pipeline ...`):
    pipeline status  <company> <unit> <run>
    pipeline advance <company> <unit> <run>     # run the next ungated stage
    pipeline run     <company> <unit> <run>     # advance until blocked / delivered
    pipeline snapshot <company> <unit> <run>    # checkpoint lightweight run state
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
import studio_lib as S  # noqa: E402

import yaml

BRIDGE = "http://127.0.0.1:3101"

# Default per-stage plan. Most stages are produced by agents/tools and the
# orchestrator gates on the artifacts they leave behind; a couple are wired to
# bridge endpoints to show automated dispatch. Tune per run in .pipeline/plan.yaml.
DEFAULT_PLAN = {
    "01-scripts":     {"handler": "manual",  "gate": ["screenplay.md"]},   # input (a writer agent)
    "02-storyboards": {"handler": "produce", "fn": "storyboard", "gate": ["shotlist.json"]},
    "03-layout":      {"handler": "manual",  "gate": []},                  # optional
    "04-raw_renders": {"handler": "produce", "fn": "renders",    "gate": ["shot_*.png"]},
    "05-assets":      {"handler": "manual",  "gate": []},                  # optional
    "06-audio":       {"handler": "produce", "fn": "audio",      "gate": ["*.wav"]},
    "07-editing":     {"handler": "produce", "fn": "editing",    "gate": ["timeline.mp4"]},
    "08-subtitles":   {"handler": "produce", "fn": "subtitles",  "gate": ["*.srt"]},
    "09-deliver":     {"handler": "produce", "fn": "deliver",    "gate": ["master.mp4"]},
}


def run_dir(company: str, unit: str, run: str) -> pathlib.Path:
    return S.unit_folder(company, unit) / "production" / run


def _plan_path(rd: pathlib.Path) -> pathlib.Path:
    return rd / ".pipeline" / "plan.yaml"


def load_plan(rd: pathlib.Path) -> dict:
    p = _plan_path(rd)
    if p.exists():
        return yaml.safe_load(p.read_text()) or {}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump({"stages": DEFAULT_PLAN}, sort_keys=False))
    return {"stages": DEFAULT_PLAN}


def gate_satisfied(rd: pathlib.Path, stage: str, spec: dict) -> bool:
    gate = spec.get("gate", ["*"])
    if not gate:
        return True  # optional stage
    sdir = rd / stage
    results = [any(sdir.glob(pat)) for pat in gate]
    return any(results) if spec.get("gate_any") else all(results)


# ── ledger ───────────────────────────────────────────────────────────────────

def _ledger(rd: pathlib.Path) -> pathlib.Path:
    p = rd / ".pipeline" / "ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(rd: pathlib.Path, entry: dict) -> None:
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    with _ledger(rd).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ledger_summary(rd: pathlib.Path) -> dict:
    p = _ledger(rd)
    if not p.exists():
        return {"events": 0, "seconds": 0.0, "tokens": 0}
    secs = toks = n = 0
    for line in p.read_text().splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        n += 1
        secs += e.get("seconds", 0) or 0
        toks += e.get("tokens", 0) or 0
    return {"events": n, "seconds": round(secs, 1), "tokens": toks}


# ── handlers ─────────────────────────────────────────────────────────────────

def run_handler(rd: pathlib.Path, company: str, unit: str, run: str,
                stage: str, spec: dict) -> dict:
    """Dispatch a stage. Returns {ok, detail, seconds, tokens}."""
    h = spec.get("handler", "manual")
    import time
    start = time.time()
    try:
        if h == "manual":
            detail = "manual stage — gating on produced artifacts"
            ok = gate_satisfied(rd, stage, spec)
        elif h == "command":
            cmd = spec["cmd"].replace("{run}", str(rd))
            r = subprocess.run(cmd, shell=True, cwd=str(rd), capture_output=True, text=True, timeout=1800)
            ok = r.returncode == 0
            detail = (r.stderr or r.stdout).strip()[:120] or f"exit {r.returncode}"
        elif h == "bridge":
            payload = dict(spec.get("payload", {}))
            payload.update({"company": company, "unit": unit, "run": run})
            data = json.dumps(payload).encode()
            req = urllib.request.Request(f"{BRIDGE}{spec['endpoint']}", data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode())
            ok = body.get("status") == "ok"
            detail = body.get("output_path", body.get("error", "ok"))
        elif h == "produce":
            # run the stage's Python producer (storyboard/renders/audio/editing/…)
            import pipeline_stages as PS
            fn = PS.PRODUCERS.get(spec.get("fn", ""))
            if fn is None:
                ok, detail = False, f"unknown producer '{spec.get('fn')}'"
            else:
                r = fn(rd=rd, company=company, unit=unit, run=run)
                ok, detail = r["ok"], r["detail"]
        elif h == "agent":
            # create a Paperclip issue for the responsible role/agent to do the stage
            detail = create_stage_issue(company, unit, run, stage, spec)
            ok = True  # dispatched; gate will confirm once the agent produces output
        else:
            ok, detail = False, f"unknown handler '{h}'"
    except Exception as e:
        ok, detail = False, str(e)[:120]
    return {"ok": ok, "detail": detail, "seconds": round(time.time() - start, 2),
            "tokens": 0, "handler": h}


def create_stage_issue(company: str, unit: str, run: str, stage: str, spec: dict) -> str:
    reg_unit = S.units(company).get(unit, {})
    pid = reg_unit.get("paperclip_project_id")
    title = f"[{run}] {stage}"
    desc = (f"Produce the **{stage}** deliverables for run `{run}` "
            f"({company}/{unit}). Output into "
            f"`business_units/{company}/{unit}/production/{run}/{stage}/`.")
    payload = {"title": title, "description": desc, "status": "backlog"}
    if spec.get("role_agent_id"):
        payload["assigneeAgentId"] = spec["role_agent_id"]
    if pid:
        payload["projectId"] = pid
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:3100/api/companies/15041ee2-b1c5-43ac-b488-04934bfa1806/issues",
            data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as r:
            iss = json.loads(r.read().decode())
        return f"created issue {iss.get('identifier', iss.get('id', '?'))}"
    except Exception as e:
        return f"issue creation failed: {e}"


# ── orchestration ────────────────────────────────────────────────────────────

def status(company: str, unit: str, run: str) -> dict:
    rd = run_dir(company, unit, run)
    if not rd.exists():
        raise SystemExit(f"❌ run not found: {rd}")
    plan = load_plan(rd)["stages"]
    rows, next_stage = [], None
    for stage in S.PRODUCTION_DIRS:
        spec = plan.get(stage, {"gate": ["*"]})
        ok = gate_satisfied(rd, stage, spec)
        rows.append((stage, spec.get("handler", "manual"), ok, spec.get("gate", ["*"])))
        if not ok and next_stage is None:
            next_stage = stage
    return {"rd": rd, "rows": rows, "next": next_stage, "ledger": ledger_summary(rd)}


def advance(company: str, unit: str, run: str) -> dict:
    st = status(company, unit, run)
    rd, nxt = st["rd"], st["next"]
    if nxt is None:
        return {"done": True, "msg": "all gates satisfied — run delivered ✅"}
    plan = load_plan(rd)["stages"]
    spec = plan.get(nxt, {})
    res = run_handler(rd, company, unit, run, nxt, spec)
    passed = res["ok"] and gate_satisfied(rd, nxt, spec)
    # QA review gate (#5): at key stages, a content review can BLOCK before more
    # compute is spent. A failed gate flags the run for a human.
    qa_note = ""
    import pipeline_stages as PS
    if passed and nxt in PS.QA_STAGES:
        qa = PS.qa_review(rd, nxt)
        qa_note = qa["notes"]
        if not qa["pass"]:
            passed = False
            res["detail"] = f"QA gate blocked: {qa['notes']}"
            create_stage_issue(company, unit, run, nxt,
                               {"title_suffix": "QA review failed"})
    record(rd, {"stage": nxt, "handler": res["handler"], "ok": passed,
                "detail": res["detail"], "seconds": res["seconds"], "tokens": res["tokens"],
                "qa": qa_note})
    return {"done": False, "stage": nxt, "passed": passed, "detail": res["detail"],
            "seconds": res["seconds"], "qa": qa_note}


def clear_produced(company: str, unit: str, run: str) -> list:
    """Wipe the artifacts of every 'produce' stage (02-09) so a revised script
    re-propagates. Leaves the input script (01-scripts) and manual stages intact."""
    rd = run_dir(company, unit, run)
    plan = load_plan(rd)["stages"]
    cleared = []
    for stage, spec in plan.items():
        if spec.get("handler") != "produce":
            continue
        sdir = rd / stage
        if sdir.exists():
            for f in sdir.iterdir():
                if f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)
                else:
                    f.unlink()
            cleared.append(stage)
    return cleared


def snapshot(company: str, unit: str, run: str) -> str:
    rd = run_dir(company, unit, run)
    if not rd.exists():
        raise SystemExit(f"❌ run not found: {rd}")
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    snap = rd / ".pipeline" / "snapshots" / ts
    snap.mkdir(parents=True, exist_ok=True)
    # lightweight: scripts + plan + a manifest (hash/size) of heavy artifacts
    for light in ("01-scripts", "08-subtitles", "project.yaml", ".pipeline/plan.yaml"):
        src = rd / light
        if src.exists():
            tgt = snap / light
            tgt.parent.mkdir(parents=True, exist_ok=True)
            (shutil.copytree(src, tgt, dirs_exist_ok=True) if src.is_dir() else shutil.copy2(src, tgt))
    manifest = []
    for f in rd.rglob("*"):
        if f.is_file() and ".pipeline" not in f.parts and f.name not in S._IGNORE:
            try:
                manifest.append({"path": str(f.relative_to(rd)), "bytes": f.stat().st_size})
            except OSError:
                pass
    (snap / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    return f"snapshot {ts} — {len(manifest)} artifacts manifested → {snap.relative_to(ROOT)}"


# ── CLI ──────────────────────────────────────────────────────────────────────

def _print_status(company, unit, run):
    st = status(company, unit, run)
    print(f"Pipeline: {company}/{unit}/{run}")
    for stage, handler, ok, gate in st["rows"]:
        mark = "\033[32m✓\033[0m" if ok else "\033[33m○\033[0m"
        g = ("any:" if False else "") + (", ".join(gate) if gate else "optional")
        print(f"  {mark} {stage:16} [{handler:7}] gate: {g}")
    l = st["ledger"]
    print(f"  next: {st['next'] or '— delivered'}   |   ledger: {l['events']} events, "
          f"{l['seconds']}s, {l['tokens']} tokens")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    parsers = {}
    for name in ("status", "advance", "run", "snapshot"):
        p = sub.add_parser(name)
        p.add_argument("company"); p.add_argument("unit"); p.add_argument("run")
        parsers[name] = p
    parsers["run"].add_argument(
        "--force", action="store_true",
        help="clear produced stages (02-09) and regenerate from the current script")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        _print_status(a.company, a.unit, a.run)
    elif a.cmd == "advance":
        r = advance(a.company, a.unit, a.run)
        print("  " + (r["msg"] if r.get("done") else
                      f"{'✓' if r['passed'] else '○'} {r['stage']}: {r['detail']} ({r['seconds']}s)"))
        _print_status(a.company, a.unit, a.run)
    elif a.cmd == "run":
        if getattr(a, "force", False):
            cleared = clear_produced(a.company, a.unit, a.run)
            print(f"  ♻️  --force: cleared {len(cleared)} produced stage(s) → "
                  f"{', '.join(cleared) or 'none'}")
        # QA the input script BEFORE spending render/TTS compute (#5).
        import pipeline_stages as PS
        sq = PS.qa_review(run_dir(a.company, a.unit, a.run), "01-scripts")
        print(f"  QA(script): {'✓ pass' if sq['pass'] else '✗ FAIL'} — {sq['notes']}")
        if not sq["pass"]:
            print("  ⏸  script failed QA review — revise the script, then re-run.")
            return 0
        for _ in range(len(S.PRODUCTION_DIRS) + 1):
            r = advance(a.company, a.unit, a.run)
            if r.get("done"):
                print("  " + r["msg"])
                # Stage publish for human approval (does NOT upload).
                try:
                    import publish
                    publish.prep(a.company, a.unit, a.run)
                except Exception as e:
                    print(f"  ⚠️ publish prep skipped: {e}")
                break
            qa = f"  ⟂ QA: {r['qa']}" if r.get("qa") else ""
            print(f"  {'✓' if r['passed'] else '○'} {r['stage']}: {r['detail']}{qa}")
            if not r["passed"]:
                print(f"  ⏸  blocked at {r['stage']} — produce its artifacts, then re-run")
                break
    elif a.cmd == "snapshot":
        print("  " + snapshot(a.company, a.unit, a.run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
