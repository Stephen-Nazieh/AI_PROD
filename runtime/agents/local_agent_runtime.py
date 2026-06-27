#!/usr/bin/env python3
"""
local_agent_runtime.py — Local LLM Agent Runtime for Paperclip

Replaces Claude Code CLI with a local MLX-backed agent runtime.
Provides autonomous file editing, bash execution, git operations, and reasoning.
Falls back to Kimi 2.6 for complex tasks.

Invoked by Paperclip process adapter with env vars:
    PAPERCLIP_AGENT_ID, PAPERCLIP_ISSUE_ID, PAPERCLIP_ISSUE_TITLE,
    PAPERCLIP_ISSUE_DESCRIPTION, PAPERCLIP_COMPANY_ID, PAPERCLIP_API_URL
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

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except Exception:
    WEBSOCKET_AVAILABLE = False

# ── Configuration ───────────────────────────────────────────────────────────

MACOS_TOOLS_ENABLED = os.environ.get("ENABLE_MACOS_TOOLS", "0") == "1" and MACOS_TOOLS_AVAILABLE
DELEGATION_TOOLS_ENABLED = os.environ.get("ENABLE_DELEGATION_TOOLS", "0") == "1"
OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "ws://127.0.0.1:18789")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "")
CLAUDE_BIN = os.environ.get("CLAUDE_LOCAL_BIN", "/Users/nazeera/Documents/AI_PRODUCER/env/bin/claude-local")
PAPERCLIP_API_BASE = os.environ.get("PAPERCLIP_API_URL", "http://127.0.0.1:3100")
PAPERCLIP_COMPANY_ID = os.environ.get("PAPERCLIP_COMPANY_ID", "15041ee2-b1c5-43ac-b488-04934bfa1806")

# LLM endpoints
MLX_PRIMARY_URL = os.environ.get("MLX_PRIMARY_URL", "http://127.0.0.1:8000/v1")
MLX_FAST_URL = os.environ.get("MLX_FAST_URL", "http://127.0.0.1:8002/v1")
MLX_STANDARD_URL = os.environ.get("MLX_STANDARD_URL", "http://127.0.0.1:8001/v1")

# Kimi 2.6 fallback
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")

# Model names
MODEL_EXECUTIVE = "local-llama-4-scout"
MODEL_STANDARD = "local-qwen-32b"
MODEL_FAST = "local-qwen-7b"
MODEL_FALLBACK = "kimi-k2-5"

# Cost tracking (symbolic cents per 1K tokens)
COST_RATES = {
    MODEL_EXECUTIVE: 0.0,    # Local = free
    MODEL_STANDARD: 0.0,
    MODEL_FAST: 0.0,
    MODEL_FALLBACK: 2.0,      # Kimi ~$0.02 per 1K
}

# Runtime limits
MAX_TURNS = 30
MAX_OUTPUT_TOKENS = 4096

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
            "provider": "solocorn-local" if "local" in model else "moonshot",
            "model": model,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "costCents": cost_cents,
            "occurredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        self._request("POST", f"/api/companies/{self.company_id}/cost-events", payload)


# ── Agent Instruction Loader ────────────────────────────────────────────────

def load_agent_instructions(agent_id: str) -> str:
    """Load the agent's AGENTS.md instructions from Paperclip storage."""
    # Try Paperclip's instructions path first
    paperclip_path = Path.home() / ".paperclip" / "instances" / "default" / "companies" / PAPERCLIP_COMPANY_ID / "agents" / agent_id / "instructions" / "AGENTS.md"
    if paperclip_path.exists():
        return paperclip_path.read_text(encoding="utf-8")

    # Fallback: search in workspace
    for root in [WORKSPACE_ROOT / "07_PAPERCLIP", WORKSPACE_ROOT / "01_SKILLS"]:
        for path in root.rglob("AGENTS.md"):
            # Heuristic: match agent name in path
            if agent_id[:8] in str(path) or agent_id in str(path):
                return path.read_text(encoding="utf-8")

    return "# Agent Instructions\n\nNo specific instructions found."


# ── Tool Definitions ────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Use this to examine code, docs, or data.",
        "parameters": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed)", "default": 1},
            "limit": {"type": "integer", "description": "Max lines to read", "default": 200},
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates the file if it doesn't exist. Overwrites if it does.",
        "parameters": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "content": {"type": "string", "description": "Full content to write"},
        },
    },
    {
        "name": "edit_file",
        "description": "Replace a specific string in a file with another string. Use for surgical edits.",
        "parameters": {
            "path": {"type": "string", "description": "File path"},
            "old_string": {"type": "string", "description": "Exact text to replace"},
            "new_string": {"type": "string", "description": "Replacement text"},
        },
    },
    {
        "name": "list_dir",
        "description": "List files and directories in a given path.",
        "parameters": {
            "path": {"type": "string", "description": "Directory path", "default": "."},
        },
    },
    {
        "name": "bash",
        "description": "Execute a shell command. Use for git, grep, find, python scripts, etc.",
        "parameters": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory", "default": "."},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
        },
    },
    {
        "name": "git_status",
        "description": "Check git status in the workspace.",
        "parameters": {
            "cwd": {"type": "string", "description": "Repository path", "default": "."},
        },
    },
    {
        "name": "git_commit",
        "description": "Stage all changes and commit with a message.",
        "parameters": {
            "message": {"type": "string", "description": "Commit message"},
            "cwd": {"type": "string", "description": "Repository path", "default": "."},
        },
    },
    {
        "name": "search_files",
        "description": "Search for text in files using grep.",
        "parameters": {
            "pattern": {"type": "string", "description": "Search pattern"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "glob": {"type": "string", "description": "File glob pattern", "default": "*"},
        },
    },
    {
        "name": "done",
        "description": "Signal that the task is complete. Provide a final summary of what was accomplished.",
        "parameters": {
            "summary": {"type": "string", "description": "Final summary of completed work"},
        },
    },
]

# macOS automation tools (only available when ENABLE_MACOS_TOOLS=1)
MACOS_TOOLS = [
    {
        "name": "applescript",
        "description": "Execute AppleScript to control macOS applications (FCP, Logic Pro, Motion, Compressor, etc.).",
        "parameters": {
            "script": {"type": "string", "description": "AppleScript code to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
        },
    },
    {
        "name": "blender_script",
        "description": "Run a Python script in Blender headless mode using bpy.",
        "parameters": {
            "script": {"type": "string", "description": "Blender Python (bpy) script"},
            "blend_file": {"type": "string", "description": "Optional .blend file to open first", "default": ""},
            "output_path": {"type": "string", "description": "Optional render output path", "default": ""},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 600},
        },
    },
    {
        "name": "fcp_import",
        "description": "Import an FCPXML file into Final Cut Pro.",
        "parameters": {
            "xml_path": {"type": "string", "description": "Path to the FCPXML file"},
        },
    },
    {
        "name": "logic_bounce",
        "description": "Bounce the current Logic Pro project to audio.",
        "parameters": {
            "output_path": {"type": "string", "description": "Destination audio file path"},
            "format": {"type": "string", "description": "WAV, AIFF, or MP3", "default": "WAV"},
            "sample_rate": {"type": "integer", "description": "e.g. 44100, 48000", "default": 48000},
            "bit_depth": {"type": "integer", "description": "e.g. 16, 24", "default": 24},
        },
    },
    {
        "name": "motion_render",
        "description": "Render a Motion project to video.",
        "parameters": {
            "project_path": {"type": "string", "description": "Path to Motion project"},
            "output_path": {"type": "string", "description": "Destination video path"},
        },
    },
    {
        "name": "compressor_submit",
        "description": "Submit a job to Compressor.",
        "parameters": {
            "job_path": {"type": "string", "description": "Path to source media or batch file"},
        },
    },
    {
        "name": "ffmpeg",
        "description": "Run an FFmpeg command.",
        "parameters": {
            "args": {"type": "array", "description": "FFmpeg argument list (without 'ffmpeg' prefix)"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 300},
        },
    },
]

# Delegation tools (only available when ENABLE_DELEGATION_TOOLS=1)
DELEGATION_TOOLS = [
    {
        "name": "invoke_claude",
        "description": "Delegate a complex coding subtask to Claude Code CLI. Use sparingly to avoid recursion.",
        "parameters": {
            "prompt": {"type": "string", "description": "Task prompt for Claude"},
            "max_tokens": {"type": "integer", "description": "Max tokens", "default": 4096},
        },
    },
    {
        "name": "invoke_openclaw",
        "description": "Delegate a task to OpenClaw daemon (web browsing, WhatsApp, external APIs).",
        "parameters": {
            "task": {"type": "string", "description": "Task description for OpenClaw"},
        },
    },
]

# Combine all tools
if MACOS_TOOLS_ENABLED:
    TOOLS = TOOLS + MACOS_TOOLS
if DELEGATION_TOOLS_ENABLED:
    TOOLS = TOOLS + DELEGATION_TOOLS


def format_tools() -> str:
    """Format tool definitions for the system prompt."""
    lines = ["Available tools:"]
    for tool in TOOLS:
        lines.append(f"\n### {tool['name']}")
        lines.append(f"Description: {tool['description']}")
        lines.append("Parameters:")
        for param_name, param_info in tool["parameters"].items():
            default = f" (default: {param_info.get('default')})" if "default" in param_info else ""
            lines.append(f"  - {param_name}: {param_info['description']}{default}")
    lines.append("\n---")
    lines.append("When you need to use a tool, output ONLY a JSON object in this exact format:")
    lines.append('{"tool": "tool_name", "arguments": {"param": "value"}}')
    lines.append("The system will execute the tool and return the result to you.")
    lines.append('When the task is fully complete, output ONLY: {"tool": "done", "arguments": {"summary": "Your final summary here"}}')
    return "\n".join(lines)


# ── Tool Execution Engine ───────────────────────────────────────────────────

def execute_tool(tool_name: str, arguments: dict) -> dict:
    """Execute a tool and return the result."""
    try:
        if tool_name == "read_file":
            return _tool_read_file(**arguments)
        elif tool_name == "write_file":
            return _tool_write_file(**arguments)
        elif tool_name == "edit_file":
            return _tool_edit_file(**arguments)
        elif tool_name == "list_dir":
            return _tool_list_dir(**arguments)
        elif tool_name == "bash":
            return _tool_bash(**arguments)
        elif tool_name == "git_status":
            return _tool_git_status(**arguments)
        elif tool_name == "git_commit":
            return _tool_git_commit(**arguments)
        elif tool_name == "search_files":
            return _tool_search_files(**arguments)
        elif tool_name == "done":
            return {"status": "done", "summary": arguments.get("summary", "")}
        elif tool_name == "applescript":
            return _tool_applescript(**arguments)
        elif tool_name == "blender_script":
            return _tool_blender_script(**arguments)
        elif tool_name == "fcp_import":
            return _tool_fcp_import(**arguments)
        elif tool_name == "logic_bounce":
            return _tool_logic_bounce(**arguments)
        elif tool_name == "motion_render":
            return _tool_motion_render(**arguments)
        elif tool_name == "compressor_submit":
            return _tool_compressor_submit(**arguments)
        elif tool_name == "ffmpeg":
            return _tool_ffmpeg(**arguments)
        elif tool_name == "invoke_claude":
            return _tool_invoke_claude(**arguments)
        elif tool_name == "invoke_openclaw":
            return _tool_invoke_openclaw(**arguments)
        else:
            return {"status": "error", "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    return p.resolve()


def _tool_read_file(path: str, offset: int = 1, limit: int = 200) -> dict:
    p = _resolve_path(path)
    if not p.exists():
        return {"status": "error", "error": f"File not found: {p}"}
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        total = len(lines)
        start = max(0, offset - 1)
        end = min(total, start + limit)
        selected = lines[start:end]
        result_lines = []
        for i, line in enumerate(selected, start=start + 1):
            result_lines.append(f"{i:4d} | {line}")
        return {
            "status": "ok",
            "path": str(p),
            "total_lines": total,
            "shown_lines": f"{start + 1}-{end}",
            "content": "\n".join(result_lines),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _tool_write_file(path: str, content: str) -> dict:
    p = _resolve_path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"status": "ok", "path": str(p), "bytes_written": len(content.encode("utf-8"))}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _tool_edit_file(path: str, old_string: str, new_string: str) -> dict:
    p = _resolve_path(path)
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


def _tool_list_dir(path: str = ".") -> dict:
    p = _resolve_path(path)
    try:
        entries = []
        for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            entries.append(f"{'[DIR] ' if entry.is_dir() else '      '}{entry.name}")
        return {"status": "ok", "path": str(p), "entries": entries}
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
            "stdout": result.stdout[:5000],  # Truncate large outputs
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _tool_git_status(cwd: str = ".") -> dict:
    return _tool_bash("git status --short", cwd=cwd)


def _tool_git_commit(message: str, cwd: str = ".") -> dict:
    add_result = _tool_bash("git add -A", cwd=cwd)
    if add_result.get("status") != "ok":
        return add_result
    commit_result = _tool_bash(f"git commit -m {json.dumps(message)}", cwd=cwd)
    return commit_result


def _tool_search_files(pattern: str, path: str = ".", glob: str = "*") -> dict:
    try:
        working_dir = _resolve_path(path)
        result = subprocess.run(
            ["grep", "-rn", "--include", glob, pattern, str(working_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = result.stdout.strip().splitlines()[:50]  # Limit results
        return {
            "status": "ok",
            "matches": len(lines),
            "results": lines,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── macOS Automation Tools ──────────────────────────────────────────────────

def _tool_applescript(script: str, timeout: int = 60) -> dict:
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = run_applescript(script, timeout=timeout)
    return {
        "status": result.get("status", "error"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


def _tool_blender_script(script: str, blend_file: str = "", output_path: str = "", timeout: int = 600) -> dict:
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = blender_headless(script, blend_file=blend_file or None, output_path=output_path or None, timeout=timeout)
    return {
        "status": result.get("status", "error"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


def _tool_fcp_import(xml_path: str) -> dict:
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = fcp_import_xml(xml_path)
    return {
        "status": result.get("status", "error"),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


def _tool_logic_bounce(output_path: str, format: str = "WAV", sample_rate: int = 48000, bit_depth: int = 24) -> dict:
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = logic_pro_bounce(output_path, format=format, sample_rate=sample_rate, bit_depth=bit_depth)
    return {
        "status": result.get("status", "error"),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


def _tool_motion_render(project_path: str, output_path: str) -> dict:
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = motion_render(project_path, output_path)
    return {
        "status": result.get("status", "error"),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


def _tool_compressor_submit(job_path: str) -> dict:
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = compressor_submit(job_path)
    return {
        "status": result.get("status", "error"),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


def _tool_ffmpeg(args: list, timeout: int = 300) -> dict:
    if not MACOS_TOOLS_ENABLED:
        return {"status": "error", "error": "macOS tools are not enabled. Set ENABLE_MACOS_TOOLS=1"}
    result = ffmpeg_command(args, timeout=timeout)
    return {
        "status": result.get("status", "error"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "message": result.get("message", ""),
        "data": result.get("data"),
    }


# ── Delegation Tools ────────────────────────────────────────────────────────

_claude_invocation_depth = 0
_MAX_CLAUDE_DEPTH = 2


def _tool_invoke_claude(prompt: str, max_tokens: int = 4096) -> dict:
    """Delegate a subtask to Claude Code CLI. Tracks recursion depth to prevent loops."""
    global _claude_invocation_depth
    if not DELEGATION_TOOLS_ENABLED:
        return {"status": "error", "error": "Delegation tools are not enabled. Set ENABLE_DELEGATION_TOOLS=1"}

    if _claude_invocation_depth >= _MAX_CLAUDE_DEPTH:
        return {"status": "error", "error": f"Max Claude delegation depth ({_MAX_CLAUDE_DEPTH}) reached. Refusing recursive call."}

    _claude_invocation_depth += 1
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "--bare", "--print", prompt],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(WORKSPACE_ROOT),
        )
        _claude_invocation_depth -= 1
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "message": "Claude delegation completed" if result.returncode == 0 else f"Claude failed: {result.stderr[:300]}",
        }
    except subprocess.TimeoutExpired:
        _claude_invocation_depth -= 1
        return {"status": "error", "error": "Claude delegation timed out after 300s"}
    except Exception as e:
        _claude_invocation_depth -= 1
        return {"status": "error", "error": f"Claude delegation error: {e}"}


def _tool_invoke_openclaw(task: str) -> dict:
    """Delegate a task to the OpenClaw daemon via WebSocket."""
    if not DELEGATION_TOOLS_ENABLED:
        return {"status": "error", "error": "Delegation tools are not enabled. Set ENABLE_DELEGATION_TOOLS=1"}
    if not WEBSOCKET_AVAILABLE:
        return {"status": "error", "error": "websocket-client library not available. Run: pip install websocket-client"}

    try:
        ws = websocket.create_connection(OPENCLAW_URL, timeout=30)
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


# ── LLM Client ──────────────────────────────────────────────────────────────

class LLMClient:
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_cents = 0
        self.calls_made = []
        self._model_cache = {}  # base_url -> model_name

    def _get_model_name(self, base_url: str) -> str | None:
        """Query the MLX server for its model name."""
        if base_url in self._model_cache:
            return self._model_cache[base_url]
        try:
            url = base_url.rstrip("/") + "/models"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            # Pick the model that matches this endpoint's expected model
            expected_map = {
                MLX_PRIMARY_URL: "Scout",
                MLX_STANDARD_URL: "32B",
                MLX_FAST_URL: "7B",
            }
            expected = expected_map.get(base_url)
            if expected:
                for m in models:
                    name = m.get("id", "")
                    if expected in name:
                        self._model_cache[base_url] = name
                        return name
            # Fallback: first model
            if models:
                name = models[0].get("id", "")
                self._model_cache[base_url] = name
                return name
        except Exception:
            pass
        return None

    def call(self, messages: list[dict], model: str = MODEL_STANDARD, max_tokens: int = MAX_OUTPUT_TOKENS) -> dict:
        """Call an LLM and return the response."""
        start = time.time()

        if "local" in model:
            return self._call_local(messages, model, max_tokens, start)
        else:
            return self._call_kimi(messages, model, max_tokens, start)

    def _call_local(self, messages: list[dict], model: str, max_tokens: int, start: float) -> dict:
        """Call local MLX server via OpenAI-compatible API."""
        # Map model name to endpoint
        if "scout" in model or "executive" in model:
            base_url = MLX_PRIMARY_URL
        elif "32b" in model or "standard" in model:
            base_url = MLX_STANDARD_URL
        else:
            base_url = MLX_FAST_URL

        # Query the server for its actual model name
        actual_model = self._get_model_name(base_url)
        if not actual_model:
            actual_model = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"  # fallback

        url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": actual_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            input_toks = usage.get("prompt_tokens", 0)
            output_toks = usage.get("completion_tokens", 0)

            self.total_input_tokens += input_toks
            self.total_output_tokens += output_toks
            self.calls_made.append({"model": model, "input": input_toks, "output": output_toks, "elapsed": time.time() - start})

            return {
                "status": "ok",
                "content": content,
                "model": model,
                "input_tokens": input_toks,
                "output_tokens": output_toks,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "model": model}

    def _call_kimi(self, messages: list[dict], model: str, max_tokens: int, start: float) -> dict:
        """Call Kimi 2.6 API as fallback."""
        if not KIMI_API_KEY:
            return {"status": "error", "error": "KIMI_API_KEY not set"}

        url = KIMI_BASE_URL.rstrip("/") + "/chat/completions"
        payload = {
            "model": "kimi-k2-5",  # Kimi 2.6 latest model name
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {KIMI_API_KEY}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            input_toks = usage.get("prompt_tokens", 0)
            output_toks = usage.get("completion_tokens", 0)

            # Cost: $0.02 per 1K tokens = 2 cents per 1K
            cost = ((input_toks + output_toks) / 1000) * COST_RATES[MODEL_FALLBACK]
            self.total_cost_cents += cost
            self.total_input_tokens += input_toks
            self.total_output_tokens += output_toks
            self.calls_made.append({"model": MODEL_FALLBACK, "input": input_toks, "output": output_toks, "cost": cost, "elapsed": time.time() - start})

            return {
                "status": "ok",
                "content": content,
                "model": MODEL_FALLBACK,
                "input_tokens": input_toks,
                "output_tokens": output_toks,
                "cost_cents": cost,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "model": MODEL_FALLBACK}


# ── ReAct Agent Loop ────────────────────────────────────────────────────────

def run_agent(agent_id: str, issue_id: str, issue_title: str, issue_description: str,
              instructions: str, client: PaperclipClient) -> dict:
    """Run the ReAct loop: reason, act (tool), observe, repeat."""

    llm = LLMClient()

    # Decide which model to use based on task complexity
    complexity = assess_complexity(issue_title + " " + issue_description)
    if complexity == "executive":
        model = MODEL_EXECUTIVE
    elif complexity == "standard":
        model = MODEL_STANDARD
    else:
        model = MODEL_FAST

    print(f"🧠 Task complexity: {complexity} → using {model}", file=sys.stderr)

    # Build system prompt
    extra_instructions = ""
    if MACOS_TOOLS_ENABLED:
        extra_instructions += (
            "\nmacOS automation tools are ENABLED. You can control Final Cut Pro, Logic Pro, Motion, "
            "Compressor, and Blender directly via AppleScript. Use these for media production tasks.\n"
        )
    if DELEGATION_TOOLS_ENABLED:
        extra_instructions += (
            "\nDelegation tools are ENABLED. You can invoke_claude for complex coding subtasks "
            "(max 2 levels deep) and invoke_openclaw for web browsing or external APIs.\n"
        )

    system_prompt = f"""You are an autonomous agent running locally on Apple Silicon (M5 Max, 128GB RAM).
Your identity and instructions:

{instructions}

{format_tools()}
{extra_instructions}
Rules:
1. You have access to the full workspace at {WORKSPACE_ROOT}
2. Use tools to explore, read, write, and execute commands
3. Make progress incrementally — read files before editing them
4. Use bash for git operations, searches, and running scripts
5. Always verify your work by reading files back after editing
6. When complete, use the 'done' tool with a clear summary
7. Be concise but thorough
8. You have a {MAX_TURNS} turn budget — use them wisely
9. IMPORTANT: If you get an error from a tool, do NOT retry the same exact action. Try a different approach.
10. IMPORTANT: After getting tool results, analyze them and decide on the NEXT step. Do NOT repeat the same tool call.
11. If a task is simple (listing files, checking status), complete it in 1-2 turns and use 'done'.
12. CRITICAL: You MUST use the 'done' tool to finish. Simply describing completion is NOT enough.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Issue: {issue_title}\n\nDescription:\n{issue_description}"},
    ]

    tool_results = []
    final_summary = ""

    for turn in range(MAX_TURNS):
        print(f"  Turn {turn + 1}/{MAX_TURNS}", file=sys.stderr)

        # Call LLM
        response = llm.call(messages, model=model)

        if response["status"] != "ok":
            # Try fallback
            print(f"  ⚠️  Primary model failed: {response.get('error')}. Trying fallback...", file=sys.stderr)
            response = llm.call(messages, model=MODEL_FALLBACK)
            if response["status"] != "ok":
                return {"status": "error", "error": f"All models failed: {response.get('error')}"}

        content = response["content"]

        # Parse tool call
        tool_call = parse_tool_call(content)

        if not tool_call:
            # No tool call — just add to conversation and continue
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": "Please use a tool to make progress on the task, or use the 'done' tool if complete."})
            continue

        tool_name = tool_call["tool"]
        arguments = tool_call["arguments"]

        print(f"  🔧 Tool: {tool_name}({json.dumps(arguments)})"[:200], file=sys.stderr)

        if tool_name == "done":
            final_summary = arguments.get("summary", "Task completed.")
            break

        # Execute tool
        result = execute_tool(tool_name, arguments)
        tool_results.append({"tool": tool_name, "args": arguments, "result": result})

        # Detect loops
        if detect_loop(tool_results):
            print(f"  🔄 Loop detected! Stopping early.", file=sys.stderr)
            final_summary = generate_fallback_summary(tool_results, issue_title)
            break

        # Add to conversation
        messages.append({"role": "assistant", "content": content})

        result_text = json.dumps(result, indent=2, ensure_ascii=False)
        if len(result_text) > 3000:
            result_text = result_text[:3000] + "\n... [truncated]"
        messages.append({"role": "user", "content": f"Tool result ({tool_name}):\n{result_text}"})

    else:
        # Max turns reached — generate best-effort summary from tool results
        final_summary = generate_fallback_summary(tool_results, issue_title)
        print(f"  ⚠️  Max turns reached. Fallback summary generated.", file=sys.stderr)

    # Report costs
    total_cost = int(round(llm.total_cost_cents))
    client.report_cost(
        agent_id=agent_id,
        cost_cents=total_cost,
        input_tokens=llm.total_input_tokens,
        output_tokens=llm.total_output_tokens,
        model=model,
        issue_id=issue_id,
    )

    return {
        "status": "ok",
        "summary": final_summary,
        "turns": len(tool_results) + 1,
        "model_used": model,
        "total_input_tokens": llm.total_input_tokens,
        "total_output_tokens": llm.total_output_tokens,
        "total_cost_cents": total_cost,
        "tool_results": tool_results,
        "llm_calls": llm.calls_made,
    }


def assess_complexity(text: str) -> str:
    """Assess task complexity to select the right model."""
    text_lower = text.lower()

    executive_keywords = [
        "strategy", "quarterly", "roadmap", "budget", "executive",
        "ceo", "cto", "cfo", "director", "vision", "mission", "prioritize",
        "stakeholder", "partnership", "investor", "board", "forecast",
    ]

    simple_keywords = [
        "search", "find", "lookup", "query", "check", "status", "list",
        "read", "show", "display", "count", "summarize", "brief",
    ]

    if any(kw in text_lower for kw in executive_keywords):
        return "executive"
    if any(kw in text_lower for kw in simple_keywords):
        return "fast"
    return "standard"


def detect_loop(tool_history: list[dict]) -> bool:
    """Detect if the agent is stuck in a loop (same tool+args repeated)."""
    if len(tool_history) < 4:
        return False
    # Check last 4 tool calls
    last4 = tool_history[-4:]
    signatures = [json.dumps({"t": t["tool"], "a": t["args"]}, sort_keys=True) for t in last4]
    # If same signature appears 3+ times in last 4, it's a loop
    from collections import Counter
    counts = Counter(signatures)
    return any(c >= 3 for c in counts.values())


def generate_fallback_summary(tool_results: list[dict], issue_title: str) -> str:
    """Generate a summary from tool results when max turns reached."""
    lines = [f"Task: {issue_title}", "", "Actions taken:"]
    for tr in tool_results:
        tool = tr["tool"]
        result = tr["result"]
        if result.get("status") == "ok":
            if tool == "list_dir":
                entries = result.get("entries", [])
                lines.append(f"- Listed {len(entries)} items in {result.get('path', '?')}")
            elif tool == "read_file":
                lines.append(f"- Read file {result.get('path', '?')} ({result.get('shown_lines', '?')} lines)")
            elif tool == "write_file":
                lines.append(f"- Created file {result.get('path', '?')} ({result.get('bytes_written', 0)} bytes)")
            elif tool == "edit_file":
                lines.append(f"- Edited file {result.get('path', '?')}")
            elif tool == "bash":
                cmd = result.get("command", "?")[:60]
                lines.append(f"- Ran command: {cmd}")
            elif tool == "git_status":
                stdout = result.get("stdout", "")
                lines.append(f"- Git status: {stdout[:100]}")
            elif tool == "search_files":
                lines.append(f"- Found {result.get('matches', 0)} matches")
            elif tool == "applescript":
                lines.append(f"- Executed AppleScript")
            elif tool == "blender_script":
                lines.append(f"- Ran Blender Python script")
            elif tool == "fcp_import":
                lines.append(f"- Imported FCPXML: {result.get('data', {}).get('xml_path', '?')}")
            elif tool == "logic_bounce":
                lines.append(f"- Bounced Logic Pro to: {result.get('data', {}).get('output_path', '?')}")
            elif tool == "motion_render":
                lines.append(f"- Rendered Motion project to: {result.get('data', {}).get('output_path', '?')}")
            elif tool == "compressor_submit":
                lines.append(f"- Submitted Compressor job: {result.get('data', {}).get('job_path', '?')}")
            elif tool == "ffmpeg":
                lines.append(f"- Ran FFmpeg command")
            elif tool == "invoke_claude":
                lines.append(f"- Delegated subtask to Claude")
            elif tool == "invoke_openclaw":
                lines.append(f"- Delegated subtask to OpenClaw")
            else:
                lines.append(f"- Executed {tool}")
        else:
            lines.append(f"- {tool} failed: {result.get('error', 'unknown')}")
    lines.append("")
    lines.append("Note: Task reached the maximum number of turns. Review the actions above.")
    return "\n".join(lines)


def parse_tool_call(content: str) -> dict | None:
    """Parse a tool call from the model's response."""
    # Look for JSON object in the content
    # The model should output: {"tool": "name", "arguments": {...}}

    # Try to find JSON blocks
    patterns = [
        r'\{[\s\S]*?"tool"\s*:\s*"[^"]+"[\s\S]*?"arguments"[\s\S]*?\}',
        r'```json\s*([\s\S]*?)```',
        r'```\s*([\s\S]*?)```',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            try:
                # If the pattern captured the inner content (for code blocks)
                candidate = match if match.strip().startswith("{") else content[content.find(match):content.find(match) + len(match)]
                # Find the outermost JSON object
                start = candidate.find("{")
                end = candidate.rfind("}")
                if start >= 0 and end > start:
                    parsed = json.loads(candidate[start:end+1])
                    if "tool" in parsed and "arguments" in parsed:
                        return parsed
            except (json.JSONDecodeError, ValueError):
                continue

    # Fallback: try to parse the entire content as JSON
    try:
        parsed = json.loads(content.strip())
        if "tool" in parsed and "arguments" in parsed:
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    return None


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

    print(f"🤖 Local Agent Runtime starting", file=sys.stderr)
    print(f"   Agent:    {agent_id}", file=sys.stderr)
    print(f"   Issue:    {issue_id}", file=sys.stderr)
    print(f"   API:      {api_url}", file=sys.stderr)
    print(f"   macOS:    {'enabled' if MACOS_TOOLS_ENABLED else 'disabled'}", file=sys.stderr)
    print(f"   Delegation: {'enabled' if DELEGATION_TOOLS_ENABLED else 'disabled'}", file=sys.stderr)

    client = PaperclipClient(api_url, company_id)

    # Woken with no specific issue (wake-on-demand): pick up an assigned backlog
    # issue and reason on it via the agent's instructions, rather than the bridge's
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

    # Load agent instructions
    instructions = load_agent_instructions(agent_id)
    print(f"📋 Instructions loaded: {len(instructions)} chars", file=sys.stderr)

    # Mark issue as in-progress
    client.update_issue(issue_id, status="in_progress")

    # Run the agent
    start = time.time()
    try:
        result = run_agent(agent_id, issue_id, issue_title, issue_description, instructions, client)
    except Exception as e:
        result = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}

    elapsed_ms = round((time.time() - start) * 1000, 2)

    # Update issue with result
    if result["status"] == "ok":
        status = "done"
        desc = (
            f"**Status**: Completed ✅\n\n"
            f"**Summary**: {result['summary']}\n\n"
            f"**Model**: {result['model_used']}\n\n"
            f"**Turns**: {result['turns']}\n\n"
            f"**Tokens**: {result['total_input_tokens']} in / {result['total_output_tokens']} out\n\n"
            f"**Cost**: {result['total_cost_cents']} cents\n\n"
            f"**Elapsed**: {elapsed_ms} ms"
        )
    else:
        status = "backlog"
        desc = (
            f"**Status**: Failed ❌\n\n"
            f"**Error**: {result.get('error', 'Unknown error')}\n\n"
            f"**Elapsed**: {elapsed_ms} ms"
        )

    client.update_issue(issue_id, status=status, description=desc)

    # Attach work products if files were created
    for tr in result.get("tool_results", []):
        if tr["tool"] == "write_file" and tr["result"].get("status") == "ok":
            path = tr["result"].get("path", "")
            client.create_work_product(
                issue_id=issue_id,
                title=f"Generated File",
                product_type="artifact",
                url=f"file://{path}",
                status="active",
                summary=f"Created by {agent_id}",
                metadata={"localPath": path, "tool": "write_file"},
            )

    # Output result JSON for Paperclip capture
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
