#!/usr/bin/env python3
"""Dispatch observability — one view of why the pipeline is (or isn't) moving.

Three things stall an auto-pipeline, and until now each meant grepping logs:
  1. the dispatcher    — agents idle with backlog, or stuck/paused, or on cooldown
  2. render slots       — the ComfyUI concurrency semaphore is full (pipelines queue)
  3. the budget cap     — a channel hit its daily $ cap and is being skipped

This pulls all three into a single dashboard.

  studio dispatch            # render the dashboard
  studio dispatch --json     # machine-readable snapshot

Agent/cooldown state comes from the running bridge's read-only /dispatch-status
(the cooldown map lives in that process). Render slots (/tmp file-semaphore) and
budget (ledger file) are read directly, so those sections work even if the
bridge is down.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.request

import cost_ledger
import pipeline  # reuse SLOT_DIR / MAX_CONCURRENT so this never drifts from the limiter

BRIDGE = os.environ.get("BRIDGE_URL", "http://127.0.0.1:3101")

C = {
    "dim": "\033[2m", "rst": "\033[0m", "b": "\033[1m",
    "grn": "\033[32m", "yel": "\033[33m", "red": "\033[31m", "cyn": "\033[36m",
}


def _c(code: str, s: str) -> str:
    return f"{C[code]}{s}{C['rst']}"


# ── data sources ─────────────────────────────────────────────────────────────

def fetch_dispatch() -> dict:
    """Read-only dispatch snapshot from the bridge. {} (with _error) if unreachable."""
    try:
        with urllib.request.urlopen(f"{BRIDGE}/dispatch-status", timeout=8) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_error": str(e)[:80], "agents": []}


def render_slots() -> dict:
    """Read the /tmp file-semaphore the pipeline limiter uses. A slot whose holder
    PID is dead is reported reclaimable (the limiter reclaims it on next acquire)."""
    slots = []
    for i in range(pipeline.MAX_CONCURRENT):
        sf = pipeline.SLOT_DIR / f"slot_{i}"
        if not sf.exists():
            slots.append({"slot": i, "state": "free", "pid": None})
            continue
        try:
            pid = int(sf.read_text() or "0")
        except (ValueError, OSError):
            pid = 0
        alive = False
        if pid:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
        slots.append({"slot": i, "pid": pid,
                      "state": "busy" if alive else "stale"})
    busy = sum(1 for s in slots if s["state"] == "busy")
    return {"max": pipeline.MAX_CONCURRENT, "busy": busy, "slots": slots}


def budgets() -> list[dict]:
    """Per-channel today-spend vs daily cap, for every channel with ledger history."""
    out = []
    for u in cost_ledger.summary()["by_unit"]:
        company, _, unit = u.partition("/")
        spend, cap = cost_ledger.today_spend(company, unit), cost_ledger.daily_cap(unit)
        out.append({"channel": u, "today": spend, "cap": cap,
                    "over": bool(cap > 0 and spend >= cap)})
    out.sort(key=lambda r: -r["today"])
    return out


def snapshot() -> dict:
    return {"dispatch": fetch_dispatch(), "slots": render_slots(), "budgets": budgets()}


# ── rendering ────────────────────────────────────────────────────────────────

def _bar(frac: float, width: int = 12) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    return "▓" * filled + "░" * (width - filled)


def render(snap: dict) -> None:
    d = snap["dispatch"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(_c("b", "Dispatch observability") + _c("dim", f"   {now}"))

    # ── dispatcher line ──
    if d.get("_error"):
        print("\n  " + _c("red", "● dispatcher unreachable") +
              _c("dim", f"  (bridge {BRIDGE}: {d['_error']})"))
    else:
        on = d.get("dispatch_enabled", True)
        dot = _c("grn", "●") if on else _c("yel", "○")
        label = "running" if on else "disabled (AGENT_DISPATCH_DISABLED=1)"
        print(f"\n  {dot} dispatcher {label}" +
              _c("dim", f"   poll {d.get('poll_interval','?')}s · "
                        f"cooldown {d.get('cooldown_seconds','?')}s"))

    # ── agents ──
    agents = d.get("agents", [])
    recoverable = set(d.get("recoverable_states", []))
    print(_c("b", "\n  Agents") + _c("dim", "  (with backlog work or on cooldown)"))
    if not agents:
        print("    " + _c("dim", "— none waiting; nothing assigned in backlog"))
    else:
        print(_c("dim", f"    {'AGENT':22}{'STATUS':12}{'PEND':>5}  {'COOLDOWN':10} NOTE"))
        for a in agents:
            st = a["status"]
            if a["paused"]:
                label, color, note = "paused", "yel", "won't be woken"
            elif st == "idle":
                label, color, note = "idle", "grn", ("ready to dispatch" if a["pending"] else "")
            elif st in recoverable:
                label, color, note = st, "red", "auto-recovers → idle"
            else:
                label, color, note = st, "cyn", "busy / running"
            label = label[:11]
            cd = a["cooldown_remaining"]
            cdlabel = f"{cd}s" if cd else "ready"
            cdc = _c("yel", cdlabel) if cd else _c("dim", cdlabel)
            # pad by the *visible* label width (ANSI codes don't count toward str width)
            print(f"    {a['name'][:21]:22}{_c(color, label)}{'':<{max(0, 12 - len(label))}}"
                  f"{a['pending']:>5}  {cdc}{'':<{max(0, 10 - len(cdlabel))}} "
                  + _c("dim", note))

    # ── render slots ──
    s = snap["slots"]
    busy_c = _c("red" if s["busy"] >= s["max"] else "grn", f"{s['busy']}/{s['max']}")
    print(_c("b", "\n  Render slots ") + busy_c +
          _c("dim", "  (ComfyUI concurrency limiter)"))
    if s["busy"] >= s["max"]:
        print("    " + _c("yel", "full — new pipelines queue until a slot frees"))
    for sl in s["slots"]:
        if sl["state"] == "busy":
            print(f"    slot_{sl['slot']}  " + _c("cyn", f"pid {sl['pid']}") + _c("grn", "  ● alive"))
        elif sl["state"] == "stale":
            print(f"    slot_{sl['slot']}  " + _c("dim", f"pid {sl['pid']}") +
                  _c("yel", "  ○ dead holder (reclaimable)"))
        else:
            print(f"    slot_{sl['slot']}  " + _c("dim", "free"))

    # ── budgets ──
    print(_c("b", "\n  Budget ") + _c("dim", "(today / daily cap)"))
    bs = snap["budgets"]
    if not bs:
        print("    " + _c("dim", "— no cloud spend recorded yet"))
    else:
        for b in bs:
            cap = b["cap"]
            if cap <= 0:
                meter = _c("dim", "cap disabled")
            else:
                frac = b["today"] / cap
                meter = _bar(frac) + f"  {int(frac*100)}%"
                meter = _c("red", meter) if b["over"] else meter
            flag = _c("red", "  🚫 OVER CAP") if b["over"] else ""
            print(f"    {b['channel']:34} ${b['today']:.2f} / ${cap:.0f}   {meter}{flag}")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    snap = snapshot()
    if "--json" in argv:
        print(json.dumps(snap, indent=2))
    else:
        render(snap)
    # exit non-zero if the dispatcher is unreachable — lets scripts gate on it
    return 1 if snap["dispatch"].get("_error") else 0


if __name__ == "__main__":
    sys.exit(main())
