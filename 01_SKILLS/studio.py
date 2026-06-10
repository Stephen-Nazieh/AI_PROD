#!/usr/bin/env python3
"""
studio — unified control plane for the DeParadigm Media studio.

One entrypoint over the studio's tools and state. Subcommands compose the existing
modules (provision_business_unit, init_project, knowledge_base) and the shared
run-state model (studio_lib).

    studio status                       # services + companies/units/runs overview
    studio runs [--company C --unit U]  # production run dashboard (stage progress)
    studio new-project <company> <unit> --name "…" [--domain "…"]
    studio new-run <run> --company C --unit U --title "…"
    studio kb <cmd> ...                 # delegate to knowledge_base.py
    studio doctor                       # run smoke tests / health checks
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import pathlib

WORKSPACE_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "01_SKILLS"))
import studio_lib as S  # noqa: E402

PY = str(WORKSPACE_ROOT / "env" / "bin" / "python3")
SKILLS = WORKSPACE_ROOT / "01_SKILLS"

# ── rendering helpers ────────────────────────────────────────────────────────

GREEN, DIM, BOLD, RED, YELLOW, RESET = "\033[32m", "\033[2m", "\033[1m", "\033[31m", "\033[33m", "\033[0m"


def _bar(stages: dict) -> str:
    return "".join((GREEN + "█" + RESET) if s["done"] else (DIM + "░" + RESET)
                   for s in stages.values())


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_status(args) -> int:
    print(f"{BOLD}DeParadigm Media — studio status{RESET}")
    print(f"\n  {BOLD}Services{RESET}")
    for s in S.services():
        mark = f"{GREEN}●{RESET}" if s["up"] else f"{RED}○{RESET}"
        print(f"    {mark} {s['name']:18} {s['detail']}")
    import json as _json
    def _kb_docs(folder):
        idx = WORKSPACE_ROOT / folder / "knowledge" / ".kb" / "index.json"
        try:
            return len(_json.loads(idx.read_text()).get("documents", []))
        except Exception:
            return 0

    print(f"\n  {BOLD}Companies & business units{RESET}")
    runs = S.all_runs()
    for cslug, cdata in S.companies().items():
        us = cdata.get("units") or {}
        print(f"    {BOLD}{cdata.get('name', cslug)}{RESET} ({cslug}) — {len(us)} unit(s)")
        for uslug, u in us.items():
            ur = [r for r in runs if r["company"] == cslug and r["unit"] == uslug]
            deliv = sum(1 for r in ur if r["delivered"])
            docs = _kb_docs(u.get("folder", f"business_units/{cslug}/{uslug}"))
            print(f"      • {u.get('name', uslug):22} {uslug:14} "
                  f"{len(ur)} run(s), {deliv} delivered, {docs} KB docs")

    agents = "?"
    try:
        import urllib.request
        agents = len(_json.loads(urllib.request.urlopen(
            "http://127.0.0.1:3100/api/companies/15041ee2-b1c5-43ac-b488-04934bfa1806/agents",
            timeout=6).read()))
    except Exception:
        pass
    print(f"\n  {BOLD}Totals{RESET}: {len(runs)} runs, "
          f"{sum(1 for r in runs if r['delivered'])} delivered, "
          f"{S.human_bytes(sum(r['bytes'] for r in runs))} artifacts, {agents} agents")
    return 0


def cmd_runs(args) -> int:
    runs = S.all_runs(args.company, args.unit)
    if not runs:
        print("  (no production runs yet — create one: studio new-run <run> --company C --unit U --title …)")
        return 0
    print(f"{BOLD}Production runs{RESET}   stages: " +
          " ".join(s.split("-", 1)[1][:4] for s in S.PRODUCTION_DIRS))
    print(f"  {'RUN':40} PROGRESS    DONE  STATUS          FILES   SIZE")
    for r in runs:
        label = f"{r['company']}/{r['unit']}/{r['name']}"
        if len(label) > 39:
            label = "…" + label[-38:]
        st = r["status"]
        color = GREEN if r["delivered"] else (YELLOW if r["current_stage"] else DIM)
        print(f"  {label:40} {_bar(r['stages'])}  {r['stages_done']}/{r['stages_total']}   "
              f"{color}{st:14}{RESET}  {r['files']:5}  {S.human_bytes(r['bytes'])}")
    return 0


def cmd_new_project(args) -> int:
    argv = ["provision", args.company, args.unit]
    if args.name:
        argv += ["--name", args.name]
    if args.domain:
        argv += ["--domain", args.domain]
    return subprocess.call([PY, str(SKILLS / "provision_business_unit.py"), *argv])


def cmd_new_run(args) -> int:
    return subprocess.call([PY, str(SKILLS / "init_project.py"), "create", args.run,
                            "--company", args.company, "--unit", args.unit,
                            "--title", args.title])


_KB_TOOLS = {"semantic", "add-url", "promote", "pull", "audit", "stale", "graph"}


def cmd_kb(args) -> int:
    # route advanced commands to kb_tools.py, basics to knowledge_base.py
    tool = "kb_tools.py" if (args.rest and args.rest[0] in _KB_TOOLS) else "knowledge_base.py"
    return subprocess.call([PY, str(SKILLS / tool), *args.rest])


def cmd_pipeline(args) -> int:
    return subprocess.call([PY, str(SKILLS / "pipeline.py"), *args.rest])


def cmd_agents(args) -> int:
    return subprocess.call([PY, str(SKILLS / "agents_ops.py"), *args.rest])


def cmd_creative(args) -> int:
    return subprocess.call([PY, str(SKILLS / "creative.py"), *args.rest])


def cmd_business(args) -> int:
    return subprocess.call([PY, str(SKILLS / "business.py"), *args.rest])


def cmd_youtube(args) -> int:
    return subprocess.call([PY, str(SKILLS / "youtube_client.py"), *args.rest])


def cmd_backup(args) -> int:
    return subprocess.call([PY, str(SKILLS / "backup.py"), *(["--no-dedup"] if args.no_dedup else [])])


def cmd_costs(args) -> int:
    return subprocess.call([PY, str(SKILLS / "cost_ledger.py")])


def cmd_publish(args) -> int:
    sub = "apply" if args.apply else "prep"
    return subprocess.call([PY, str(SKILLS / "publish.py"), sub, args.company, args.unit, args.run])


def cmd_heal(args) -> int:
    return subprocess.call([PY, str(SKILLS / "observability.py"), "heal", *(["--apply"] if args.apply else [])])


def cmd_logs(args) -> int:
    extra = []
    if args.grep:
        extra += ["--grep", args.grep]
    if args.errors:
        extra += ["--errors"]
    return subprocess.call([PY, str(SKILLS / "observability.py"), "logs", "--lines", str(args.lines), *extra])


def cmd_doctor(args) -> int:
    smoke = WORKSPACE_ROOT / "tests" / "smoke_test.py"
    if smoke.exists():
        return subprocess.call([PY, str(smoke)])
    print("  (no smoke tests installed yet)")
    return cmd_status(args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="studio", description="DeParadigm Media studio control plane")
    sub = ap.add_subparsers(dest="cmd")  # optional — bare `studio` shows the dashboard

    sub.add_parser("status", help="services + companies/units/runs overview").set_defaults(fn=cmd_status)

    p_runs = sub.add_parser("runs", help="production run dashboard")
    p_runs.add_argument("--company"); p_runs.add_argument("--unit")
    p_runs.set_defaults(fn=cmd_runs)

    p_np = sub.add_parser("new-project", help="create/sync a business unit")
    p_np.add_argument("company"); p_np.add_argument("unit")
    p_np.add_argument("--name"); p_np.add_argument("--domain")
    p_np.set_defaults(fn=cmd_new_project)

    p_nr = sub.add_parser("new-run", help="scaffold a production run inside a unit")
    p_nr.add_argument("run"); p_nr.add_argument("--company", required=True)
    p_nr.add_argument("--unit", required=True); p_nr.add_argument("--title", default="Untitled")
    p_nr.set_defaults(fn=cmd_new_run)

    p_kb = sub.add_parser("kb", help="knowledge base (delegates to knowledge_base.py)")
    p_kb.add_argument("rest", nargs=argparse.REMAINDER)
    p_kb.set_defaults(fn=cmd_kb)

    p_pl = sub.add_parser("pipeline", help="production pipeline (status/advance/run/snapshot <co> <unit> <run>)")
    p_pl.add_argument("rest", nargs=argparse.REMAINDER)
    p_pl.set_defaults(fn=cmd_pipeline)

    p_ag = sub.add_parser("agents", help="agent ops (skills/digest/tree/budget/remember)")
    p_ag.add_argument("rest", nargs=argparse.REMAINDER)
    p_ag.set_defaults(fn=cmd_agents)

    p_cr = sub.add_parser("creative", help="creative tools (brand-check/i18n/ab/trends)")
    p_cr.add_argument("rest", nargs=argparse.REMAINDER)
    p_cr.set_defaults(fn=cmd_creative)

    p_bz = sub.add_parser("business", help="publish/dedup/revenue/experiments/analytics")
    p_bz.add_argument("rest", nargs=argparse.REMAINDER)
    p_bz.set_defaults(fn=cmd_business)

    p_yt = sub.add_parser("youtube", help="YouTube (check/trending/upload)")
    p_yt.add_argument("rest", nargs=argparse.REMAINDER)
    p_yt.set_defaults(fn=cmd_youtube)

    p_bk = sub.add_parser("backup", help="dedup + snapshot DBs/registry/KBs/personas")
    p_bk.add_argument("--no-dedup", action="store_true", help="skip the dedup maintenance pass")
    p_bk.set_defaults(fn=cmd_backup)

    sub.add_parser("costs", help="inference cost ledger ($/channel/model)").set_defaults(fn=cmd_costs)

    p_pub = sub.add_parser("publish", help="stage (prep) or upload (--apply) a delivered run to YouTube")
    p_pub.add_argument("company"); p_pub.add_argument("unit"); p_pub.add_argument("run")
    p_pub.add_argument("--apply", action="store_true", help="actually upload as PRIVATE (your approval)")
    p_pub.set_defaults(fn=cmd_publish)

    p_heal = sub.add_parser("heal", help="probe services + auto-recover the down ones")
    p_heal.add_argument("--apply", action="store_true", help="actually restart (default: dry run)")
    p_heal.set_defaults(fn=cmd_heal)

    p_logs = sub.add_parser("logs", help="aggregate recent logs across sources")
    p_logs.add_argument("--grep"); p_logs.add_argument("--lines", type=int, default=40)
    p_logs.add_argument("--errors", action="store_true")
    p_logs.set_defaults(fn=cmd_logs)

    sub.add_parser("doctor", help="run smoke tests / health checks").set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        # no subcommand (e.g. double-clicked) → show the dashboard + a hint
        rc = cmd_status(args)
        print(f"\n  {DIM}(this is the `studio` control CLI — try: studio runs | kb | pipeline | "
              f"agents | doctor.\n   To start services, double-click LAUNCH_STUDIO.command){RESET}")
        return rc
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
