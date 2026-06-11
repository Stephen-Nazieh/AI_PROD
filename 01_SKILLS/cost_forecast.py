#!/usr/bin/env python3
"""Cost forecast — turn the inference cost ledger into a burn-rate + runway view.

`cost_ledger` answers "what have we spent?"; this answers "at this rate, how long
do we last, and which channel is burning it?". It reads the same JSONL ledger,
computes a trailing-window daily burn per business unit, projects 30 days out, and
divides a runway pool by total burn to estimate days of solvency remaining.

Cash burn = the cloud writer (Kimi) tokens. Local MLX/ComfyUI/TTS render is free
(own hardware), so render-hours don't enter the cash runway — only token spend does.

    studio forecast                 # 14-day trailing window vs default runway pool
    studio forecast --window 30 --pool 15000

Pool defaults to env RUNWAY_POOL_USD (else $15,000 — the governance_core default).
All figures are estimates: token counts are themselves chars/4 approximations.
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "01_SKILLS"))

import cost_ledger  # noqa: E402

DAY = 86400.0
DEFAULT_POOL_USD = float(os.environ.get("RUNWAY_POOL_USD", "15000"))


def forecast(rows: list[dict] | None = None, *, window_days: int = 14,
             pool_usd: float | None = None, now: float | None = None) -> dict:
    """Compute per-unit burn + runway. Pure given (rows, now) — pass both to test.

    Returns a dict with: window_days, pool_usd, per-unit burn records (sorted by
    daily burn, descending), total daily/window/lifetime burn, projected 30-day
    total, runway_days (float('inf') when burn is zero), and the top-burner key.
    """
    if rows is None:
        rows = cost_ledger._rows()
    if now is None:
        now = time.time()
    if pool_usd is None:
        pool_usd = DEFAULT_POOL_USD

    window_start = now - window_days * DAY
    units: dict[str, dict] = {}
    for r in rows:
        key = f"{r.get('company')}/{r.get('unit')}"
        u = units.setdefault(key, {"unit": key, "window_usd": 0.0,
                                    "lifetime_usd": 0.0, "window_calls": 0})
        usd = r.get("usd", 0.0)
        u["lifetime_usd"] += usd
        if r.get("ts", 0) >= window_start:
            u["window_usd"] += usd
            u["window_calls"] += 1

    for u in units.values():
        u["daily_burn"] = u["window_usd"] / window_days if window_days else 0.0
        u["proj_30d"] = u["daily_burn"] * 30
        u["window_usd"] = round(u["window_usd"], 4)
        u["lifetime_usd"] = round(u["lifetime_usd"], 4)
        u["daily_burn"] = round(u["daily_burn"], 4)
        u["proj_30d"] = round(u["proj_30d"], 2)

    ranked = sorted(units.values(), key=lambda x: -x["daily_burn"])
    total_daily = round(sum(u["daily_burn"] for u in ranked), 4)
    total_window = round(sum(u["window_usd"] for u in ranked), 4)
    total_life = round(sum(u["lifetime_usd"] for u in ranked), 4)
    runway_days = (pool_usd / total_daily) if total_daily > 0 else float("inf")

    return {
        "window_days": window_days,
        "pool_usd": round(pool_usd, 2),
        "units": ranked,
        "total_daily_burn": total_daily,
        "total_window_usd": total_window,
        "total_lifetime_usd": total_life,
        "proj_30d_total": round(total_daily * 30, 2),
        "runway_days": runway_days,
        "top_burner": ranked[0]["unit"] if ranked and ranked[0]["daily_burn"] > 0 else None,
    }


GREEN, DIM, BOLD, RED, YELLOW, RESET = (
    "\033[32m", "\033[2m", "\033[1m", "\033[31m", "\033[33m", "\033[0m")


def _fmt_runway(days: float) -> str:
    if days == float("inf"):
        return f"{GREEN}∞ (no recorded burn){RESET}"
    color = RED if days < 30 else YELLOW if days < 90 else GREEN
    return f"{color}{days:,.0f} days{RESET}  (~{days/30:.1f} months)"


def _print(window_days: int = 14, pool_usd: float | None = None) -> None:
    f = forecast(window_days=window_days, pool_usd=pool_usd)
    print(f"{BOLD}Cost forecast{RESET}  "
          f"{DIM}({f['window_days']}-day trailing window · estimates){RESET}")
    if not f["units"]:
        print("  (no spend recorded yet — burn $0/day, runway ∞)")
        return

    print(f"\n  {BOLD}Per-channel daily burn{RESET} (window | 30-day projection | lifetime):")
    for u in f["units"]:
        flag = f"  {RED}◄ top burner{RESET}" if u["unit"] == f["top_burner"] else ""
        print(f"    {u['unit']:34} ${u['daily_burn']:.3f}/day  | "
              f"30d ${u['proj_30d']:.2f}  | life ${u['lifetime_usd']:.2f}"
              f"  ({u['window_calls']} calls){flag}")

    print(f"\n  {BOLD}Totals{RESET}")
    print(f"    burn rate     ${f['total_daily_burn']:.3f}/day  "
          f"(${f['proj_30d_total']:.2f}/30d)")
    print(f"    runway pool   ${f['pool_usd']:,.2f}")
    print(f"    runway        {_fmt_runway(f['runway_days'])}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="cost_forecast")
    ap.add_argument("--window", type=int, default=14, help="trailing window in days")
    ap.add_argument("--pool", type=float, default=None, help="runway pool USD")
    a = ap.parse_args()
    _print(window_days=a.window, pool_usd=a.pool)
