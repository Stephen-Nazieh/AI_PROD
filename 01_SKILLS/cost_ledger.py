#!/usr/bin/env python3
"""Cost ledger — track inference spend per run / channel.

Local MLX/ComfyUI/TTS are free (own hardware); the real spend is the cloud writer
(Kimi). The runtime records each cloud call here; `studio costs` aggregates it so
the auto-loops (showrunner, auto-pipeline) are observable and budgetable.

Rates are estimates (USD per 1M tokens) and overridable via env — token counts from
the runtime are themselves estimates (chars/4), so treat $ as a ballpark, not a bill.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "logs" / "cost_ledger.jsonl"

# USD per 1M tokens (input, output). Local models = 0. Override via env.
RATES = {
    "kimi-for-coding": (float(os.environ.get("KIMI_USD_IN", "0.60")),
                        float(os.environ.get("KIMI_USD_OUT", "2.50"))),
}

# Per-channel daily spend cap (USD). Default applies to all; override one channel via
# env CAP_<unit-with-underscores>, e.g. CAP_SARCASTIC_ME=2.0. Set 0 to disable a cap.
DEFAULT_DAILY_CAP = float(os.environ.get("CHANNEL_DAILY_CAP_USD", "5.0"))


def daily_cap(unit: str) -> float:
    return float(os.environ.get(f"CAP_{unit.upper().replace('-', '_')}", DEFAULT_DAILY_CAP))


def today_spend(company: str, unit: str) -> float:
    midnight = time.mktime(datetime.date.today().timetuple())
    return round(sum(r.get("usd", 0.0) for r in _rows()
                     if r.get("company") == company and r.get("unit") == unit
                     and r.get("ts", 0) >= midnight), 4)


def over_budget(company: str, unit: str) -> bool:
    cap = daily_cap(unit)
    return cap > 0 and today_spend(company, unit) >= cap


def estimate_usd(model: str, in_tok: int, out_tok: int) -> float:
    rin, rout = RATES.get(model, (0.0, 0.0))
    return round(in_tok / 1e6 * rin + out_tok / 1e6 * rout, 4)


def record(company: str, unit: str, run: str, agent: str, model: str,
           in_tok: int, out_tok: int) -> float:
    usd = estimate_usd(model, in_tok, out_tok)
    rec = {"ts": int(time.time()), "company": company, "unit": unit, "run": run,
           "agent": agent, "model": model, "in_tok": in_tok, "out_tok": out_tok, "usd": usd}
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    return usd


def _rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def summary() -> dict:
    rows = _rows()
    by_unit, by_model = {}, {}
    total_usd = total_calls = total_in = total_out = 0
    for r in rows:
        u = f"{r.get('company')}/{r.get('unit')}"
        by_unit.setdefault(u, {"usd": 0.0, "calls": 0})
        by_unit[u]["usd"] += r.get("usd", 0.0)
        by_unit[u]["calls"] += 1
        m = r.get("model", "?")
        by_model.setdefault(m, {"usd": 0.0, "calls": 0})
        by_model[m]["usd"] += r.get("usd", 0.0)
        by_model[m]["calls"] += 1
        total_usd += r.get("usd", 0.0)
        total_calls += 1
        total_in += r.get("in_tok", 0)
        total_out += r.get("out_tok", 0)
    return {"total_usd": round(total_usd, 4), "calls": total_calls,
            "in_tok": total_in, "out_tok": total_out,
            "by_unit": by_unit, "by_model": by_model}


def _print() -> None:
    s = summary()
    print("\033[1mInference cost ledger\033[0m  (estimates)")
    if not s["calls"]:
        print("  (no cloud calls recorded yet)")
        return
    print(f"  total: ${s['total_usd']:.2f} over {s['calls']} call(s) "
          f"({s['in_tok']//1000}K in / {s['out_tok']//1000}K out)")
    print("  by channel (total | today/cap):")
    for u, d in sorted(s["by_unit"].items(), key=lambda kv: -kv[1]["usd"]):
        company, _, unit = u.partition("/")
        ts, cap = today_spend(company, unit), daily_cap(unit)
        flag = "  🚫 OVER CAP" if (cap > 0 and ts >= cap) else ""
        print(f"    {u:36} ${d['usd']:.2f}  | today ${ts:.2f}/${cap:.0f}{flag}  ({d['calls']} calls)")
    print("  by model:")
    for m, d in sorted(s["by_model"].items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {m:42} ${d['usd']:.2f}  ({d['calls']} calls)")


if __name__ == "__main__":
    _print()
