#!/usr/bin/env python3
"""
Studio control-plane library — shared run-state model + service probes.

Foundation for the `studio` CLI (dashboard), the pipeline orchestrator, the cost
ledger, and observability. Pure read helpers over the canonical structures:
companies → business units (00_CORE/business_units.yaml) → production/<run>/ with
the 01..09 pipeline stages (provision_business_unit.PRODUCTION_DIRS).
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

import yaml

WORKSPACE_ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = WORKSPACE_ROOT / "00_CORE" / "business_units.yaml"
sys.path.insert(0, str(WORKSPACE_ROOT / "01_SKILLS"))

try:
    from provision_business_unit import PRODUCTION_DIRS  # canonical pipeline stages
except Exception:
    PRODUCTION_DIRS = [
        "01-scripts", "02-storyboards", "03-layout", "04-raw_renders",
        "05-assets", "06-audio", "07-editing", "08-subtitles", "09-deliver",
    ]

_IGNORE = {".gitkeep", ".DS_Store"}


# ── Registry ────────────────────────────────────────────────────────────────

def registry() -> dict:
    if not REGISTRY.exists():
        return {"companies": {}}
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {"companies": {}}


def companies() -> dict:
    return registry().get("companies", {})


def units(company: str) -> dict:
    return (companies().get(company, {}) or {}).get("units", {}) or {}


def unit_folder(company: str, unit: str) -> pathlib.Path:
    rec = units(company).get(unit, {})
    return WORKSPACE_ROOT / rec.get("folder", f"business_units/{company}/{unit}")


# ── Run-state model ─────────────────────────────────────────────────────────

def _populated(stage_dir: pathlib.Path) -> tuple[int, int]:
    """(file_count, physical_bytes) under a stage dir.

    Symlinks count toward the file count (the run still has those artifacts) but
    contribute ~0 bytes — after dedup they point at an already-counted original,
    so byte totals reflect real on-disk usage, not logical content size.
    """
    n, b = 0, 0
    if not stage_dir.exists():
        return 0, 0
    for f in stage_dir.rglob("*"):
        if not f.is_file() or f.name in _IGNORE or f.name.startswith("."):
            continue
        n += 1
        if f.is_symlink():
            continue  # deduped duplicate — no physical disk cost
        try:
            b += f.stat().st_size
        except OSError:
            pass
    return n, b


def run_summary(run_path: pathlib.Path) -> dict:
    """Stage-by-stage status for one production run."""
    stages = {}
    total_files, total_bytes, last_done = 0, 0, None
    for stage in PRODUCTION_DIRS:
        n, b = _populated(run_path / stage)
        stages[stage] = {"files": n, "bytes": b, "done": n > 0}
        total_files += n
        total_bytes += b
        if n > 0:
            last_done = stage
    deliver = stages.get("09-deliver", {})
    delivered = deliver.get("done", False)
    done_count = sum(1 for s in stages.values() if s["done"])
    return {
        "name": run_path.name,
        "path": str(run_path.relative_to(WORKSPACE_ROOT)),
        "stages": stages,
        "stages_done": done_count,
        "stages_total": len(PRODUCTION_DIRS),
        "current_stage": last_done,
        "delivered": delivered,
        "files": total_files,
        "bytes": total_bytes,
        "status": "delivered" if delivered else (f"in:{last_done}" if last_done else "empty"),
    }


def iter_runs(company: str | None = None, unit: str | None = None):
    """Yield (company, unit, run_path) for every production run."""
    for cslug, cdata in companies().items():
        if company and cslug != company:
            continue
        for uslug in (cdata.get("units") or {}):
            if unit and uslug != unit:
                continue
            prod = unit_folder(cslug, uslug) / "production"
            if not prod.exists():
                continue
            for run in sorted(prod.iterdir()):
                if run.is_dir() and not run.name.startswith("_") and run.name != "README.md":
                    yield cslug, uslug, run


def all_runs(company: str | None = None, unit: str | None = None) -> list[dict]:
    out = []
    for cslug, uslug, run in iter_runs(company, unit):
        s = run_summary(run)
        s["company"], s["unit"] = cslug, uslug
        out.append(s)
    return out


# ── Service probes ──────────────────────────────────────────────────────────

def _probe(url: str, timeout: float = 12.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(400).decode("utf-8", "ignore")
            return True, body
    except Exception as e:
        return False, str(e)[:60]


def services() -> list[dict]:
    """Probe the core studio services. Returns [{name, url, up, detail}]."""
    checks = [
        ("MLX :8000", "http://127.0.0.1:8000/health"),
        ("MLX :8001", "http://127.0.0.1:8001/health"),
        ("MLX :8002", "http://127.0.0.1:8002/health"),
        ("ComfyUI :8188", "http://127.0.0.1:8188/system_stats"),
        ("Paperclip :3100", "http://127.0.0.1:3100/api/health"),
        ("Bridge :3101", "http://127.0.0.1:3101/health"),
    ]
    out = []
    for name, url in checks:
        up, detail = _probe(url)
        st = ""
        if up:
            try:
                d = json.loads(detail)
                st = d.get("status") or d.get("bootstrapStatus") or "ok"
            except Exception:
                st = "ok"
        out.append({"name": name, "url": url, "up": up, "detail": st if up else detail})
    return out


# ── Local MLX inference ──────────────────────────────────────────────────────
#
# CRITICAL: mlx_lm.server loads whatever model the REQUEST names. If the name
# doesn't match the server's loaded model, it tries to fetch it from HuggingFace
# (404 / multi-GB download / hang). Always send the exact loaded model name.
MLX_FAST = ("http://127.0.0.1:8002/v1/chat/completions", "mlx-community/Qwen2.5-7B-Instruct-4bit")
MLX_BIG = ("http://127.0.0.1:8001/v1/chat/completions", "mlx-community/Qwen2.5-32B-Instruct-4bit")


def mlx_chat(messages, big=False, timeout=90, max_tokens=1500, temperature=0.2):
    """Call a local MLX server with the correct model name. Returns text or None."""
    import urllib.request
    url, model = MLX_BIG if big else MLX_FAST
    body = {"model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def human_bytes(n: float) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024 or unit == "T":
            return f"{int(n)}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


if __name__ == "__main__":
    print(json.dumps({"companies": list(companies()), "runs": len(all_runs())}, indent=2))
