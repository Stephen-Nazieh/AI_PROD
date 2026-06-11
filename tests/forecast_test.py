#!/usr/bin/env python3
"""Cost-forecast tests — pure burn/runway math over synthetic ledger rows.

forecast(rows, now=...) is deterministic given its inputs, so these pin the window
filtering, per-unit daily burn, runway division, and the empty-ledger edge case —
no real ledger / services touched.

Run:  env/bin/python3 tests/forecast_test.py   (auto-run by `studio doctor`)
"""
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))

import cost_forecast as F  # noqa: E402

PASS, FAIL = "\033[32m✓\033[0m", "\033[31m✗\033[0m"
hard_failures = 0


def check(name, fn):
    global hard_failures
    try:
        detail = fn() or ""
        print(f"  {PASS} {name}{(' — ' + detail) if detail else ''}")
    except Exception as e:
        print(f"  {FAIL} {name} — {e}")
        hard_failures += 1
        if "-v" in sys.argv:
            traceback.print_exc()


NOW = 2_000_000.0  # fixed clock; window_days=10 → window_start = 1_136_000
ROWS = [
    {"company": "co", "unit": "A", "usd": 1.0, "ts": 1_900_000},   # in window
    {"company": "co", "unit": "A", "usd": 1.0, "ts": 1_500_000},   # in window
    {"company": "co", "unit": "A", "usd": 10.0, "ts": 1_000_000},  # OUT of window
    {"company": "co", "unit": "B", "usd": 0.5, "ts": 1_800_000},   # in window
]


def t_window_filtering_and_burn():
    f = F.forecast(ROWS, window_days=10, pool_usd=100.0, now=NOW)
    a = next(u for u in f["units"] if u["unit"] == "co/A")
    b = next(u for u in f["units"] if u["unit"] == "co/B")
    # A: only the 2 in-window rows count toward burn; the $10 row is lifetime-only.
    assert a["window_usd"] == 2.0, a
    assert a["lifetime_usd"] == 12.0, a
    assert a["window_calls"] == 2, a
    assert a["daily_burn"] == 0.2, a            # 2.0 / 10 days
    assert a["proj_30d"] == 6.0, a              # 0.2 * 30
    assert b["daily_burn"] == 0.05, b           # 0.5 / 10
    return "window filter + per-unit daily burn correct"


def t_totals_and_runway():
    f = F.forecast(ROWS, window_days=10, pool_usd=100.0, now=NOW)
    assert f["total_daily_burn"] == 0.25, f      # 0.2 + 0.05
    assert f["proj_30d_total"] == 7.5, f         # 0.25 * 30
    assert f["runway_days"] == 400.0, f          # 100 / 0.25
    assert f["top_burner"] == "co/A", f          # ranked by daily burn
    return "runway 400d, top burner co/A"


def t_empty_ledger_is_infinite_runway():
    f = F.forecast([], window_days=14, pool_usd=15000.0, now=NOW)
    assert f["units"] == [], f
    assert f["runway_days"] == float("inf"), f
    assert f["top_burner"] is None, f
    return "no spend → runway ∞, no top burner"


def t_ranking_orders_by_daily_burn():
    f = F.forecast(ROWS, window_days=10, pool_usd=100.0, now=NOW)
    burns = [u["daily_burn"] for u in f["units"]]
    assert burns == sorted(burns, reverse=True), burns
    assert f["units"][0]["unit"] == "co/A"
    return "units sorted by burn, descending"


if __name__ == "__main__":
    print("Cost-forecast tests")
    check("window filtering + per-unit daily burn", t_window_filtering_and_burn)
    check("totals + runway division", t_totals_and_runway)
    check("empty ledger → infinite runway", t_empty_ledger_is_infinite_runway)
    check("ranking by daily burn", t_ranking_orders_by_daily_burn)

    print()
    if hard_failures:
        print(f"\033[31mFAIL — {hard_failures} hard failure(s)\033[0m")
        sys.exit(1)
    print("\033[32mOK — 0 hard failure(s)\033[0m")
