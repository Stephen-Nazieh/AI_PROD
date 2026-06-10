#!/usr/bin/env python3
"""
Studio smoke tests — fast, mostly-offline invariants that catch regressions in the
control plane (registry, run-state, knowledge bases, scaffolding consistency).

Run:  env/bin/python3 tests/smoke_test.py   (or: studio doctor)
Exit non-zero if any hard check fails. Network/service checks are warn-only.
"""
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))

PASS, FAIL, WARN = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[33m!\033[0m"
hard_failures = 0


def check(name, fn, warn_only=False):
    global hard_failures
    try:
        detail = fn() or ""
        print(f"  {PASS} {name}{(' — ' + detail) if detail else ''}")
    except Exception as e:
        mark = WARN if warn_only else FAIL
        print(f"  {mark} {name} — {e}")
        if not warn_only:
            hard_failures += 1
        if "-v" in sys.argv:
            traceback.print_exc()


def t_studio_lib():
    import studio_lib as S
    cos = S.companies()
    assert cos, "no companies in registry"
    return f"{len(cos)} companies, {len(S.all_runs())} runs"


def t_canonical_stages():
    import studio_lib as S
    assert S.PRODUCTION_DIRS[0] == "01-scripts" and S.PRODUCTION_DIRS[-1] == "09-deliver"
    return f"{len(S.PRODUCTION_DIRS)} stages"


def t_init_derives_from_canonical():
    import init_project, provision_business_unit
    top = [k for k in init_project.PROJECT_TEMPLATE if k != "episodes"]
    assert top == list(provision_business_unit.PRODUCTION_DIRS), \
        "init_project tree drifted from provision_business_unit.PRODUCTION_DIRS"
    return "init_project ↔ provision in sync"


def t_kb_resolves():
    import knowledge_base as kb, studio_lib as S
    co = next(iter(S.companies()))
    units = S.units(co)
    if not units:
        return "no units to check"
    u = next(iter(units))
    root = kb.kb_root(co, u)
    return f"{co}/{u} KB → {root.name}/"


def t_registry_folders_exist():
    import studio_lib as S
    missing = []
    for co, cdata in S.companies().items():
        for u, rec in (cdata.get("units") or {}).items():
            folder = ROOT / rec.get("folder", f"business_units/{co}/{u}")
            if not folder.exists():
                missing.append(f"{co}/{u}")
    assert not missing, f"folders missing: {missing}"
    return "all registry folders present on disk"


def t_name_slug_consistency():
    import studio_lib as S
    import re
    import json
    import urllib.request
    try:
        projs = {p["id"]: p["name"] for p in json.load(
            urllib.request.urlopen("http://127.0.0.1:3100/api/companies/"
                                   "15041ee2-b1c5-43ac-b488-04934bfa1806/projects", timeout=6))}
    except Exception:
        raise AssertionError("Paperclip not reachable (skip)")
    bad = []
    for u, rec in S.units("deparadigm-media").items():
        pn = projs.get(rec.get("paperclip_project_id"))
        if pn and re.sub(r"[^a-z0-9]+", "-", pn.lower()).strip("-") != u:
            bad.append(f"{pn}≠{u}")
    assert not bad, f"name/slug mismatch: {bad}"
    return "project names ↔ folder slugs consistent"


def t_services():
    import studio_lib as S
    down = [s["name"] for s in S.services() if not s["up"]]
    assert not down, f"down: {down}"
    return "all services up"


print("Studio smoke tests")
check("studio_lib + registry loads", t_studio_lib)
check("canonical pipeline stages", t_canonical_stages)
check("init_project derives from canonical tree", t_init_derives_from_canonical)
check("knowledge base resolves", t_kb_resolves)
check("registry folders exist on disk", t_registry_folders_exist)
check("project name ↔ folder slug consistency", t_name_slug_consistency, warn_only=True)
check("services reachable", t_services, warn_only=True)

print(f"\n{'FAILED' if hard_failures else 'OK'} — {hard_failures} hard failure(s)")
sys.exit(1 if hard_failures else 0)
