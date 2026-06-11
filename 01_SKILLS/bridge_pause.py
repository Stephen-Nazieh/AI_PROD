#!/usr/bin/env python3
"""Bridge maintenance pause — quiesce the background pollers before registry edits.

The bridge runs two background pollers on a timer:
  • scaffold — reads 00_CORE/business_units.yaml and WRITES folders + registry entries
  • dispatch — wakes agents (writes the agents DB, not the registry)

Editing the registry or the business_units/ layout while the scaffold poller runs
races it: it can write a stale registry shape back or create folders against the old
layout (this actually happened during the multi-company migration). The old fix was
"remember to pkill the bridge first." This replaces that with a flag the pollers honor:

    # in a migration script
    import bridge_pause
    with bridge_pause.bridge_paused("registry migration"):
        ...edit 00_CORE/business_units.yaml / move business_units/ ...

    # or from the shell
    studio bridge pause   →  do the migration  →  studio bridge resume

`bridge_paused()` sets the flag, then BLOCKS until every running poller acknowledges
it has parked (proving none is mid-write) before yielding — and aborts rather than
racing if they don't park in time. Pollers `register()` at startup so the wait only
depends on pollers that are actually running (disabled ones don't deadlock it).
"""
from __future__ import annotations

import contextlib
import os
import pathlib
import subprocess
import sys
import time

STATE_DIR = pathlib.Path(os.environ.get("BRIDGE_STATE_DIR", "/tmp/dpm_bridge"))
PAUSE_FILE = STATE_DIR / "paused"
ACK_DIR = STATE_DIR / "ack"
ACTIVE_DIR = STATE_DIR / "active"
BRIDGE_PROC = "runtime/agents/paperclip_bridge.py"


class BridgeBusy(RuntimeError):
    """Pollers did not park within the timeout — caller should abort, not race."""


# ── flag state ───────────────────────────────────────────────────────────────

def is_paused() -> bool:
    return PAUSE_FILE.exists()


def pause(reason: str = "") -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PAUSE_FILE.write_text(f"{int(time.time())} {reason}".strip() + "\n")


def resume() -> None:
    try:
        PAUSE_FILE.unlink()
    except FileNotFoundError:
        pass


def _pause_mtime() -> float:
    try:
        return PAUSE_FILE.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _pause_reason() -> str:
    try:
        parts = PAUSE_FILE.read_text().strip().split(" ", 1)
        return parts[1] if len(parts) > 1 else ""
    except FileNotFoundError:
        return ""


# ── poller side ──────────────────────────────────────────────────────────────

def register(poller: str) -> None:
    """A poller declares itself running, so wait_quiesced() knows to wait for it."""
    try:
        ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
        (ACTIVE_DIR / poller).write_text(str(time.time()))
    except OSError:
        pass


def unregister(poller: str) -> None:
    for d in (ACTIVE_DIR, ACK_DIR):
        try:
            (d / poller).unlink()
        except (FileNotFoundError, OSError):
            pass


def checkpoint(poller: str) -> bool:
    """Call at the top of each poll cycle. If paused, record an ack (proving this
    poller has observed the *current* pause and is parked, not writing) and return
    True so the caller skips its work this cycle."""
    if not PAUSE_FILE.exists():
        return False
    try:
        ACK_DIR.mkdir(parents=True, exist_ok=True)
        (ACK_DIR / poller).write_text(str(time.time()))
    except OSError:
        pass
    return True


def nap(seconds: float, poller: str, tick: float = 1.0) -> None:
    """Interruptible sleep used in place of time.sleep(interval): wakes (and acks)
    within ~tick of a pause appearing, so wait_quiesced() sees this poller park
    promptly instead of after a full poll interval."""
    end = time.monotonic() + seconds
    while True:
        if PAUSE_FILE.exists():
            checkpoint(poller)   # ack, then let the loop top keep us parked
            return
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(tick, remaining))


# ── controller side ──────────────────────────────────────────────────────────

def _acked(poller: str) -> float:
    try:
        return float((ACK_DIR / poller).read_text() or 0)
    except (FileNotFoundError, ValueError, OSError):
        return 0.0


def active_pollers() -> list[str]:
    try:
        return sorted(p.name for p in ACTIVE_DIR.iterdir())
    except FileNotFoundError:
        return []


def bridge_running() -> bool:
    try:
        return subprocess.run(["pgrep", "-f", BRIDGE_PROC],
                              capture_output=True).returncode == 0
    except Exception:
        return False


def wait_quiesced(timeout: float = 20.0) -> bool:
    """Block until every running poller has acked AFTER the pause was set (i.e. is
    parked, not mid-write), or until timeout. True if all parked. With no active
    pollers, returns True immediately."""
    if not is_paused():
        return False
    since = _pause_mtime()
    pollers = active_pollers()
    if not pollers:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(_acked(p) >= since for p in pollers):
            return True
        time.sleep(0.2)
    return False


@contextlib.contextmanager
def bridge_paused(reason: str = "maintenance", timeout: float = 20.0):
    """Pause the bridge pollers for the duration of the block, guaranteeing they've
    parked before yielding. No-op-safe if the bridge isn't running. Raises BridgeBusy
    (and does NOT yield) if a running poller won't park in time — so a migration
    aborts cleanly rather than racing. Restores the prior pause state on exit."""
    we_set = not is_paused()
    pause(reason)
    try:
        if bridge_running() and not wait_quiesced(timeout):
            raise BridgeBusy(
                f"bridge pollers ({', '.join(active_pollers()) or 'unknown'}) did not "
                f"park within {timeout}s — aborting to avoid racing the migration")
        yield
    finally:
        if we_set:
            resume()


def status() -> dict:
    actives = active_pollers()
    since = _pause_mtime()
    return {
        "paused": is_paused(),
        "reason": _pause_reason(),
        "paused_since": int(since) if since else None,
        "bridge_running": bridge_running(),
        "active_pollers": actives,
        "parked": {p: (_acked(p) >= since if since else False) for p in actives},
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

_C = {"g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "d": "\033[2m", "x": "\033[0m"}


def _print_status() -> None:
    s = status()
    if s["paused"]:
        since = (f" since {time.strftime('%H:%M:%S', time.localtime(s['paused_since']))}"
                 if s["paused_since"] else "")
        why = f" — {s['reason']}" if s["reason"] else ""
        print(f"  {_C['y']}⏸ PAUSED{_C['x']}{since}{why}")
    else:
        print(f"  {_C['g']}▶ running{_C['x']} (pollers active)")
    br = f"{_C['g']}up{_C['x']}" if s["bridge_running"] else f"{_C['d']}down{_C['x']}"
    print(f"  bridge process: {br}")
    if s["active_pollers"]:
        for p in s["active_pollers"]:
            mark = (f"{_C['g']}parked{_C['x']}" if s["parked"][p]
                    else (f"{_C['y']}running{_C['x']}" if s["paused"] else f"{_C['d']}active{_C['x']}"))
            print(f"    {p:10} {mark}")
    elif s["bridge_running"]:
        print(f"    {_C['d']}(no pollers registered){_C['x']}")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"

    if cmd == "pause":
        reason = " ".join(argv[1:]) or "manual"
        pause(reason)
        print(f"  {_C['y']}⏸ pause requested{_C['x']} — {reason}")
        if bridge_running():
            if wait_quiesced():
                print(f"  {_C['g']}✓ pollers parked{_C['x']} — safe to edit the registry / layout")
            else:
                print(f"  {_C['r']}✗ pollers did not park in time{_C['x']} — do NOT migrate; "
                      f"check the bridge or run `studio bridge resume`")
                return 1
        else:
            print(f"  {_C['d']}(bridge not running — nothing polling; safe to edit){_C['x']}")
        return 0

    if cmd == "resume":
        resume()
        print(f"  {_C['g']}▶ resumed{_C['x']} — pollers will pick up on their next cycle")
        return 0

    if cmd == "status":
        _print_status()
        return 0

    print(f"usage: studio bridge [pause [reason] | resume | status]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
