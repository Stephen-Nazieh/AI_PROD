#!/usr/bin/env python3
"""
macos_automation.py — macOS App Automation Toolkit for Paperclip Agents

Provides structured wrappers around AppleScript, JXA (JavaScript for Automation),
and CLI tools to control macOS applications programmatically.

Apps supported:
  - Final Cut Pro (FCPXML import, limited live control)
  - Logic Pro (project open, bounce, export)
  - MainStage (concert open, patch control)
  - Motion (render via AppleScript or CLI)
  - Compressor (job submission)
  - DaVinci Resolve Studio (render, project export)
  - Adobe After Effects 2026 (aerender CLI, render queue)
  - VRoid Studio (VRM export)
  - Blender (headless Python scripting)
  - Any AppleScript-scriptable app via generic helpers

All functions return a structured dict:
  {
    "status": "ok" | "error" | "degraded",
    "stdout": str,
    "stderr": str,
    "exit_code": int,
    "message": str,       # human-readable summary
    "data": dict | None,  # app-specific structured output
  }

Env vars:
  ENABLE_MACOS_TOOLS=1  — required for tools to be active (safety gate)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path("/Users/nazeera/Documents/AI_PRODUCER")

# ── Safety gate ─────────────────────────────────────────────────────────────

MACOS_TOOLS_ENABLED = os.environ.get("ENABLE_MACOS_TOOLS", "0") == "1"


def _require_enabled() -> dict | None:
    """Return error dict if macOS tools are not enabled."""
    if not MACOS_TOOLS_ENABLED:
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "message": "macOS automation tools are disabled. Set ENABLE_MACOS_TOOLS=1 to enable.",
            "data": None,
        }
    return None


# ── Low-level script runners ────────────────────────────────────────────────

def _run_subprocess(cmd: list[str], input_text: str = "", timeout: int = 60,
                    cwd: Path = WORKSPACE_ROOT) -> dict:
    """Run a subprocess and return a structured result."""
    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "message": f"Command exited with code {result.returncode}",
            "data": None,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "status": "error",
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "exit_code": -1,
            "message": f"Command timed out after {timeout}s",
            "data": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "message": f"Subprocess error: {e}",
            "data": None,
        }


def run_applescript(script: str, timeout: int = 60) -> dict:
    """Execute an AppleScript string via osascript."""
    err = _require_enabled()
    if err:
        return err
    result = _run_subprocess(["osascript", "-e", script], timeout=timeout)
    result["message"] = "AppleScript execution complete" if result["status"] == "ok" else f"AppleScript failed: {result['stderr'][:200]}"
    return result


def run_javascript(script: str, timeout: int = 60) -> dict:
    """Execute a JavaScript for Automation (JXA) string via osascript."""
    err = _require_enabled()
    if err:
        return err
    result = _run_subprocess(["osascript", "-l", "JavaScript", "-e", script], timeout=timeout)
    result["message"] = "JXA execution complete" if result["status"] == "ok" else f"JXA failed: {result['stderr'][:200]}"
    return result


def tell_app(app_name: str, command: str, timeout: int = 60) -> dict:
    """Wrap a command in an AppleScript 'tell application' block."""
    script = f'tell application "{app_name}"\n{command}\nend tell'
    return run_applescript(script, timeout=timeout)


def get_running_apps(timeout: int = 30) -> dict:
    """List currently running applications via AppleScript."""
    err = _require_enabled()
    if err:
        return err
    script = 'tell application "System Events" to get name of every application process whose background only is false'
    result = run_applescript(script, timeout=timeout)
    if result["status"] == "ok":
        apps = [a.strip() for a in result["stdout"].split(",")]
        result["data"] = {"apps": apps, "count": len(apps)}
        result["message"] = f"Found {len(apps)} running apps"
    return result


def is_app_running(app_name: str) -> dict:
    """Check if a specific application is currently running."""
    err = _require_enabled()
    if err:
        return err
    script = f'tell application "System Events" to (name of processes) contains "{app_name}"'
    result = run_applescript(script, timeout=15)
    if result["status"] == "ok":
        running = result["stdout"].strip().lower() == "true"
        result["data"] = {"running": running}
        result["message"] = f"{app_name} is {'running' if running else 'not running'}"
    return result


def activate_app(app_name: str) -> dict:
    """Activate (bring to front) an application."""
    err = _require_enabled()
    if err:
        return err
    return tell_app(app_name, "activate", timeout=15)


# ── Blender ─────────────────────────────────────────────────────────────────

def _find_blender_binary() -> str:
    """Find the Blender binary, preferring the full .app bundle over bare CLI."""
    candidates = [
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/Applications/Blender.app/Contents/MacOS/blender",
        "/usr/local/bin/blender",
        "/opt/homebrew/bin/blender",
        "blender",
    ]
    for c in candidates:
        import shutil
        if shutil.which(c) or Path(c).exists():
            return c
    return "blender"


def blender_headless(script: str, blend_file: str | None = None,
                     output_path: str | None = None, timeout: int = 600) -> dict:
    """
    Run a Python script in Blender headless mode.

    Args:
        script: Python code to execute inside Blender's bpy context.
        blend_file: Optional .blend file to open first.
        output_path: Optional render output path (sets bpy.context.scene.render.filepath).
        timeout: Max seconds to wait (renders can take a while).
    """
    err = _require_enabled()
    if err:
        return err

    blender_bin = _find_blender_binary()
    cmd = [blender_bin, "--background"]
    if blend_file:
        cmd.append(blend_file)

    # Write script to a temp file (Blender doesn't support --python - for stdin)
    import tempfile
    full_script = script
    if output_path:
        full_script = f'import bpy\nbpy.context.scene.render.filepath = {json.dumps(output_path)}\n' + script

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(full_script)
        script_path = f.name

    cmd.extend(["--python", script_path])

    result = _run_subprocess(cmd, timeout=timeout)

    # Clean up temp file
    try:
        Path(script_path).unlink()
    except Exception:
        pass
    result["message"] = (
        "Blender render complete" if result["status"] == "ok"
        else f"Blender failed: {result['stderr'][:300]}"
    )
    if result["status"] == "ok":
        result["data"] = {"blend_file": blend_file, "output_path": output_path}
    return result


# ── Final Cut Pro ───────────────────────────────────────────────────────────

def fcp_import_xml(xml_path: str, timeout: int = 60) -> dict:
    """
    Tell Final Cut Pro to import an FCPXML file.

    Note: Final Cut Pro's AppleScript support is limited. This may require
    FCP to already be running. If FCP is not scriptable for import, this
    degrades to generating instructions for manual import.
    """
    err = _require_enabled()
    if err:
        return err

    p = Path(xml_path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    p = p.resolve()

    if not p.exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"File not found: {p}",
            "exit_code": -1,
            "message": f"FCPXML not found: {p}",
            "data": None,
        }

    # Try AppleScript first
    script = f'tell application "Final Cut Pro"\nactivate\nopen POSIX file {json.dumps(str(p))}\nend tell'
    result = run_applescript(script, timeout=timeout)

    if result["status"] == "ok":
        result["message"] = f"FCP imported {p.name}"
        result["data"] = {"xml_path": str(p), "method": "applescript"}
        return result

    # Degraded: FCP may not be scriptable for import on this system
    result["status"] = "degraded"
    result["message"] = (
        f"Could not auto-import into FCP. Please manually import: {p}\n"
        "Open Final Cut Pro → File → Import → XML → select the file above."
    )
    result["data"] = {"xml_path": str(p), "method": "manual_instructions"}
    return result


def fcp_export_xml(project_name: str, output_path: str, timeout: int = 60) -> dict:
    """
    Tell Final Cut Pro to export the current project as FCPXML.

    Note: This is experimental and depends on FCP's AppleScript dictionary.
    """
    err = _require_enabled()
    if err:
        return err

    p = Path(output_path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    p = p.resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    script = (
        f'tell application "Final Cut Pro"\n'
        f'activate\n'
        f'set xmlPath to POSIX file {json.dumps(str(p))}\n'
        f'export active project to xmlPath using FCPXML\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)
    result["message"] = (
        f"FCP exported to {p.name}" if result["status"] == "ok"
        else f"FCP export failed (may not be scriptable): {result['stderr'][:200]}"
    )
    if result["status"] == "ok":
        result["data"] = {"output_path": str(p)}
    return result


# ── Logic Pro ───────────────────────────────────────────────────────────────

def logic_pro_open(project_path: str, timeout: int = 60) -> dict:
    """Open a Logic Pro project file (.logicx)."""
    err = _require_enabled()
    if err:
        return err

    p = Path(project_path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    p = p.resolve()

    if not p.exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Project not found: {p}",
            "exit_code": -1,
            "message": f"Logic Pro project not found: {p}",
            "data": None,
        }

    return tell_app("Logic Pro", f"open POSIX file {json.dumps(str(p))}", timeout=timeout)


def logic_pro_bounce(output_path: str, format: str = "WAV", sample_rate: int = 48000,
                     bit_depth: int = 24, timeout: int = 300) -> dict:
    """
    Bounce the current Logic Pro project to audio.

    Args:
        output_path: Destination audio file path.
        format: "WAV", "AIFF", or "MP3".
        sample_rate: e.g. 44100, 48000.
        bit_depth: e.g. 16, 24.
        timeout: Max seconds (bouncing can take a while).

    Note: Logic Pro's AppleScript bounce syntax varies by version.
    This attempts the most common syntax and degrades gracefully.
    """
    err = _require_enabled()
    if err:
        return err

    p = Path(output_path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    p = p.resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    # Try the modern AppleScript bounce syntax first
    script = (
        f'tell application "Logic Pro"\n'
        f'activate\n'
        f'set bounceFile to POSIX file {json.dumps(str(p))}\n'
        f'bounce project at bounceFile with properties '
        f'{{file type:{format}, sample rate:{sample_rate}, bit depth:{bit_depth}, surr render mode:off}}\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)

    if result["status"] == "ok":
        result["message"] = f"Logic Pro bounced to {p.name}"
        result["data"] = {"output_path": str(p), "format": format}
        return result

    # Fallback: try alternative syntax
    script_alt = (
        f'tell application "Logic Pro"\n'
        f'activate\n'
        f'export project to POSIX file {json.dumps(str(p))} as {format}\n'
        f'end tell'
    )
    result = run_applescript(script_alt, timeout=timeout)

    if result["status"] == "ok":
        result["message"] = f"Logic Pro exported to {p.name} (alternative syntax)"
        result["data"] = {"output_path": str(p), "format": format, "method": "alternative"}
        return result

    # Degraded: provide manual instructions
    result["status"] = "degraded"
    result["message"] = (
        f"Could not auto-bounce from Logic Pro. Manual steps:\n"
        f"1. Open Logic Pro\n"
        f"2. File → Bounce → Project or Section\n"
        f"3. Set format: {format}, sample rate: {sample_rate}, bit depth: {bit_depth}\n"
        f"4. Save to: {p}"
    )
    result["data"] = {"output_path": str(p), "format": format, "method": "manual_instructions"}
    return result


def logic_pro_close(save: bool = True, timeout: int = 30) -> dict:
    """Close the current Logic Pro project."""
    err = _require_enabled()
    if err:
        return err
    cmd = "close front project saving yes" if save else "close front project saving no"
    return tell_app("Logic Pro", cmd, timeout=timeout)


# ── Motion ──────────────────────────────────────────────────────────────────

def motion_render(project_path: str, output_path: str, timeout: int = 600) -> dict:
    """
    Render a Motion project to video.

    Strategy:
      1. Try AppleScript to tell Motion to open and export.
      2. If that fails, try the `motion` CLI tool.
      3. If both fail, degrade to manual instructions.
    """
    err = _require_enabled()
    if err:
        return err

    pp = Path(project_path)
    op = Path(output_path)
    if not pp.is_absolute():
        pp = WORKSPACE_ROOT / pp
    if not op.is_absolute():
        op = WORKSPACE_ROOT / op
    pp = pp.resolve()
    op = op.resolve()

    if not pp.exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Motion project not found: {pp}",
            "exit_code": -1,
            "message": f"Motion project not found: {pp}",
            "data": None,
        }

    op.parent.mkdir(parents=True, exist_ok=True)

    # Try AppleScript first
    script = (
        f'tell application "Motion"\n'
        f'activate\n'
        f'open POSIX file {json.dumps(str(pp))}\n'
        f'export project to POSIX file {json.dumps(str(op))}\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)

    if result["status"] == "ok":
        result["message"] = f"Motion rendered to {op.name}"
        result["data"] = {"project_path": str(pp), "output_path": str(op), "method": "applescript"}
        return result

    # Try motion CLI
    cli_result = _run_subprocess(["motion", "--project", str(pp), "--export", str(op)], timeout=timeout)
    if cli_result["status"] == "ok":
        cli_result["message"] = f"Motion rendered via CLI to {op.name}"
        cli_result["data"] = {"project_path": str(pp), "output_path": str(op), "method": "cli"}
        return cli_result

    # Degraded
    result["status"] = "degraded"
    result["message"] = (
        f"Could not auto-render Motion project. Manual steps:\n"
        f"1. Open Motion → File → Open → {pp}\n"
        f"2. Share → Export Movie → Save to {op}"
    )
    result["data"] = {"project_path": str(pp), "output_path": str(op), "method": "manual_instructions"}
    return result


# ── Compressor ──────────────────────────────────────────────────────────────

def compressor_submit(job_path: str, timeout: int = 60) -> dict:
    """
    Submit a job to Compressor.

    Args:
        job_path: Path to a Compressor batch file (.cmpr) or source media.

    Note: Compressor has both AppleScript and CLI interfaces.
    """
    err = _require_enabled()
    if err:
        return err

    p = Path(job_path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    p = p.resolve()

    if not p.exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Job file not found: {p}",
            "exit_code": -1,
            "message": f"Compressor job file not found: {p}",
            "data": None,
        }

    # Try Compressor CLI first
    result = _run_subprocess(["Compressor", "-batchname", p.name, "-jobpath", str(p)], timeout=timeout)
    if result["status"] == "ok":
        result["message"] = f"Compressor job submitted: {p.name}"
        result["data"] = {"job_path": str(p), "method": "cli"}
        return result

    # Try AppleScript
    script = (
        f'tell application "Compressor"\n'
        f'activate\n'
        f'submit job POSIX file {json.dumps(str(p))}\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)
    if result["status"] == "ok":
        result["message"] = f"Compressor job submitted via AppleScript: {p.name}"
        result["data"] = {"job_path": str(p), "method": "applescript"}
        return result

    # Degraded
    result["status"] = "degraded"
    result["message"] = (
        f"Could not auto-submit to Compressor. Manual steps:\n"
        f"1. Open Compressor\n"
        f"2. File → Add File → {p}\n"
        f"3. Choose settings and destination, then Submit"
    )
    result["data"] = {"job_path": str(p), "method": "manual_instructions"}
    return result


# ── DaVinci Resolve Studio ──────────────────────────────────────────────────

def resolve_render(project_path: str, timeline_name: str, output_path: str,
                   format: str = "QuickTime", codec: str = "ProRes422HQ",
                   timeout: int = 1800) -> dict:
    """
    Render a timeline from a DaVinci Resolve Studio project.

    Strategy:
      1. Try Resolve's headless CLI (/Applications/DaVinci Resolve/Resolve).
      2. Fall back to AppleScript for GUI automation.
      3. Degrade to manual instructions.

    Args:
        project_path: Path to .drp project file or Resolve project name.
        timeline_name: Timeline to render.
        output_path: Destination video file.
        format: Container format (QuickTime, MXF, etc.).
        codec: Video codec (ProRes422HQ, DNxHR, H.264, etc.).
        timeout: Max seconds (renders can take a while).
    """
    err = _require_enabled()
    if err:
        return err

    op = Path(output_path)
    if not op.is_absolute():
        op = WORKSPACE_ROOT / op
    op.parent.mkdir(parents=True, exist_ok=True)

    # Try Resolve CLI first (Studio only)
    resolve_cli = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/Resolve"
    if Path(resolve_cli).exists():
        cmd = [
            resolve_cli, "-nogui", "-render", timeline_name,
            "-out", str(op), "-format", format, "-codec", codec,
        ]
        result = _run_subprocess(cmd, timeout=timeout)
        if result["status"] == "ok":
            result["message"] = f"Resolve rendered {timeline_name} to {op.name}"
            result["data"] = {"timeline": timeline_name, "output_path": str(op), "method": "cli"}
            return result

    # Try AppleScript
    script = (
        f'tell application "DaVinci Resolve"\n'
        f'activate\n'
        f'open project "{project_path}"\n'
        f'set current timeline to "{timeline_name}"\n'
        f'render timeline to POSIX file {json.dumps(str(op))}\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)
    if result["status"] == "ok":
        result["message"] = f"Resolve rendered {timeline_name} to {op.name}"
        result["data"] = {"timeline": timeline_name, "output_path": str(op), "method": "applescript"}
        return result

    # Degraded
    result["status"] = "degraded"
    result["message"] = (
        f"Could not auto-render from Resolve. Manual steps:\n"
        f"1. Open DaVinci Resolve → Load project '{project_path}'\n"
        f"2. Switch to Deliver page\n"
        f"3. Select timeline '{timeline_name}'\n"
        f"4. Set format: {format}, codec: {codec}\n"
        f"5. Add to Render Queue and Start Render\n"
        f"6. Save to: {op}"
    )
    result["data"] = {"project": project_path, "timeline": timeline_name, "output_path": str(op), "method": "manual_instructions"}
    return result


def resolve_export_color(page: str = "gallery", output_path: str = None,
                         timeout: int = 300) -> dict:
    """
    Export color grades (LUTs or stills) from DaVinci Resolve.

    Args:
        page: Which page to export from — "gallery" (still grades) or "timeline".
        output_path: Destination directory or file.
        timeout: Max seconds.
    """
    err = _require_enabled()
    if err:
        return err

    op = Path(output_path) if output_path else WORKSPACE_ROOT / "06_SHARED_ASSETS" / "lut-color-grades" / "export"
    if not op.is_absolute():
        op = WORKSPACE_ROOT / op
    op.parent.mkdir(parents=True, exist_ok=True)

    script = (
        f'tell application "DaVinci Resolve"\n'
        f'activate\n'
        f'export {page} grades to POSIX file {json.dumps(str(op))}\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)
    if result["status"] == "ok":
        result["message"] = f"Resolve exported {page} grades to {op.name}"
        result["data"] = {"page": page, "output_path": str(op), "method": "applescript"}
        return result

    result["status"] = "degraded"
    result["message"] = (
        f"Could not auto-export grades. Manual steps:\n"
        f"1. Open Resolve → Color page\n"
        f"2. Right-click still → Export\n"
        f"3. Save to: {op}"
    )
    result["data"] = {"page": page, "output_path": str(op), "method": "manual_instructions"}
    return result


# ── Adobe After Effects 2026 ────────────────────────────────────────────────

def after_effects_render(project_path: str, output_path: str,
                         comp_name: str = None, timeout: int = 1800) -> dict:
    """
    Render an After Effects project using the aerender CLI.

    Args:
        project_path: Path to .aep project file.
        output_path: Destination video file or directory.
        comp_name: Specific composition to render (default: render queue).
        timeout: Max seconds.

    Note: After Effects must be installed. The aerender CLI is the most
    reliable automation method; AppleScript support is very limited.
    """
    err = _require_enabled()
    if err:
        return err

    pp = Path(project_path)
    op = Path(output_path)
    if not pp.is_absolute():
        pp = WORKSPACE_ROOT / pp
    if not op.is_absolute():
        op = WORKSPACE_ROOT / op
    pp = pp.resolve()
    op = op.resolve()

    if not pp.exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"AE project not found: {pp}",
            "exit_code": -1,
            "message": f"After Effects project not found: {pp}",
            "data": None,
        }

    op.parent.mkdir(parents=True, exist_ok=True)

    aerender = "/Applications/Adobe After Effects 2026/aerender"
    if not Path(aerender).exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": "aerender not found at /Applications/Adobe After Effects 2026/aerender",
            "exit_code": -1,
            "message": "After Effects 2026 aerender CLI not found. Is AE installed?",
            "data": None,
        }

    cmd = [aerender, "-project", str(pp), "-output", str(op)]
    if comp_name:
        cmd += ["-comp", comp_name]

    result = _run_subprocess(cmd, timeout=timeout)
    result["message"] = (
        f"AE rendered {comp_name or 'render queue'} to {op.name}"
        if result["status"] == "ok"
        else f"AE render failed: {result['stderr'][:300]}"
    )
    if result["status"] == "ok":
        result["data"] = {"project_path": str(pp), "output_path": str(op), "comp": comp_name, "method": "aerender"}
    return result


def after_effects_render_queue(project_path: str, timeout: int = 1800) -> dict:
    """
    Render the current render queue in an After Effects project.

    This is the standard AE workflow: set up render queue items inside AE,
    then call this function to render them all.
    """
    return after_effects_render(project_path, "", comp_name=None, timeout=timeout)


# ── VRoid Studio ────────────────────────────────────────────────────────────

def vroid_export(vrm_file: str, output_dir: str = None, format: str = "vrm",
                 timeout: int = 300) -> dict:
    """
    Export a VRM character from VRoid Studio.

    Note: VRoid Studio has very limited scripting support.
    This function attempts AppleScript and degrades gracefully.

    Args:
        vrm_file: Path to the .vroid or .vrm file to open.
        output_dir: Destination directory for exports.
        format: Export format (vrm, fbx, etc.).
        timeout: Max seconds.
    """
    err = _require_enabled()
    if err:
        return err

    vf = Path(vrm_file)
    od = Path(output_dir) if output_dir else WORKSPACE_ROOT / "06_SHARED_ASSETS" / "character-rigs"
    if not vf.is_absolute():
        vf = WORKSPACE_ROOT / vf
    if not od.is_absolute():
        od = WORKSPACE_ROOT / od
    vf = vf.resolve()
    od = od.resolve()
    od.mkdir(parents=True, exist_ok=True)

    if not vf.exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"VRM file not found: {vf}",
            "exit_code": -1,
            "message": f"VRM file not found: {vf}",
            "data": None,
        }

    script = (
        f'tell application "VRoidStudio"\n'
        f'activate\n'
        f'open POSIX file {json.dumps(str(vf))}\n'
        f'export model to POSIX file {json.dumps(str(od))} as {format}\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)

    if result["status"] == "ok":
        result["message"] = f"VRoid exported {vf.name} to {od.name}"
        result["data"] = {"vrm_file": str(vf), "output_dir": str(od), "format": format, "method": "applescript"}
        return result

    result["status"] = "degraded"
    result["message"] = (
        f"Could not auto-export from VRoid Studio. Manual steps:\n"
        f"1. Open VRoid Studio → File → Open → {vf}\n"
        f"2. Camera / Export → Export VRM → Save to {od}"
    )
    result["data"] = {"vrm_file": str(vf), "output_dir": str(od), "format": format, "method": "manual_instructions"}
    return result


# ── MainStage ───────────────────────────────────────────────────────────────

def mainstage_open(concert_path: str, timeout: int = 60) -> dict:
    """Open a MainStage concert file (.concert)."""
    err = _require_enabled()
    if err:
        return err

    p = Path(concert_path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    p = p.resolve()

    if not p.exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Concert not found: {p}",
            "exit_code": -1,
            "message": f"MainStage concert not found: {p}",
            "data": None,
        }

    return tell_app("MainStage", f"open POSIX file {json.dumps(str(p))}", timeout=timeout)


def mainstage_set_patch(patch_name: str, timeout: int = 30) -> dict:
    """Switch to a specific patch in the current MainStage concert."""
    err = _require_enabled()
    if err:
        return err

    script = (
        f'tell application "MainStage"\n'
        f'activate\n'
        f'set current patch to "{patch_name}"\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)
    result["message"] = (
        f"MainStage switched to patch '{patch_name}'"
        if result["status"] == "ok"
        else f"MainStage patch switch failed: {result['stderr'][:200]}"
    )
    return result


def mainstage_bounce(output_path: str, format: str = "WAV", timeout: int = 300) -> dict:
    """Bounce the current MainStage concert to audio."""
    err = _require_enabled()
    if err:
        return err

    p = Path(output_path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    p = p.resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    script = (
        f'tell application "MainStage"\n'
        f'activate\n'
        f'export concert to POSIX file {json.dumps(str(p))} as {format}\n'
        f'end tell'
    )
    result = run_applescript(script, timeout=timeout)
    result["message"] = (
        f"MainStage bounced to {p.name}"
        if result["status"] == "ok"
        else f"MainStage bounce failed: {result['stderr'][:200]}"
    )
    if result["status"] == "ok":
        result["data"] = {"output_path": str(p), "format": format}
    return result


# ── Apple Shortcuts ─────────────────────────────────────────────────────────

def run_shortcut(name: str, input_text: str = "", timeout: int = 120) -> dict:
    """
    Run an Apple Shortcut by name.

    Args:
        name: The exact name of the shortcut as shown in Shortcuts app.
        input_text: Optional input to pass to the shortcut.
        timeout: Max seconds to wait.
    """
    err = _require_enabled()
    if err:
        return err

    cmd = ["shortcuts", "run", name]
    result = _run_subprocess(cmd, input_text=input_text, timeout=timeout)
    result["message"] = (
        f"Shortcut '{name}' completed" if result["status"] == "ok"
        else f"Shortcut '{name}' failed: {result['stderr'][:200]}"
    )
    if result["status"] == "ok":
        result["data"] = {"shortcut_name": name}
    return result


# ── FFmpeg helpers (complementary to media_bridge) ──────────────────────────

def ffmpeg_command(args: list[str], timeout: int = 300) -> dict:
    """
    Run an FFmpeg command with structured result.

    Args:
        args: List of FFmpeg arguments (without the 'ffmpeg' prefix).
        timeout: Max seconds.

    Example:
        ffmpeg_command(["-i", "input.mp4", "-c:v", "prores_ks", "-profile:v", "3", "output.mov"])
    """
    err = _require_enabled()
    if err:
        return err

    cmd = ["ffmpeg", "-y"] + args  # -y to overwrite without prompting
    result = _run_subprocess(cmd, timeout=timeout)
    result["message"] = (
        "FFmpeg completed" if result["status"] == "ok"
        else f"FFmpeg failed: {result['stderr'][:300]}"
    )
    if result["status"] == "ok":
        # Try to extract output path from args
        try:
            if "-" not in args:
                output_path = args[-1]
                result["data"] = {"output_path": output_path}
        except Exception:
            pass
    return result


# ── Generic app launcher ────────────────────────────────────────────────────

def open_app(app_name: str, timeout: int = 30) -> dict:
    """Open (launch) an application by name or bundle ID."""
    err = _require_enabled()
    if err:
        return err

    # Try by name first
    result = _run_subprocess(["open", "-a", app_name], timeout=timeout)
    if result["status"] == "ok":
        result["message"] = f"Opened {app_name}"
        return result

    # Try as bundle ID
    result = _run_subprocess(["open", "-b", app_name], timeout=timeout)
    result["message"] = f"Opened {app_name}" if result["status"] == "ok" else f"Could not open {app_name}: {result['stderr'][:200]}"
    return result


def open_file(file_path: str, with_app: str | None = None, timeout: int = 30) -> dict:
    """Open a file with the default app or a specific app."""
    err = _require_enabled()
    if err:
        return err

    p = Path(file_path)
    if not p.is_absolute():
        p = WORKSPACE_ROOT / p
    p = p.resolve()

    if not p.exists():
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"File not found: {p}",
            "exit_code": -1,
            "message": f"File not found: {p}",
            "data": None,
        }

    if with_app:
        result = _run_subprocess(["open", "-a", with_app, str(p)], timeout=timeout)
    else:
        result = _run_subprocess(["open", str(p)], timeout=timeout)

    result["message"] = f"Opened {p.name}" if result["status"] == "ok" else f"Could not open {p.name}: {result['stderr'][:200]}"
    if result["status"] == "ok":
        result["data"] = {"file_path": str(p), "app": with_app}
    return result


# ── Test / diagnostic ───────────────────────────────────────────────────────

def self_test() -> dict:
    """Run a quick diagnostic of the macOS automation toolkit."""
    tests = {
        "macos_tools_enabled": MACOS_TOOLS_ENABLED,
        "osascript_available": False,
        "blender_available": False,
        "ffmpeg_available": False,
        "shortcuts_available": False,
        "aerender_available": False,
        "resolve_available": False,
        "fcp_running": False,
        "logic_running": False,
        "mainstage_running": False,
        "motion_running": False,
        "compressor_running": False,
        "resolve_running": False,
        "after_effects_running": False,
        "vroid_running": False,
    }

    # Check binaries
    for binary in ["osascript", "blender", "ffmpeg", "shortcuts"]:
        r = subprocess.run(["which", binary], capture_output=True, text=True)
        key = f"{binary}_available"
        if key in tests:
            tests[key] = r.returncode == 0

    # Check aerender CLI
    aerender_path = "/Applications/Adobe After Effects 2026/aerender"
    tests["aerender_available"] = Path(aerender_path).exists()

    # Check Resolve CLI
    resolve_path = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/Resolve"
    tests["resolve_available"] = Path(resolve_path).exists()

    # Check running apps
    if MACOS_TOOLS_ENABLED:
        for app in ["Final Cut Pro", "Logic Pro", "MainStage", "Motion",
                    "Compressor", "DaVinci Resolve", "Adobe After Effects 2026",
                    "VRoidStudio"]:
            r = is_app_running(app)
            key = app.lower().replace(" ", "_").replace(".", "") + "_running"
            if key in tests and r.get("data"):
                tests[key] = r["data"]["running"]

    return {
        "status": "ok",
        "stdout": json.dumps(tests, indent=2),
        "stderr": "",
        "exit_code": 0,
        "message": f"macOS automation toolkit diagnostic complete. Enabled={MACOS_TOOLS_ENABLED}",
        "data": tests,
    }


if __name__ == "__main__":
    # Quick CLI test
    print(json.dumps(self_test(), indent=2))
