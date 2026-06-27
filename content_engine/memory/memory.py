"""CONTENT ENGINE — MEMORY (robust + self-improving).

Two stores:
  runs.jsonl    — append-only log of every run (idea, format, channel, outcome, notes)
  learnings.md  — accumulated craft lessons, tagged [agent]. Agents inject the relevant ones
                  into their prompts, so the system gets better over time.

API:  record_run(...) · add_learning(agent, text) · learnings_for(agent) · recent_runs(n)
"""
import json, os, re
MEM = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(MEM, "runs.jsonl")
LEARN = os.path.join(MEM, "learnings.md")

def record_run(run, idea, fmt, channel, outcome, notes=""):
    rec = {"run": run, "idea": idea, "format": fmt, "channel": channel,
           "outcome": outcome, "notes": notes}
    with open(RUNS, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def recent_runs(n=10):
    if not os.path.exists(RUNS): return []
    return [json.loads(l) for l in open(RUNS) if l.strip()][-n:]

def add_learning(agent, text):
    """Record a craft lesson for an agent (or 'general'). De-dups on exact text."""
    line = f"- [{agent}] {text.strip()}"
    existing = open(LEARN).read() if os.path.exists(LEARN) else "# Content Engine — Learnings\n\n"
    if line in existing:
        return False
    open(LEARN, "w").write(existing.rstrip() + "\n" + line + "\n")
    return True

def learnings_for(agent):
    """Return the lessons tagged [agent] or [general], formatted for prompt injection."""
    if not os.path.exists(LEARN):
        return ""
    keep = []
    for ln in open(LEARN):
        m = re.match(r"- \[(\w+)\] (.+)", ln.strip())
        if m and m.group(1) in (agent, "general"):
            keep.append("- " + m.group(2))
    if not keep:
        return ""
    return "\n\n## Learnings so far (apply these)\n" + "\n".join(keep)
