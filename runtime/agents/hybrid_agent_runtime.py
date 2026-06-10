#!/usr/bin/env python3
"""
hybrid_agent_runtime.py — Best of Both Worlds

THINK with Claude Code CLI (superior reasoning/coding) → 
EXECUTE with local ToolExecutor (reliable file/bash/git ops + macOS automation) →
REPORT to Paperclip

Architecture:
    Phase 1: Claude Code CLI generates plan/code via `claude-local -p`
    Phase 2: Parse markdown for structured actions (### FILE:, ### BASH:, ### APPLESCRIPT:, etc.)
    Phase 3: Execute actions with local ToolExecutor + macOS automation toolkit
    Phase 4: Report results + work products to Paperclip

Env vars (from Paperclip process adapter):
    PAPERCLIP_AGENT_ID, PAPERCLIP_ISSUE_ID, PAPERCLIP_ISSUE_TITLE,
    PAPERCLIP_ISSUE_DESCRIPTION, PAPERCLIP_COMPANY_ID, PAPERCLIP_API_URL
    ENABLE_MACOS_TOOLS=1      — enable AppleScript/Blender/FCP/Logic/Motion/Compressor tools
    ENABLE_DELEGATION_TOOLS=1 — enable invoke_openclaw tool
"""

import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Ensure workspace root is on path for runtime.tools imports
WORKSPACE_ROOT = Path("/Users/nazeera/Documents/AI_PRODUCER")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

try:
    from runtime.tools.macos_automation import (
        run_applescript, blender_headless, fcp_import_xml,
        logic_pro_bounce, motion_render, compressor_submit, ffmpeg_command,
    )
    MACOS_TOOLS_AVAILABLE = True
except Exception as _macos_import_err:
    MACOS_TOOLS_AVAILABLE = False
    print(f"⚠️  macOS automation tools not available: {_macos_import_err}", file=sys.stderr)

PAPERCLIP_API_BASE = os.environ.get("PAPERCLIP_API_URL", "http://127.0.0.1:3100")
PAPERCLIP_COMPANY_ID = os.environ.get("PAPERCLIP_COMPANY_ID", "15041ee2-b1c5-43ac-b488-04934bfa1806")
CLAUDE_BIN = os.environ.get("CLAUDE_LOCAL_BIN", "/Users/nazeera/Documents/AI_PRODUCER/env/bin/claude-local")

MACOS_TOOLS_ENABLED = os.environ.get("ENABLE_MACOS_TOOLS", "0") == "1" and MACOS_TOOLS_AVAILABLE
DELEGATION_TOOLS_ENABLED = os.environ.get("ENABLE_DELEGATION_TOOLS", "0") == "1"
OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "ws://127.0.0.1:18789")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "***REMOVED-ROTATED-SEE-.docker/.env***")

MAX_TURNS = 10  # Max Claude → Execute → Verify loops

# ── Paperclip API Client ────────────────────────────────────────────────────

class PaperclipClient:
    def __init__(self, api_base: str = PAPERCLIP_API_BASE, company_id: str = PAPERCLIP_COMPANY_ID):
        self.api_base = api_base.rstrip("/")
        self.company_id = company_id

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict | None:
        url = f"{self.api_base}{path}"
        data = json.dumps(payload).encode("utf-8") if payload else None
        req = urllib.request.Request(url, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"⚠️  Paperclip API {method} {path} failed: {e}", file=sys.stderr)
            return None

    def get_issue(self, issue_id: str) -> dict | None:
        return self._request("GET", f"/api/issues/{issue_id}")

    def next_assigned_issue(self, agent_id: str) -> dict | None:
        """Oldest backlog issue assigned to this agent (for wake-on-demand pickup), or None."""
        issues = self._request(
            "GET", f"/api/companies/{self.company_id}/issues?assigneeAgentId={agent_id}"
        )
        if not isinstance(issues, list):
            return None
        pending = [i for i in issues if isinstance(i, dict) and i.get("status") == "backlog"]
        return pending[0] if pending else None

    def get_agent(self, agent_id: str) -> dict | None:
        return self._request("GET", f"/api/agents/{agent_id}")

    def update_issue(self, issue_id: str, **fields) -> dict | None:
        return self._request("PATCH", f"/api/issues/{issue_id}", fields)

    def add_comment(self, issue_id: str, body: str) -> dict | None:
        return self._request("POST", f"/api/issues/{issue_id}/comments", {"body": body})

    def create_work_product(self, issue_id: str, **fields) -> dict | None:
        return self._request("POST", f"/api/issues/{issue_id}/work-products", fields)

    def report_cost(self, agent_id: str, cost_cents: int, input_tokens: int, output_tokens: int,
                    model: str, issue_id: str | None = None) -> None:
        payload = {
            "agentId": agent_id,
            "issueId": issue_id,
            "provider": "solocorn-local",
            "model": model,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "costCents": cost_cents,
            "occurredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        self._request("POST", f"/api/companies/{self.company_id}/cost-events", payload)


# ── Claude Client ───────────────────────────────────────────────────────────

class ClaudeClient:
    """Wraps claude-local -p to get structured output."""

    SYSTEM_PROMPT = """You are a senior software engineer working autonomously.
When you need to create or modify files, or run commands, use this exact structured format:

### FILE: <relative_path>
```<language>
<full file content>
```

### BASH:
```bash
<command to run>
```

### EDIT: <relative_path>
```diff
- <old line>
+ <new line>
```
"""

    MACOS_TOOLS_PROMPT = """
### APPLESCRIPT:
```applescript
<tell application block or raw AppleScript>
```

### BLENDER_SCRIPT:
```python
<Blender Python (bpy) script to run headlessly>
```

### INVOKE_OPENCLAW:
```
<task description to send to OpenClaw daemon for web browsing/WhatsApp/external APIs>
```

macOS automation tools are available. Use them to control applications:
- APPLESCRIPT: Control any macOS app (Final Cut Pro, Logic Pro, Motion, Compressor, etc.)
- BLENDER_SCRIPT: Run Python inside Blender headless mode
- INVOKE_OPENCLAW: Delegate web browsing or external API tasks to OpenClaw

AppleScript examples:
- Tell Final Cut Pro to import FCPXML:
  tell application "Final Cut Pro" to open POSIX file "/path/to/file.fcpxml"
- Tell Logic Pro to bounce:
  tell application "Logic Pro" to bounce project at (POSIX file "/path/out.wav")
- Check if app is running:
  tell application "System Events" to (name of processes) contains "Final Cut Pro"
"""

    def __init__(self, binary: str = CLAUDE_BIN, persona: str | None = None):
        self.binary = binary
        self.persona = persona          # per-agent persona (from library/agents/)
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.calls_made = []

    def _system_prompt(self) -> str:
        # Lead with the agent's own persona/charter so it acts AS that role,
        # then the shared structured-output protocol.
        parts = [self.persona] if self.persona else []
        parts.append(self.SYSTEM_PROMPT)
        if MACOS_TOOLS_ENABLED:
            parts.append(self.MACOS_TOOLS_PROMPT)
        parts.append("""
After all actions, explain your reasoning normally.
Important rules:
1. FILE blocks contain the COMPLETE file content (not diffs).
2. EDIT blocks use unified diff format (- old, + new).
3. BASH blocks contain ONE command per block.
4. APPLESCRIPT blocks contain valid AppleScript for macOS app automation.
5. BLENDER_SCRIPT blocks contain Python code for Blender's bpy API.
6. INVOKE_OPENCLAW blocks contain a plain-text task for OpenClaw.
7. Only use structured blocks when you actually need to take action.
8. If no files need changing, just explain your answer.
""")
        return "\n".join(parts)

    def call(self, task: str, context: str = "", max_tokens: int = 4096) -> dict:
        """Invoke claude-local -p and return parsed response."""
        prompt = self._build_prompt(task, context)
        start = time.time()

        try:
            result = subprocess.run(
                [self.binary, "--bare", "--print", prompt],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(WORKSPACE_ROOT),
            )
            elapsed = time.time() - start
            stdout = result.stdout
            stderr = result.stderr

            # Rough token estimation (1 token ≈ 4 chars for English)
            input_chars = len(prompt)
            output_chars = len(stdout)
            input_tokens = input_chars // 4
            output_tokens = output_chars // 4
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.calls_made.append({
                "elapsed": round(elapsed, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "exit_code": result.returncode,
            })

            if result.returncode != 0 and not stdout:
                return {
                    "status": "error",
                    "error": f"claude-local exited {result.returncode}: {stderr[:500]}",
                    "raw": stderr,
                }

            return {
                "status": "ok",
                "content": stdout,
                "stderr": stderr,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "elapsed": round(elapsed, 2),
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "claude-local timed out after 300s"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _build_prompt(self, task: str, context: str) -> str:
        parts = [self._system_prompt()]
        if context:
            parts.append(f"\nPrevious execution results:\n{context}\n")
        parts.append(f"\nTask: {task}\n")
        return "\n".join(parts)


# ── Action Parser ───────────────────────────────────────────────────────────

class ActionParser:
    """Parse Claude's markdown output into structured actions."""

    @staticmethod
    def parse(content: str) -> list[dict]:
        """Extract FILE, BASH, EDIT, APPLESCRIPT, BLENDER_SCRIPT, INVOKE_OPENCLAW actions."""
        actions = []

        # Parse ### FILE: blocks
        file_pattern = r'###\s*FILE:\s*(.+?)\n```(\w+)?\n(.*?)```'
        for match in re.finditer(file_pattern, content, re.DOTALL):
            path = match.group(1).strip()
            lang = (match.group(2) or "").strip()
            code = match.group(3)
            actions.append({
                "type": "write_file",
                "path": path,
                "content": code,
                "language": lang,
            })

        # Parse ### BASH: blocks
        bash_pattern = r'###\s*BASH:\s*\n```bash\n(.*?)```'
        for match in re.finditer(bash_pattern, content, re.DOTALL):
            cmd = match.group(1).strip()
            actions.append({
                "type": "bash",
                "command": cmd,
            })

        # Parse ### EDIT: blocks (unified diff style)
        edit_pattern = r'###\s*EDIT:\s*(.+?)\n```diff\n(.*?)```'
        for match in re.finditer(edit_pattern, content, re.DOTALL):
            path = match.group(1).strip()
            diff_text = match.group(2)
            edits = ActionParser._parse_diff(diff_text)
            for edit in edits:
                actions.append({
                    "type": "edit_file",
                    "path": path,
                    "old_string": edit["old"],
                    "new_string": edit["new"],
                })

        # Parse ### APPLESCRIPT: blocks
        applescript_pattern = r'###\s*APPLESCRIPT:\s*\n```applescript\n(.*?)```'
        for match in re.finditer(applescript_pattern, content, re.DOTALL):
            script = match.group(1).strip()
            actions.append({
                "type": "applescript",
                "script": script,
            })

        # Parse ### BLENDER_SCRIPT: blocks
        blender_pattern = r'###\s*BLENDER_SCRIPT:\s*\n```python\n(.*?)```'
        for match in re.finditer(blender_pattern, content, re.DOTALL):
            script = match.group(1).strip()
            actions.append({
                "type": "blender_script",
                "script": script,
            })

        # Parse ### INVOKE_OPENCLAW: blocks
        openclaw_pattern = r'###\s*INVOKE_OPENCLAW:\s*\n```\n(.*?)```'
        for match in re.finditer(openclaw_pattern, content, re.DOTALL):
            task = match.group(1).strip()
            actions.append({
                "type": "invoke_openclaw",
                "task": task,
            })

        # Heuristic: markdown code blocks after backtick file mentions
        heuristic_pattern = r'`([^`\n]+\.(py|js|ts|jsx|tsx|go|rs|java|kt|swift|c|cpp|h|hpp|yaml|yml|json|toml|md|sh|bash|zsh))`\s*\n```(\w+)?\n(.*?)```'
        for match in re.finditer(heuristic_pattern, content, re.DOTALL):
            path = match.group(1).strip()
            code = match.group(4)
            # Only add if we don't already have a FILE action for this path
            if not any(a["type"] == "write_file" and a["path"] == path for a in actions):
                actions.append({
                    "type": "write_file",
                    "path": path,
                    "content": code,
                    "language": match.group(3) or "",
                })

        return actions

    @staticmethod
    def _parse_diff(diff_text: str) -> list[dict]:
        """Parse simple unified diff (- old, + new) into edit pairs."""
        edits = []
        lines = diff_text.splitlines()
        i = 0
        while i < len(lines):
            # Collect consecutive - and + lines
            old_lines = []
            new_lines = []
            while i < len(lines) and lines[i].startswith("-"):
                old_lines.append(lines[i][1:])  # Remove leading -
                i += 1
            while i < len(lines) and lines[i].startswith("+"):
                new_lines.append(lines[i][1:])  # Remove leading +
                i += 1
            if old_lines and new_lines:
                edits.append({
                    "old": "\n".join(old_lines),
                    "new": "\n".join(new_lines),
                })
            else:
                i += 1
        return edits


# ── Tool Executor ───────────────────────────────────────────────────────────

def _resolve_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    return p.resolve()


# Per-run base directory for agent FILE WRITES (set by run_hybrid from the task's
# channel). Keeps creative/work output inside business_units/<co>/<unit>/production/
# instead of dumping into the repo root. Reads/cwd still resolve against WORKSPACE_ROOT.
_OUTPUT_BASE: Path | None = None

_STAGE_DIRS = {"01-scripts", "02-storyboards", "03-layout", "04-raw_renders",
               "05-assets", "06-audio", "07-editing", "08-subtitles", "09-deliver"}


def _resolve_write_path(path: str) -> Path:
    """Route an agent's file write into the per-run output base.

    Anything not already inside the run base is re-rooted under it, preserving a
    canonical stage tail when present — so 'scripts/x.md', '01-scripts/x.md', and a
    full '.../production/01-scripts/x.md' (run slug omitted) all land in
    <run>/01-scripts/x.md. Only deliberate external scratch (RAID / /tmp) escapes.
    """
    base = (_OUTPUT_BASE or WORKSPACE_ROOT).resolve()
    p = Path(path)
    raw = str(p)
    if p.is_absolute():
        s = str(p.resolve())
        if raw.startswith("/tmp/") or s.startswith("/private/tmp/") or s.startswith("/Volumes/"):
            return p.resolve()  # respect explicit external scratch / RAID

    # If the path names a canonical stage, file it under the run at that stage — this
    # takes priority so a full '.../production/01-scripts/x.md' (run slug omitted, abs
    # or relative) collapses to <run>/01-scripts/x.md instead of nesting.
    parts = p.parts
    for i, seg in enumerate(parts):
        if seg in _STAGE_DIRS:
            return (base / Path(*parts[i:])).resolve()

    # No stage hint: keep if already inside the run base, else re-root by basename.
    rp = (p if p.is_absolute() else base / p).resolve()
    try:
        rp.relative_to(base)
        return rp
    except ValueError:
        return (base / p.name).resolve()


def execute_action(action: dict) -> dict:
    """Execute a parsed action and return result."""
    try:
        if action["type"] == "write_file":
            return _tool_write_file(action["path"], action["content"])
        elif action["type"] == "bash":
            return _tool_bash(action["command"])
        elif action["type"] == "edit_file":
            return _tool_edit_file(action["path"], action["old_string"], action["new_string"])
        elif action["type"] == "applescript":
            return _tool_applescript(action["script"])
        elif action["type"] == "blender_script":
            return _tool_blender_script(action["script"])
        elif action["type"] == "invoke_openclaw":
            return _tool_invoke_openclaw(action["task"])
        else:
            return {"status": "error", "error": f"Unknown action type: {action['type']}"}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


def _tool_write_file(path: str, content: str) -> dict:
    p = _resolve_write_path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"status": "ok", "path": str(p), "bytes_written": len(content.encode("utf-8"))}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _tool_edit_file(path: str, old_string: str, new_string: str) -> dict:
    p = _resolve_write_path(path)
    if not p.exists():
        return {"status": "error", "error": f"File not found: {p}"}
    try:
        text = p.read_text(encoding="utf-8")
        if old_string not in text:
            return {"status": "error", "error": f"old_string not found in {p}"}
        new_text = text.replace(old_string, new_string, 1)
        p.write_text(new_text, encoding="utf-8")
        return {"status": "ok", "path": str(p), "replacements": 1}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _tool_bash(command: str, cwd: str = ".", timeout: int = 60) -> dict:
    try:
        working_dir = _resolve_path(cwd)
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "status": "ok",
            "command": command,
            "cwd": str(working_dir),
            "exit_code": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _tool_applescript(script: str) -> dict:
    """Execute AppleScript via the macOS automation toolkit."""
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = run_applescript(script)
    return {
        "status": result.get("status", "error"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


def _tool_blender_script(script: str) -> dict:
    """Execute a Blender Python script headlessly."""
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = blender_headless(script, timeout=600)
    return {
        "status": result.get("status", "error"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


def _tool_invoke_openclaw(task: str) -> dict:
    """Delegate a task to the OpenClaw daemon via WebSocket."""
    if not DELEGATION_TOOLS_ENABLED:
        return {"status": "error", "error": "Delegation tools are not enabled. Set ENABLE_DELEGATION_TOOLS=1"}

    try:
        import websocket
        ws_url = OPENCLAW_URL
        ws = websocket.create_connection(ws_url, timeout=30)
        # Simple JSON-RPC-ish message
        ws.send(json.dumps({
            "type": "task",
            "task": task,
            "authToken": OPENCLAW_TOKEN,
        }))
        response = ws.recv()
        ws.close()

        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            parsed = {"raw": response}

        return {
            "status": "ok",
            "openclaw_response": parsed,
            "message": f"OpenClaw task completed: {task[:80]}",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"OpenClaw delegation failed: {e}",
            "message": str(e),
        }


# ── Hybrid Runtime ──────────────────────────────────────────────────────────

def _normalize_agent_name(name: str) -> str:
    """
    Normalize an agent name for tolerant matching: strip a trailing duplicate
    suffix (" 2", " 3"), fold the legacy Solocorn brand onto DeParadigm Media
    (live agents may predate the rebrand), and lowercase.
    """
    n = name.strip()
    n = re.sub(r"\s+\d+$", "", n)                      # "Backend Architect 2" -> "Backend Architect"
    n = n.replace("Solocorn Studios", "DeParadigm Media")
    n = n.replace("SOLOCORN", "DEPARADIGM MEDIA").replace("Solocorn", "DeParadigm Media")
    return n.strip().lower()


def load_agent_persona(name: str) -> str | None:
    """
    Resolve an agent's persona (charter body) from library/agents/ by matching
    the Paperclip agent name against each definition's frontmatter `name:`
    (tolerant of duplicate suffixes and the Solocorn→DeParadigm rebrand).
    Returns the markdown body after the frontmatter, or None if no match.
    """
    if not name:
        return None
    lib = WORKSPACE_ROOT / "library" / "agents"
    if not lib.is_dir():
        return None
    target = _normalize_agent_name(name)
    for d in sorted(lib.iterdir()):
        md = d / "AGENTS.md"
        if not md.is_file():
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        m = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        if m and _normalize_agent_name(m.group(1)) == target:
            parts = text.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else text.strip()
            # Persistent per-agent memory: durable facts the agent has learned,
            # appended so they carry across runs (see `studio agents remember`).
            mem = d / "MEMORY.md"
            if mem.is_file():
                try:
                    mtext = mem.read_text(encoding="utf-8").strip()
                except Exception:
                    mtext = ""
                if mtext:
                    body += "\n\n## Persistent memory (facts you have learned)\n\n" + mtext
            return body
    return None


def _channel_for_project(project_id: str | None) -> tuple[str, str, dict] | None:
    """(company_slug, unit_slug, unit_record) for a Paperclip project, or None."""
    if not project_id:
        return None
    try:
        import yaml
        reg = yaml.safe_load((WORKSPACE_ROOT / "00_CORE" / "business_units.yaml").read_text())
    except Exception:
        return None
    for cslug, cdata in (reg.get("companies") or {}).items():
        for uslug, urec in (cdata.get("units") or {}).items():
            if urec.get("paperclip_project_id") == project_id:
                return cslug, uslug, urec
    return None


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "task").strip().lower()).strip("-")
    return s or "task"


def compute_output_base(issue: dict | None) -> Path:
    """Directory this task's file writes should land in: the channel's production
    run folder if the task maps to a channel, else a gitignored scratch area. Keeps
    agent output out of the repo root and segmented by company → unit."""
    issue = issue or {}
    run_slug = _slug(issue.get("identifier") or issue.get("title") or "task")
    ch = _channel_for_project(issue.get("projectId"))
    if ch:
        _, uslug, urec = ch
        folder = urec.get("folder", f"business_units/deparadigm-media/{uslug}")
        return WORKSPACE_ROOT / folder / "production" / run_slug
    return WORKSPACE_ROOT / ".agent_output" / run_slug


def load_kb_context(cslug: str, uslug: str, query: str, k: int = 3, max_chars: int = 2000) -> str | None:
    """Retrieve the channel KB's most relevant notes for the task and format them for
    injection — so agents GROUND output in the channel's knowledge instead of just
    the model's training. Lightweight lexical scoring (no sklearn, fast per-run)."""
    notes_dir = WORKSPACE_ROOT / "business_units" / cslug / uslug / "knowledge" / "notes"
    if not notes_dir.is_dir():
        return None
    q_terms = set(re.findall(r"[a-z0-9]{3,}", (query or "").lower()))
    if not q_terms:
        return None
    scored = []
    for f in sorted(notes_dir.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        body = text.split("---", 2)[-1] if text.startswith("---") else text
        terms = re.findall(r"[a-z0-9]{3,}", body.lower())
        if not terms:
            continue
        # query-term hits, length-normalized so a long note doesn't always win
        hits = sum(1 for t in terms if t in q_terms)
        score = hits / (len(terms) ** 0.5)
        if hits:
            scored.append((score, f.stem, body.strip()))
    if not scored:
        return None
    scored.sort(reverse=True)
    parts, total = [], 0
    for _, name, body in scored[:k]:
        chunk = f"### {name}\n{body[:700].strip()}"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    if not parts:
        return None
    return ("## Relevant knowledge from this channel's KB — use these facts; prefer them "
            "over your own assumptions:\n\n" + "\n\n".join(parts))


# ── Retry / backoff for failed runs ───────────────────────────────────────────
# Failed runs used to be re-queued to backlog forever (the dispatcher re-wakes them
# every 45s → thrash). Track attempts; after MAX_RETRIES, block + flag for a human.
MAX_RETRIES = 3
_RETRY_STATE = WORKSPACE_ROOT / ".agent_output" / "retry_state.json"


def _load_retry() -> dict:
    try:
        return json.loads(_RETRY_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_retry(state: dict) -> None:
    try:
        _RETRY_STATE.parent.mkdir(parents=True, exist_ok=True)
        _RETRY_STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def _bump_retry(issue_id: str) -> int:
    state = _load_retry()
    state[issue_id] = state.get(issue_id, 0) + 1
    _save_retry(state)
    return state[issue_id]


def _clear_retry(issue_id: str) -> None:
    state = _load_retry()
    if state.pop(issue_id, None) is not None:
        _save_retry(state)


def _maybe_trigger_pipeline() -> None:
    """If this run left a script under a channel's production run, fire the full
    production pipeline (storyboard→renders→audio→edit→subtitles→deliver) detached,
    so an approved script flows straight to a finished, QA-gated video."""
    base = _OUTPUT_BASE
    if not base:
        return
    sd = base / "01-scripts"
    if not (sd.is_dir() and any(sd.glob("*.md"))):
        return  # not a script-producing run
    parts = base.parts
    if "business_units" not in parts or "production" not in parts:
        return
    try:
        bi, pi = parts.index("business_units"), parts.index("production")
        company, unit, run = parts[bi + 1], parts[bi + 2], parts[pi + 1]
    except (ValueError, IndexError):
        return
    try:
        log = open("/tmp/auto_pipeline.log", "a")
        subprocess.Popen(
            [sys.executable, str(WORKSPACE_ROOT / "01_SKILLS" / "pipeline.py"),
             "run", company, unit, run],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(f"  🎬 auto-triggered pipeline: {company}/{unit}/{run}", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️ auto-pipeline trigger failed: {str(e)[:100]}", file=sys.stderr)


def load_channel_style(project_id: str | None) -> str | None:
    """Resolve a channel's voice/goals (STYLE.md) from the issue's Paperclip project.

    Lets one shared role agent (script writer, director, …) adopt the right tone per
    channel: the runtime injects the channel's STYLE based on which unit the task
    belongs to (matched via paperclip_project_id in the registry).
    """
    ch = _channel_for_project(project_id)
    if not ch:
        return None
    cslug, uslug, urec = ch
    folder = urec.get("folder", f"business_units/{cslug}/{uslug}")
    style_f = WORKSPACE_ROOT / folder / "STYLE.md"
    if style_f.is_file():
        return (f"## Channel context — you are producing for the "
                f"\"{urec.get('name', uslug)}\" channel.\n"
                f"Write your OUTPUT in the voice described below. Apply it; do NOT "
                f"restate, summarize, or quote these guidelines back.\n\n"
                + style_f.read_text(encoding="utf-8").strip())
    return None


def run_hybrid(agent_id: str, issue_id: str, issue_title: str, issue_description: str,
               client: PaperclipClient) -> dict:
    """Run the hybrid THINK → PARSE → EXECUTE loop."""

    # Load the agent's persona so it acts AS its role (e.g. Chief Content Officer)
    persona = None
    agent = client.get_agent(agent_id)
    if agent:
        persona = load_agent_persona(agent.get("name") or agent.get("title") or "")
        print(f"  🎭 Persona: {'loaded for ' + str(agent.get('name')) if persona else 'none (generic)'}",
              file=sys.stderr)

    # Inject the CHANNEL's voice/goals AND route this run's file writes into the
    # channel's production tree (instead of the repo root).
    global _OUTPUT_BASE
    try:
        iss = client.get_issue(issue_id) or {}
        style = load_channel_style(iss.get("projectId"))
        if style:
            persona = (persona or "") + "\n\n" + style
            print(f"  🎨 Channel voice injected", file=sys.stderr)
        ch = _channel_for_project(iss.get("projectId"))
        if ch:
            kbctx = load_kb_context(ch[0], ch[1], f"{issue_title}\n{issue_description}")
            if kbctx:
                persona = (persona or "") + "\n\n" + kbctx
                print(f"  📚 KB context injected ({ch[1]})", file=sys.stderr)
        _OUTPUT_BASE = compute_output_base(iss)
        print(f"  📂 Output → {_OUTPUT_BASE.relative_to(WORKSPACE_ROOT)}/", file=sys.stderr)
    except Exception:
        _OUTPUT_BASE = None

    claude = ClaudeClient(persona=persona)
    task = f"{issue_title}\n\n{issue_description}".strip()

    all_actions = []
    all_results = []
    execution_context = ""

    for turn in range(MAX_TURNS):
        print(f"  Turn {turn + 1}/{MAX_TURNS}: THINK → PARSE → EXECUTE", file=sys.stderr)

        # Phase 1: THINK — Ask Claude to generate plan/code
        response = claude.call(task, context=execution_context)

        if response["status"] != "ok":
            return {"status": "error", "error": f"Claude failed: {response.get('error')}"}

        content = response["content"]
        print(f"  🧠 Claude responded ({len(content)} chars)", file=sys.stderr)

        # Phase 2: PARSE — Extract actionable items
        actions = ActionParser.parse(content)
        print(f"  📋 Parsed {len(actions)} actions", file=sys.stderr)

        if not actions:
            # No actions needed — Claude just provided analysis/advice
            all_results.append({
                "turn": turn + 1,
                "phase": "analysis",
                "content": content,
            })
            break

        # Phase 3: EXECUTE — Run each action
        turn_results = []
        for action in actions:
            target = action.get("path", action.get("command", action.get("script", action.get("task", ""))))
            print(f"  🔧 {action['type']}: {target}"[:120], file=sys.stderr)
            result = execute_action(action)
            turn_results.append({"action": action, "result": result})
            all_actions.append(action)

            if result["status"] == "ok":
                print(f"     ✅ OK", file=sys.stderr)
            else:
                print(f"     ❌ Error: {result.get('error', 'unknown')}"[:200], file=sys.stderr)

        all_results.append({
            "turn": turn + 1,
            "phase": "execute",
            "results": turn_results,
        })

        # Phase 4: VERIFY — Check if we need another iteration
        errors = [r for r in turn_results if r["result"]["status"] != "ok"]
        if not errors:
            # All succeeded — we're done
            break

        # Build context for next iteration with errors
        execution_context = _build_error_context(turn_results)
        print(f"  🔄 {len(errors)} errors — sending back to Claude for fix", file=sys.stderr)

    else:
        print(f"  ⚠️  Max turns ({MAX_TURNS}) reached", file=sys.stderr)

    # Build final summary
    summary = _build_summary(task, all_results, all_actions)

    return {
        "status": "ok",
        "summary": summary,
        "turns": len(all_results),
        "total_input_tokens": claude.total_input_tokens,
        "total_output_tokens": claude.total_output_tokens,
        "actions": all_actions,
        "results": all_results,
        "claude_calls": claude.calls_made,
    }


def _build_error_context(turn_results: list[dict]) -> str:
    """Build context string from failed actions for Claude to fix."""
    lines = ["The following actions failed:"]
    for item in turn_results:
        action = item["action"]
        result = item["result"]
        if result["status"] != "ok":
            lines.append(f"\n- Action: {action['type']}")
            if "path" in action:
                lines.append(f"  Path: {action['path']}")
            if "command" in action:
                lines.append(f"  Command: {action['command']}")
            if "script" in action:
                lines.append(f"  Script: {action['script'][:200]}")
            if "task" in action:
                lines.append(f"  Task: {action['task'][:200]}")
            lines.append(f"  Error: {result.get('error', 'unknown')}")
            if "stdout" in result:
                lines.append(f"  Output: {result['stdout'][:500]}")
            if "stderr" in result:
                lines.append(f"  Stderr: {result['stderr'][:500]}")
    lines.append("\nPlease fix these errors and try again.")
    return "\n".join(lines)


def _build_summary(task: str, all_results: list[dict], all_actions: list[dict]) -> str:
    """Build a human-readable summary of what was done."""
    lines = [f"**Task**: {task[:200]}", ""]

    files_created = []
    files_edited = []
    commands_run = []
    applescripts_run = []
    blender_scripts_run = []
    openclaw_tasks = []
    errors = []

    for result in all_results:
        if result.get("phase") == "execute":
            for item in result.get("results", []):
                action = item["action"]
                res = item["result"]
                if action["type"] == "write_file" and res["status"] == "ok":
                    files_created.append(action["path"])
                elif action["type"] == "edit_file" and res["status"] == "ok":
                    files_edited.append(action["path"])
                elif action["type"] == "bash" and res["status"] == "ok":
                    commands_run.append(action["command"][:80])
                elif action["type"] == "applescript" and res["status"] == "ok":
                    applescripts_run.append(action["script"][:80])
                elif action["type"] == "blender_script" and res["status"] == "ok":
                    blender_scripts_run.append(action["script"][:80])
                elif action["type"] == "invoke_openclaw" and res["status"] == "ok":
                    openclaw_tasks.append(action["task"][:80])
                elif res["status"] != "ok":
                    errors.append(f"{action['type']}: {res.get('error', 'unknown')[:100]}")

    if files_created:
        lines.append("**Files created**:")
        for f in files_created:
            lines.append(f"- `{f}`")
        lines.append("")

    if files_edited:
        lines.append("**Files edited**:")
        for f in files_edited:
            lines.append(f"- `{f}`")
        lines.append("")

    if commands_run:
        lines.append("**Commands executed**:")
        for c in commands_run:
            lines.append(f"- `{c}`")
        lines.append("")

    if applescripts_run:
        lines.append("**AppleScripts executed**:")
        for s in applescripts_run:
            lines.append(f"- `{s}`")
        lines.append("")

    if blender_scripts_run:
        lines.append("**Blender scripts executed**:")
        for s in blender_scripts_run:
            lines.append(f"- `{s}`")
        lines.append("")

    if openclaw_tasks:
        lines.append("**OpenClaw tasks delegated**:")
        for t in openclaw_tasks:
            lines.append(f"- `{t}`")
        lines.append("")

    if errors:
        lines.append("**Errors**:")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    if not files_created and not files_edited and not commands_run and not applescripts_run and not blender_scripts_run and not openclaw_tasks:
        lines.append("No actions were needed. Claude provided analysis/advice.")

    return "\n".join(lines)


# ── Main Entry Point ────────────────────────────────────────────────────────

def main() -> int:
    agent_id = os.environ.get("PAPERCLIP_AGENT_ID", "")
    issue_id = os.environ.get("PAPERCLIP_ISSUE_ID", "")
    issue_title = os.environ.get("PAPERCLIP_ISSUE_TITLE", "")
    issue_description = os.environ.get("PAPERCLIP_ISSUE_DESCRIPTION", "")
    company_id = os.environ.get("PAPERCLIP_COMPANY_ID", PAPERCLIP_COMPANY_ID)
    api_url = os.environ.get("PAPERCLIP_API_URL", PAPERCLIP_API_BASE)

    if not agent_id:
        print("❌ PAPERCLIP_AGENT_ID not set. Exiting.", file=sys.stderr)
        return 1

    print(f"🤖 Hybrid Agent Runtime starting", file=sys.stderr)
    print(f"   Agent:    {agent_id}", file=sys.stderr)
    print(f"   Issue:    {issue_id}", file=sys.stderr)
    print(f"   Claude:   {CLAUDE_BIN}", file=sys.stderr)
    print(f"   macOS:    {'enabled' if MACOS_TOOLS_ENABLED else 'disabled'}", file=sys.stderr)
    print(f"   Delegation: {'enabled' if DELEGATION_TOOLS_ENABLED else 'disabled'}", file=sys.stderr)

    client = PaperclipClient(api_url, company_id)

    # Woken with no specific issue (wake-on-demand): pick up an assigned backlog
    # issue and reason on it via the agent's persona, rather than the bridge's
    # endpoint router. Processes one issue per wake; Paperclip wakes again for more.
    if not issue_id:
        print("ℹ️  No PAPERCLIP_ISSUE_ID — checking for assigned backlog issues.", file=sys.stderr)
        picked = client.next_assigned_issue(agent_id)
        if not picked:
            print("ℹ️  No pending tasks. Exiting cleanly.", file=sys.stderr)
            return 0
        issue_id = picked["id"]
        issue_title = picked.get("title", "")
        issue_description = picked.get("description", "")
        print(f"📋 Picked up assigned issue {picked.get('identifier', issue_id)} — {issue_title}", file=sys.stderr)

    # Load issue details if not provided in env
    if not issue_title or not issue_description:
        issue = client.get_issue(issue_id)
        if issue:
            issue_title = issue.get("title", issue_title)
            issue_description = issue.get("description", issue_description)
        else:
            print("❌ Could not fetch issue details", file=sys.stderr)
            return 1

    # Mark issue as in-progress
    client.update_issue(issue_id, status="in_progress")

    # Run the hybrid agent
    start = time.time()
    try:
        result = run_hybrid(agent_id, issue_id, issue_title, issue_description, client)
    except Exception as e:
        result = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}

    elapsed_ms = round((time.time() - start) * 1000, 2)

    # Update issue with result
    if result["status"] == "ok":
        status = "done"
        _clear_retry(issue_id)
        desc = (
            f"**Status**: Completed ✅\n\n"
            f"{result['summary']}\n\n"
            f"**Turns**: {result['turns']}\n\n"
            f"**Tokens**: {result['total_input_tokens']} in / {result['total_output_tokens']} out\n\n"
            f"**Claude calls**: {len(result.get('claude_calls', []))}\n\n"
            f"**Elapsed**: {elapsed_ms} ms"
        )
    else:
        # Failed — retry up to MAX_RETRIES (preserving the original brief so the
        # retry still has its instructions), then block + flag for a human.
        attempts = _bump_retry(issue_id)
        err = str(result.get("error", "no output produced"))[:200]
        if attempts >= MAX_RETRIES:
            status = "blocked"
            _clear_retry(issue_id)
            desc = ((issue_description or "") +
                    f"\n\n---\n⚠️ **Auto-retry exhausted** after {attempts} attempts — needs human "
                    f"review. Last error: {err}")
        else:
            status = "backlog"            # dispatcher will retry
            desc = issue_description or "" # PRESERVE the brief for the next attempt
        print(f"  ↻ attempt {attempts}/{MAX_RETRIES} failed → {status} ({err[:60]})", file=sys.stderr)

    client.update_issue(issue_id, status=status, description=desc)

    # Attach work products for files created
    for action in result.get("actions", []):
        if action["type"] == "write_file":
            path = _resolve_write_path(action["path"])
            client.create_work_product(
                issue_id=issue_id,
                title=f"Generated: {action['path']}",
                product_type="artifact",
                url=f"file://{path}",
                status="active",
                summary=f"Created by hybrid agent {agent_id}",
                metadata={"localPath": str(path), "language": action.get("language", "")},
            )

    # Auto-trigger the production pipeline if this run left a script in a channel's
    # production run (brief → script → finished video). Fire-and-forget; disable with
    # AUTO_PIPELINE_DISABLED=1.
    if status == "done" and os.environ.get("AUTO_PIPELINE_DISABLED") != "1":
        _maybe_trigger_pipeline()

    # Output result JSON
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
