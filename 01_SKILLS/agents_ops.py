#!/usr/bin/env python3
"""
Agent operations (Phase 4) — visibility + control over the agent roster, working
around the Paperclip 'process' adapter's lack of a Skills tab / sync.

    agents_ops skills [--agent NAME]   # per-agent skills (library frontmatter ↔ roster)
    agents_ops digest [--days 7]       # recent activity per agent (run ledger)
    agents_ops tree                    # delegation hierarchy (issue parent→child)
    agents_ops budget [--agent N --set-cents C]   # show / set monthly budgets
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPANY = "15041ee2-b1c5-43ac-b488-04934bfa1806"
API = "http://127.0.0.1:3100"
PGCONN = dict(host="/tmp", port=54329, user="paperclip", password="paperclip", dbname="paperclip")


def _api(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode())


def _agents():
    return _api(f"/api/companies/{COMPANY}/agents")


def _library_skills() -> dict:
    """name -> [skills] from library/agents/<slug>/AGENTS.md frontmatter."""
    out = {}
    for f in (ROOT / "library" / "agents").glob("*/AGENTS.md"):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if not txt.startswith("---"):
            continue
        fm = txt.split("---", 2)[1]
        name, skills, in_sk = None, [], False
        for line in fm.splitlines():
            s = line.strip()
            if s.startswith("name:"):
                name = s.split(":", 1)[1].strip()
            elif s == "skills:" or s.startswith("skills:"):
                in_sk = True
            elif in_sk and s.startswith("- "):
                skills.append(s[2:].strip())
            elif in_sk and s and not s.startswith("- "):
                in_sk = False
        if name:
            out[name] = skills
    return out


def cmd_skills(agent_filter):
    lib = _library_skills()
    agents = sorted(_agents(), key=lambda a: a.get("title") or a.get("name") or "")
    shown = 0
    for a in agents:
        name = a.get("name", "")
        if agent_filter and agent_filter.lower() not in name.lower():
            continue
        sk = lib.get(name, [])
        adapter = a.get("adapterType", "?")
        tag = "" if sk else "  \033[2m(no library skills)\033[0m"
        print(f"  {name:34} [{adapter:12}] {', '.join(sk) if sk else '—'}{tag}")
        shown += 1
        if shown >= 60 and not agent_filter:
            print(f"  … ({len(agents) - shown} more — filter with --agent)"); break
    matched = sum(1 for a in agents if lib.get(a.get('name')))
    print(f"\n  {matched}/{len(agents)} agents have library-defined skills "
          f"(Paperclip Skills tab is unavailable for the 'process' adapter — this is the source of truth)")
    return 0


def cmd_digest(days):
    try:
        import psycopg2
        c = psycopg2.connect(connect_timeout=8, **PGCONN)
        cur = c.cursor()
        cur.execute("""
            select a.name, count(*) as runs,
                   sum(case when h.status in ('succeeded','completed') then 1 else 0 end) as ok,
                   sum(case when h.status='failed' then 1 else 0 end) as failed
            from heartbeat_runs h join agents a on a.id=h.agent_id
            where h.created_at > now() - interval '%s days' and a.company_id=%s
            group by a.name order by runs desc limit 25
        """, (days, COMPANY))
        rows = cur.fetchall()
        c.close()
    except Exception as e:
        print(f"  ⚠️ could not read run ledger: {e}"); return 1
    if not rows:
        print(f"  (no agent runs in the last {days} days)"); return 0
    print(f"  Agent activity — last {days} days")
    print(f"  {'AGENT':32} RUNS  OK  FAILED")
    for name, runs, ok, failed in rows:
        print(f"  {name[:32]:32} {runs:4}  {ok or 0:3}  {failed or 0:3}")
    print(f"\n  {len(rows)} active agent(s)")
    return 0


def cmd_tree():
    issues = _api(f"/api/companies/{COMPANY}/issues")
    issues = issues if isinstance(issues, list) else issues.get("data", [])
    by_id = {i["id"]: i for i in issues}
    children = {}
    roots = []
    for i in issues:
        pid = i.get("parentId")
        (children.setdefault(pid, []) if pid in by_id else roots).append(i) if pid else roots.append(i)
        if pid and pid in by_id:
            children.setdefault(pid, []).append(i)
    if not issues:
        print("  (no issues)"); return 0
    print(f"  Delegation tree ({len(issues)} issues)")

    def walk(node, depth):
        ident = node.get("identifier", node["id"][:8])
        print(f"  {'  ' * depth}└ {ident} {node.get('title', '')[:48]} "
              f"\033[2m[{node.get('status', '')}]\033[0m")
        for ch in children.get(node["id"], [])[:20]:
            walk(ch, depth + 1)

    for r in roots[:30]:
        if not r.get("parentId"):
            walk(r, 0)
    return 0


def cmd_budget(agent_filter, set_cents):
    agents = _agents()
    if set_cents is not None and agent_filter:
        target = [a for a in agents if agent_filter.lower() in a.get("name", "").lower()]
        for a in target:
            _api(f"/api/agents/{a['id']}", "PATCH", {"budgetMonthlyCents": set_cents})
            print(f"  ✅ set {a['name']} monthly budget → ${set_cents/100:.2f}")
        return 0
    print(f"  {'AGENT':34} BUDGET/mo    SPENT/mo")
    for a in sorted(agents, key=lambda x: -(x.get("spentMonthlyCents") or 0))[:25]:
        if agent_filter and agent_filter.lower() not in a.get("name", "").lower():
            continue
        b = a.get("budgetMonthlyCents")
        s = a.get("spentMonthlyCents") or 0
        print(f"  {a.get('name', '')[:34]:34} "
              f"{('$%.2f' % (b/100)) if b else 'unset':>10}   ${s/100:.2f}")
    return 0


def cmd_remember(agent_name, fact):
    import re
    import datetime
    lib = ROOT / "library" / "agents"
    target = agent_name.lower().strip()
    for d in sorted(lib.iterdir()):
        md = d / "AGENTS.md"
        if not md.is_file():
            continue
        m = re.search(r"^name:\s*(.+)$", md.read_text(encoding="utf-8"), re.MULTILINE)
        if m and target in m.group(1).strip().lower():
            mem = d / "MEMORY.md"
            with mem.open("a", encoding="utf-8") as f:
                f.write(f"- ({datetime.date.today().isoformat()}) {fact}\n")
            print(f"  ✅ remembered for {m.group(1).strip()} → {mem.relative_to(ROOT)}")
            print("     (the hybrid runtime injects MEMORY.md into the agent's prompt on every run)")
            return 0
    print(f"  ❌ no library agent matching '{agent_name}'")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agents_ops")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("skills"); p.add_argument("--agent")
    p = sub.add_parser("digest"); p.add_argument("--days", type=int, default=7)
    sub.add_parser("tree")
    p = sub.add_parser("budget"); p.add_argument("--agent"); p.add_argument("--set-cents", type=int)
    p = sub.add_parser("remember"); p.add_argument("agent"); p.add_argument("fact")
    a = ap.parse_args(argv)
    if a.cmd == "remember":
        return cmd_remember(a.agent, a.fact)
    if a.cmd == "skills":
        return cmd_skills(a.agent)
    if a.cmd == "digest":
        return cmd_digest(a.days)
    if a.cmd == "tree":
        return cmd_tree()
    if a.cmd == "budget":
        return cmd_budget(a.agent, a.set_cents)
    return 0


if __name__ == "__main__":
    sys.exit(main())
