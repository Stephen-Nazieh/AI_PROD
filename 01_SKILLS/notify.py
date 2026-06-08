#!/usr/bin/env python3
"""
notify.py — macOS Desktop Notifications for Solocorn Studio

Sends native macOS notifications when pipeline stages complete or fail.
No dependencies required — uses built-in osascript.

Usage:
    python3 notify.py "Pipeline Complete" "Your video is ready" --sound "Glass"
    python3 notify.py "Pipeline Failed" "Check logs for details" --sound "Basso"
"""

import argparse
import subprocess
import sys


def send_notification(title: str, message: str, sound: str = "Glass") -> dict:
    """Send a native macOS notification."""
    script = f'''
    display notification "{message.replace('"', '\\"')}" \
        with title "{title.replace('"', '\\"')}" \
        sound name "{sound}"
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"status": "ok", "title": title, "message": message}
        return {"status": "error", "message": result.stderr.strip()}
    except FileNotFoundError:
        return {"status": "error", "message": "osascript not found (not macOS?)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def send_pipeline_notification(project: str, successful: int, total: int,
                               failed: bool = False, log_file: str = "") -> dict:
    """Send a formatted pipeline completion notification."""
    if failed:
        title = f"❌ Pipeline Failed — {project}"
        msg = f"Stopped early. Check logs for details."
        sound = "Basso"
    elif successful == total:
        title = f"✅ Pipeline Complete — {project}"
        msg = f"All {total} steps successful."
        sound = "Glass"
    else:
        title = f"⚠️ Pipeline Partial — {project}"
        msg = f"{successful}/{total} steps completed."
        sound = "Tink"
    
    if log_file:
        msg += f" Log: {log_file}"
    
    return send_notification(title, msg, sound)


def main():
    parser = argparse.ArgumentParser(description="macOS Notification Sender")
    parser.add_argument("title")
    parser.add_argument("message")
    parser.add_argument("--sound", default="Glass")
    parser.add_argument("--pipeline", action="store_true",
                        help="Format as pipeline completion notification")
    parser.add_argument("--project", default="")
    parser.add_argument("--successful", type=int, default=0)
    parser.add_argument("--total", type=int, default=0)
    parser.add_argument("--failed", action="store_true")
    parser.add_argument("--log", default="")
    args = parser.parse_args()
    
    if args.pipeline:
        result = send_pipeline_notification(
            args.project, args.successful, args.total, args.failed, args.log
        )
    else:
        result = send_notification(args.title, args.message, args.sound)
    
    print(result)
    sys.exit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
