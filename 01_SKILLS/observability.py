#!/usr/bin/env python3
"""
Observability (Phase 3) — health auto-recovery + log aggregation.

    observability heal [--apply]     # probe services; restart any that are down
    observability logs [--grep P] [--lines N] [--errors]   # aggregate recent logs

`heal` recovers by running the idempotent LAUNCH_STUDIO launcher (which starts
only what's missing). Designed to be safe to run on a timer (cron):
    */5 * * * * cd <repo> && ./studio heal --apply >> logs/heal.log 2>&1
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
import studio_lib as S  # noqa: E402

LAUNCHER = ROOT / "LAUNCH_STUDIO.command"


def heal(apply: bool = False) -> int:
    svcs = S.services()
    down = [s for s in svcs if not s["up"]]
    for s in svcs:
        mark = "\033[32m●\033[0m" if s["up"] else "\033[31m○\033[0m"
        print(f"  {mark} {s['name']:18} {s['detail']}")
    if not down:
        print("  ✅ all services healthy — nothing to recover")
        return 0
    print(f"\n  ⚠️  {len(down)} service(s) down: {', '.join(s['name'] for s in down)}")
    if not apply:
        print("  (dry run — pass --apply to attempt recovery via LAUNCH_STUDIO)")
        return 1
    if not LAUNCHER.exists():
        print("  ❌ LAUNCH_STUDIO.command not found"); return 1
    print("  🔧 running LAUNCH_STUDIO (idempotent — starts only what's down)…")
    subprocess.run(["bash", str(LAUNCHER)], stdin=subprocess.DEVNULL,
                   capture_output=True, text=True, timeout=300)
    # re-probe
    still = [s["name"] for s in S.services() if not s["up"]]
    if still:
        print(f"  ⚠️  still down after recovery: {', '.join(still)}")
        return 1
    print("  ✅ recovered — all services healthy")
    return 0


def _log_sources() -> list[pathlib.Path]:
    src = []
    src += sorted((ROOT / "logs").glob("*.log")) if (ROOT / "logs").exists() else []
    pc = pathlib.Path.home() / ".paperclip/instances/default/logs/server.log"
    if pc.exists():
        src.append(pc)
    return src


def logs(grep: str | None, lines: int, errors: bool) -> int:
    pat = re.compile(grep, re.I) if grep else None
    errpat = re.compile(r"error|fail|fatal|exception|traceback|❌|⚠️", re.I)
    rows = []
    for path in _log_sources():
        try:
            tail = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-400:]
        except Exception:
            continue
        for line in tail:
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
            if pat and not pat.search(clean):
                continue
            if errors and not errpat.search(clean):
                continue
            rows.append((path.name, clean))
    if not rows:
        print("  (no matching log lines)")
        return 0
    for name, line in rows[-lines:]:
        print(f"  \033[2m[{name[:18]:18}]\033[0m {line[:180]}")
    print(f"\n  {len(rows)} matching line(s) across {len(_log_sources())} sources")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observability")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("heal"); p.add_argument("--apply", action="store_true")
    p = sub.add_parser("logs")
    p.add_argument("--grep"); p.add_argument("--lines", type=int, default=40)
    p.add_argument("--errors", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "heal":
        return heal(a.apply)
    if a.cmd == "logs":
        return logs(a.grep, a.lines, a.errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
