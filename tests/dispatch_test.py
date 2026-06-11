#!/usr/bin/env python3
"""
Dispatcher state-machine tests — fast, fully-offline checks for the one subsystem
that keeps regressing (wake-cooldown race, stuck-agent recovery, budget caps).

These exercise `paperclip_bridge.agent_dispatch_once()` and `cost_ledger`'s budget
gate by stubbing the network (`_api_request`), the DB reset (`_reset_agent_idle`),
the clock, and the ledger file — so no Paperclip / Postgres / MLX needs to be up.

Run:  env/bin/python3 tests/dispatch_test.py   (or: studio doctor)
Exit non-zero if any hard check fails.
"""
import importlib
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runtime" / "agents"))
sys.path.insert(0, str(ROOT / "01_SKILLS"))

import paperclip_bridge as B  # noqa: E402
import cost_ledger  # noqa: E402

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


# ── Fake Paperclip API ───────────────────────────────────────────────────────
# A single harness that records wakeups and serves a canned issue list + agent map,
# patched over the bridge's network/DB/clock seams. Each test builds one fresh.

class FakeWorld:
    def __init__(self, issues, agents, *, now=1000.0, reset_ok=True):
        self.issues = issues          # list of issue dicts
        self.agents = agents          # {agent_id: agent dict}
        self.now = now                # frozen clock
        self.reset_ok = reset_ok      # what _reset_agent_idle returns
        self.wakeups = []             # agent_ids that got a wakeup POST
        self.reset_calls = []         # agent_ids passed to _reset_agent_idle
        self.wakeup_returns_none = set()  # agent_ids whose wakeup is "rejected"

    def api_request(self, method, path, payload=None):
        if method == "GET" and path.endswith("/issues"):
            return self.issues
        if method == "GET" and "/api/agents/" in path:
            agent_id = path.rsplit("/", 1)[-1]
            return self.agents.get(agent_id)
        if method == "POST" and path.endswith("/wakeup"):
            agent_id = path.split("/api/agents/")[1].split("/")[0]
            if agent_id in self.wakeup_returns_none:
                return None
            self.wakeups.append(agent_id)
            return {"status": "woken"}
        raise AssertionError(f"unexpected API call: {method} {path}")

    def reset_agent_idle(self, agent_id):
        self.reset_calls.append(agent_id)
        if self.reset_ok:
            self.agents[agent_id]["status"] = "idle"
        return self.reset_ok

    def install(self):
        """Patch bridge seams to point at this world; reset cooldown state + clock."""
        B._api_request = self.api_request
        B._reset_agent_idle = self.reset_agent_idle
        B.time.time = lambda: self.now
        B._LAST_WOKEN.clear()
        return self


def issue(agent_id, status="backlog"):
    return {"status": status, "assigneeAgentId": agent_id}


def agent(status="idle", name=None, paused=False):
    a = {"status": status, "name": name}
    if paused:
        a["pausedAt"] = "2026-01-01T00:00:00Z"
    return a


# ── Dispatch state-machine tests ─────────────────────────────────────────────

def t_idle_with_backlog_woken():
    w = FakeWorld([issue("a1")], {"a1": agent("idle", "writer")}).install()
    r = B.agent_dispatch_once()
    assert w.wakeups == ["a1"], f"expected a1 woken, got {w.wakeups}"
    assert r["woken"] == ["writer"], r
    assert B._LAST_WOKEN.get("a1") == w.now, "cooldown timestamp not recorded"
    return "idle agent with backlog is woken"


def t_no_assignee_or_not_backlog_ignored():
    w = FakeWorld(
        [{"status": "backlog", "assigneeAgentId": None},   # unassigned
         issue("a1", status="in_progress"),                # not backlog
         {"status": "done", "assigneeAgentId": "a1"}],     # done
        {"a1": agent("idle")},
    ).install()
    r = B.agent_dispatch_once()
    assert w.wakeups == [], f"nothing should be woken, got {w.wakeups}"
    assert r["pending_agents"] == 0, r
    return "unassigned / non-backlog issues never dispatch"


def t_cooldown_blocks_rewake():
    # The double-dispatch race fix: an agent woken < AGENT_WAKE_COOLDOWN ago is skipped.
    w = FakeWorld([issue("a1")], {"a1": agent("idle")}).install()
    B._LAST_WOKEN["a1"] = w.now - (B.AGENT_WAKE_COOLDOWN - 1)  # just inside cooldown
    r = B.agent_dispatch_once()
    assert w.wakeups == [], f"cooldown should block re-wake, got {w.wakeups}"
    return f"no re-wake within {B.AGENT_WAKE_COOLDOWN}s cooldown"


def t_cooldown_expired_rewakes():
    w = FakeWorld([issue("a1")], {"a1": agent("idle")}).install()
    B._LAST_WOKEN["a1"] = w.now - (B.AGENT_WAKE_COOLDOWN + 1)  # just past cooldown
    B.agent_dispatch_once()
    assert w.wakeups == ["a1"], f"should re-wake after cooldown, got {w.wakeups}"
    return "re-wakes once cooldown elapses"


def t_paused_agent_never_woken():
    w = FakeWorld([issue("a1")], {"a1": agent("idle", paused=True)}).install()
    B.agent_dispatch_once()
    assert w.wakeups == [], "paused agent must not be woken"
    assert B._LAST_WOKEN.get("a1") is None, "paused agent should not record cooldown"
    return "pausedAt agent is left alone"


def t_busy_agent_not_disturbed():
    # A genuinely running agent (not a recoverable state) is left to finish.
    w = FakeWorld([issue("a1")], {"a1": agent("running")}).install()
    B.agent_dispatch_once()
    assert w.wakeups == [], "running agent must not be re-woken"
    assert w.reset_calls == [], "running agent must not be force-reset"
    return "running agent is not double-dispatched"


def t_stuck_agent_recovered_then_woken():
    # error/terminated/failed/crashed → reset to idle, then woken (else parked forever).
    for stuck in sorted(B.RECOVERABLE_STATES):
        w = FakeWorld([issue("a1")], {"a1": agent(stuck, "editor")}).install()
        B.agent_dispatch_once()
        assert w.reset_calls == ["a1"], f"[{stuck}] expected reset, got {w.reset_calls}"
        assert w.wakeups == ["a1"], f"[{stuck}] expected wake after recovery, got {w.wakeups}"
    return f"recovers {sorted(B.RECOVERABLE_STATES)} → idle → wakes"


def t_recovery_failure_leaves_agent():
    # If the DB reset fails, the agent stays non-idle and is NOT woken (no false dispatch).
    w = FakeWorld([issue("a1")], {"a1": agent("error")}, reset_ok=False).install()
    B.agent_dispatch_once()
    assert w.reset_calls == ["a1"], "should attempt reset"
    assert w.wakeups == [], "must not wake an agent that failed to reset"
    return "failed reset → no dispatch"


def t_rejected_wakeup_not_counted():
    # wakeup returning None (rejected) must NOT record cooldown — else a rejected wake
    # locks the agent out for the whole cooldown window.
    w = FakeWorld([issue("a1")], {"a1": agent("idle")}).install()
    w.wakeup_returns_none.add("a1")
    r = B.agent_dispatch_once()
    assert r["woken"] == [], f"rejected wake should not count, got {r['woken']}"
    assert B._LAST_WOKEN.get("a1") is None, "rejected wake must not set cooldown"
    return "rejected wakeup neither counts nor sets cooldown"


def t_unknown_agent_skipped():
    # Issue assigned to an agent the API can't resolve → skip, don't crash.
    w = FakeWorld([issue("ghost")], {}).install()
    r = B.agent_dispatch_once()
    assert w.wakeups == [], "unknown agent must not be woken"
    assert r["status"] == "ok", r
    return "unknown assignee skipped gracefully"


def t_bad_issue_list_errors_cleanly():
    w = FakeWorld([], {}).install()
    B._api_request = lambda *a, **k: "not-a-list"
    r = B.agent_dispatch_once()
    assert r["status"] == "error" and r["woken"] == [], r
    return "non-list issue payload → clean error, no crash"


# ── Budget-cap tests (cost_ledger) ───────────────────────────────────────────
# Drive the ledger off a temp file + env so we never touch the real logs/ledger.

def _ledger_with(rows, tmp, env):
    import json
    import time as _t
    importlib.reload(cost_ledger)
    cost_ledger.LEDGER = tmp
    now = int(_t.time())
    with tmp.open("w") as f:
        for r in rows:
            r.setdefault("ts", now)
            f.write(json.dumps(r) + "\n")


def t_over_budget_at_cap(tmpfactory):
    import os
    tmp = tmpfactory("cap")
    os.environ["CHANNEL_DAILY_CAP_USD"] = "5.0"
    _ledger_with([{"company": "c", "unit": "u", "usd": 5.0}], tmp, os.environ)
    assert cost_ledger.over_budget("c", "u") is True, "spend == cap must be over budget"
    assert cost_ledger.over_budget("c", "other") is False, "other unit is under budget"
    return "today_spend ≥ cap → over_budget"


def t_under_budget(tmpfactory):
    import os
    tmp = tmpfactory("under")
    os.environ["CHANNEL_DAILY_CAP_USD"] = "5.0"
    _ledger_with([{"company": "c", "unit": "u", "usd": 4.99}], tmp, os.environ)
    assert cost_ledger.over_budget("c", "u") is False, "under cap must not be over budget"
    return "spend < cap → under budget"


def t_zero_cap_disables(tmpfactory):
    import os
    tmp = tmpfactory("zero")
    os.environ["CHANNEL_DAILY_CAP_USD"] = "0"
    _ledger_with([{"company": "c", "unit": "u", "usd": 999.0}], tmp, os.environ)
    assert cost_ledger.over_budget("c", "u") is False, "cap=0 must disable the cap"
    return "cap=0 → never over budget (disabled)"


def t_per_unit_cap_override(tmpfactory):
    import os
    tmp = tmpfactory("override")
    os.environ["CHANNEL_DAILY_CAP_USD"] = "5.0"
    os.environ["CAP_SARCASTIC_ME"] = "2.0"   # CAP_<UNIT with - → _>
    _ledger_with([{"company": "c", "unit": "sarcastic-me", "usd": 3.0}], tmp, os.environ)
    assert cost_ledger.daily_cap("sarcastic-me") == 2.0, "per-unit env cap not honored"
    assert cost_ledger.over_budget("c", "sarcastic-me") is True, "$3 over a $2 unit cap"
    return "CAP_<UNIT> env overrides default cap"


def t_yesterday_spend_excluded(tmpfactory):
    import os
    import time as _t
    tmp = tmpfactory("stale")
    os.environ["CHANNEL_DAILY_CAP_USD"] = "5.0"
    yesterday = int(_t.time()) - 60 * 60 * 26
    _ledger_with([{"company": "c", "unit": "u", "usd": 99.0, "ts": yesterday}], tmp, os.environ)
    assert cost_ledger.today_spend("c", "u") == 0.0, "stale spend must not count toward today"
    assert cost_ledger.over_budget("c", "u") is False, "yesterday's spend should not cap today"
    return "only today's spend counts toward the cap"


def _run():
    import tempfile
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="dispatch_test_"))
    saved_env = {k: __import__("os").environ.get(k) for k in
                 ("CHANNEL_DAILY_CAP_USD", "CAP_SARCASTIC_ME")}
    # snapshot the seams we monkeypatch so we don't leak into other test modules
    saved = (B._api_request, B._reset_agent_idle, B.time.time)

    def tmpfactory(tag):
        return tmpdir / f"ledger_{tag}.jsonl"

    print("Dispatcher state-machine tests")
    check("idle+backlog → woken", t_idle_with_backlog_woken)
    check("unassigned / non-backlog ignored", t_no_assignee_or_not_backlog_ignored)
    check("cooldown blocks re-wake (double-dispatch race)", t_cooldown_blocks_rewake)
    check("re-wake after cooldown elapses", t_cooldown_expired_rewakes)
    check("paused agent never woken", t_paused_agent_never_woken)
    check("running agent not disturbed", t_busy_agent_not_disturbed)
    check("stuck agent recovered then woken", t_stuck_agent_recovered_then_woken)
    check("failed recovery → no dispatch", t_recovery_failure_leaves_agent)
    check("rejected wakeup not counted / no cooldown", t_rejected_wakeup_not_counted)
    check("unknown assignee skipped", t_unknown_agent_skipped)
    check("bad issue payload → clean error", t_bad_issue_list_errors_cleanly)

    print("Budget-cap (cost_ledger) tests")
    check("today_spend ≥ cap → over budget", lambda: t_over_budget_at_cap(tmpfactory))
    check("spend < cap → under budget", lambda: t_under_budget(tmpfactory))
    check("cap=0 disables the cap", lambda: t_zero_cap_disables(tmpfactory))
    check("CAP_<UNIT> env overrides default", lambda: t_per_unit_cap_override(tmpfactory))
    check("yesterday's spend excluded from today", lambda: t_yesterday_spend_excluded(tmpfactory))

    # restore seams + env
    B._api_request, B._reset_agent_idle, B.time.time = saved
    import os
    for k, v in saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    _run()
    print(f"\n{'FAILED' if hard_failures else 'OK'} — {hard_failures} hard failure(s)")
    sys.exit(1 if hard_failures else 0)
