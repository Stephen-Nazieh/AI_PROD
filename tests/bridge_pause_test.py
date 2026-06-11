#!/usr/bin/env python3
"""Bridge-pause tests — the quiesce contract that makes registry edits safe.

Verifies the migration-safety invariant: bridge_paused() must not yield until every
running poller has parked (acked the current pause), and must abort rather than race
if they don't. Fully offline — STATE_DIR is redirected to a temp dir and the
bridge-running probe is stubbed, so nothing touches /tmp or pgrep for real.

Run:  env/bin/python3 tests/bridge_pause_test.py   (or: studio doctor)
"""
import pathlib
import sys
import tempfile
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))

import bridge_pause as BP  # noqa: E402

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


def _fresh_state():
    """Point bridge_pause at a clean temp STATE_DIR and reset its derived paths."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="bridge_pause_test_"))
    BP.STATE_DIR = d
    BP.PAUSE_FILE = d / "paused"
    BP.ACK_DIR = d / "ack"
    BP.ACTIVE_DIR = d / "active"
    return d


def _set_bridge_running(val: bool):
    BP.bridge_running = lambda: val


# ── flag basics ──────────────────────────────────────────────────────────────

def t_pause_resume_roundtrip():
    _fresh_state()
    assert not BP.is_paused()
    BP.pause("migrating")
    assert BP.is_paused() and BP._pause_reason() == "migrating"
    BP.resume()
    assert not BP.is_paused()
    return "pause sets flag+reason; resume clears it"


# ── poller ack semantics ─────────────────────────────────────────────────────

def t_checkpoint_only_acks_when_paused():
    _fresh_state()
    assert BP.checkpoint("scaffold") is False, "no pause → no skip, no ack"
    assert BP._acked("scaffold") == 0.0
    BP.pause()
    assert BP.checkpoint("scaffold") is True, "paused → skip"
    assert BP._acked("scaffold") > 0, "ack recorded under pause"
    return "ack written only while paused"


def t_quiesce_waits_for_running_poller():
    _fresh_state()
    BP.register("scaffold")
    BP.pause()
    # poller hasn't acked yet → must NOT be considered quiesced
    assert BP.wait_quiesced(timeout=0.3) is False, "unparked poller must block quiesce"
    BP.checkpoint("scaffold")  # poller parks
    assert BP.wait_quiesced(timeout=0.3) is True, "acked poller → quiesced"
    return "waits until the registered poller acks the current pause"


def t_stale_ack_does_not_satisfy():
    _fresh_state()
    BP.register("scaffold")
    BP.checkpoint  # noqa - ensure attr exists
    # ack from BEFORE the pause (older than pause mtime) must not count
    BP.ACK_DIR.mkdir(parents=True, exist_ok=True)
    (BP.ACK_DIR / "scaffold").write_text(str(time.time()))
    time.sleep(0.02)
    BP.pause()
    assert BP.wait_quiesced(timeout=0.3) is False, "pre-pause ack must not satisfy quiesce"
    return "only an ack newer than the pause counts (no stale-ack race)"


def t_no_active_pollers_quiesces_immediately():
    _fresh_state()
    BP.pause()
    assert BP.active_pollers() == []
    assert BP.wait_quiesced(timeout=0.1) is True, "nothing running → instantly quiesced"
    return "no registered pollers → quiesced at once"


def t_disabled_poller_not_waited_on():
    # Only 'dispatch' is running; 'scaffold' disabled. Quiesce must not hang on scaffold.
    _fresh_state()
    BP.register("dispatch")
    BP.pause()
    BP.checkpoint("dispatch")
    assert BP.wait_quiesced(timeout=0.3) is True, "must ignore the unregistered (disabled) poller"
    return "quiesce depends only on registered pollers"


# ── context manager ──────────────────────────────────────────────────────────

def t_ctx_skips_wait_when_bridge_down():
    _fresh_state()
    _set_bridge_running(False)
    BP.register("scaffold")  # registered but bridge is 'down' → nothing actually polling
    with BP.bridge_paused("reg edit", timeout=0.2):
        assert BP.is_paused(), "flag set inside the block"
    assert not BP.is_paused(), "flag cleared on exit"
    return "bridge down → safe, yields without waiting"


def t_ctx_aborts_if_pollers_dont_park():
    _fresh_state()
    _set_bridge_running(True)
    BP.register("scaffold")  # running poller that never acks
    raised = False
    try:
        with BP.bridge_paused("reg edit", timeout=0.3):
            raise AssertionError("must not enter the block when pollers won't park")
    except BP.BridgeBusy:
        raised = True
    assert raised, "expected BridgeBusy when a running poller won't park"
    assert not BP.is_paused(), "pause flag cleared even on abort"
    return "raises BridgeBusy + cleans up rather than racing"


def t_ctx_restores_prior_pause_state():
    _fresh_state()
    _set_bridge_running(False)
    BP.pause("outer hold")          # pre-existing pause we did NOT set
    with BP.bridge_paused("inner", timeout=0.2):
        assert BP.is_paused()
    assert BP.is_paused(), "must NOT resume a pause it didn't set"
    assert BP._pause_reason() == "inner", "inner reason persists (we never cleared it)"
    BP.resume()
    return "nested pause: inner block doesn't clobber an outer hold"


# ── nap interruptibility ─────────────────────────────────────────────────────

def t_nap_returns_on_pause():
    _fresh_state()
    BP.register("scaffold")
    BP.pause()  # pause already present → nap should return fast and ack
    t0 = time.monotonic()
    BP.nap(5.0, "scaffold", tick=0.1)
    assert time.monotonic() - t0 < 1.0, "nap must bail out promptly when paused"
    assert BP._acked("scaffold") > 0, "nap acks on the way out"
    return "nap wakes + acks immediately under pause (no full-interval delay)"


def _run():
    saved = (BP.STATE_DIR, BP.PAUSE_FILE, BP.ACK_DIR, BP.ACTIVE_DIR, BP.bridge_running)
    print("Bridge-pause (registry-edit safety) tests")
    check("pause/resume roundtrip", t_pause_resume_roundtrip)
    check("checkpoint acks only while paused", t_checkpoint_only_acks_when_paused)
    check("quiesce waits for running poller", t_quiesce_waits_for_running_poller)
    check("stale (pre-pause) ack doesn't satisfy quiesce", t_stale_ack_does_not_satisfy)
    check("no active pollers → instant quiesce", t_no_active_pollers_quiesces_immediately)
    check("disabled poller not waited on", t_disabled_poller_not_waited_on)
    check("ctx: bridge down → yields without waiting", t_ctx_skips_wait_when_bridge_down)
    check("ctx: aborts (BridgeBusy) if pollers won't park", t_ctx_aborts_if_pollers_dont_park)
    check("ctx: restores prior pause state", t_ctx_restores_prior_pause_state)
    check("nap returns + acks promptly on pause", t_nap_returns_on_pause)
    BP.STATE_DIR, BP.PAUSE_FILE, BP.ACK_DIR, BP.ACTIVE_DIR, BP.bridge_running = saved


if __name__ == "__main__":
    _run()
    print(f"\n{'FAILED' if hard_failures else 'OK'} — {hard_failures} hard failure(s)")
    sys.exit(1 if hard_failures else 0)
