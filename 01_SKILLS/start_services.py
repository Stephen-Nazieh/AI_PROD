#!/usr/bin/env python3
"""
start_services.py — Launch All DeParadigm Media Production Services

Starts MLX inference servers, ComfyUI, the render queue worker pool,
Docker stack, and verifies health before declaring the studio ready.

Usage:
    python3 start_services.py
    python3 start_services.py --mlx-only
    python3 start_services.py --comfyui-only
    python3 start_services.py --docker-only
    python3 start_services.py --render-worker-only
    python3 start_services.py --status
    python3 start_services.py --stop
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SHARED_ASSETS = WORKSPACE_ROOT / "06_SHARED_ASSETS"
LOG_DIR = WORKSPACE_ROOT / "logs"

# Service definitions: name -> (start_cmd, health_url_or_cmd, timeout_sec)
SERVICES = {
    "mlx_llama4": {
        "cmd": ["mlx_lm.server", "--model", "mlx-community/Llama-4-Scout-17B-16E-Instruct-4bit", "--port", "8000"],
        "health": "http://127.0.0.1:8000/v1/models",
        "port": 8000,
        "timeout": 60,
        "optional": True,
    },
    "mlx_qwen32b": {
        "cmd": ["mlx_lm.server", "--model", "mlx-community/Qwen2.5-32B-Instruct-4bit", "--port", "8001"],
        "health": "http://127.0.0.1:8001/v1/models",
        "port": 8001,
        "timeout": 60,
        "optional": True,
    },
    "mlx_qwen7b": {
        "cmd": ["mlx_lm.server", "--model", "mlx-community/Qwen2.5-7B-Instruct-4bit", "--port", "8002"],
        "health": "http://127.0.0.1:8002/v1/models",
        "port": 8002,
        "timeout": 60,
        "optional": True,
    },
    "comfyui": {
        "cmd": ["env/bin/python3", "ComfyUI/main.py", "--port", "8188"],
        "health": "http://127.0.0.1:8188/system_stats",
        "port": 8188,
        "timeout": 120,
        "optional": True,
    },
    "render_worker": {
        "cmd": ["python3", "01_SKILLS/render_queue.py", "worker", "--workers", "2"],
        "health": None,
        "port": None,
        "timeout": 30,
        "optional": True,
    },
}

PID_DIR = WORKSPACE_ROOT / ".pids"


def load_pids() -> dict:
    path = PID_DIR / "services.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_pids(pids: dict):
    PID_DIR.mkdir(parents=True, exist_ok=True)
    (PID_DIR / "services.json").write_text(json.dumps(pids, indent=2), encoding="utf-8")


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False


def find_pid_by_port(port: int) -> int | None:
    """Resolves the PID of whatever process is listening on `port`, tracked or not."""
    try:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5,
        )
        found = [int(p) for p in out.stdout.split() if p.strip().isdigit()]
        return found[0] if found else None
    except Exception:
        return None


def check_http(url: str, timeout: float = 3.0) -> bool:
    import urllib.request
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def service_already_up(name: str, cfg: dict, pids: dict) -> dict | None:
    """Returns a result dict if the service is already live (tracked or external), else None.

    Trusts a live HTTP health response over PID bookkeeping — a service started
    outside this script (no entry in .pids/services.json) is still "up" and must
    not be started a second time onto the same port.
    """
    pid = pids.get(name)
    tracked = isinstance(pid, int) and is_running(pid)
    if not cfg.get("health"):
        # No HTTP health endpoint (e.g. a background worker pool) — PID liveness is all we have.
        return {"status": "ok", "name": name, "pid": pid} if tracked else None
    healthy = check_http(cfg["health"], timeout=2.0)
    if not (tracked or healthy):
        return None
    if not healthy:
        return None  # tracked but unresponsive — fall through and (re)start it
    return {"status": "ok", "name": name, "pid": pid if tracked else None}


def start_service(name: str, cfg: dict, log_dir: Path) -> dict:
    """Start a background service and return its PID."""
    log_file = log_dir / f"{name}.log"
    print(f"  🚀 Starting {name}...", end=" ", flush=True)

    with open(log_file, "w") as lf:
        proc = subprocess.Popen(
            cfg["cmd"],
            stdout=lf,
            stderr=subprocess.STDOUT,
            cwd=WORKSPACE_ROOT,
        )

    # Poll health
    health_url = cfg.get("health")
    if not health_url:
        # No HTTP endpoint to poll (e.g. a background worker pool) — a brief
        # grace period plus a liveness check is the best signal available.
        time.sleep(3.0)
        if proc.poll() is None:
            print(f"✅ (pid {proc.pid})")
            return {"status": "ok", "name": name, "pid": proc.pid}
        print(f"❌ (crashed, see {log_file})")
        return {"status": "error", "name": name, "message": f"Process exited early, check {log_file}"}

    deadline = time.time() + cfg["timeout"]
    ready = False
    while time.time() < deadline:
        if health_url and check_http(health_url, timeout=2.0):
            ready = True
            break
        if proc.poll() is not None:
            print(f"❌ (crashed, see {log_file})")
            return {"status": "error", "name": name, "message": f"Process exited early, check {log_file}"}
        time.sleep(1.0)

    if ready:
        print(f"✅ (pid {proc.pid})")
        return {"status": "ok", "name": name, "pid": proc.pid}
    else:
        print(f"⚠️  (started but health check timed out, pid {proc.pid})")
        return {"status": "warning", "name": name, "pid": proc.pid, "message": "health check timeout"}


def start_docker() -> dict:
    print("  🐳 Starting Docker stack...", end=" ", flush=True)
    try:
        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            capture_output=True, text=True, timeout=60,
            cwd=WORKSPACE_ROOT / ".docker",
        )
        if result.returncode == 0:
            print("✅")
            return {"status": "ok", "name": "docker"}
        else:
            print(f"❌ {result.stderr[:100]}")
            return {"status": "error", "name": "docker", "message": result.stderr[:100]}
    except FileNotFoundError:
        print("❌ docker not installed")
        return {"status": "error", "name": "docker", "message": "docker not installed"}
    except Exception as e:
        print(f"❌ {e}")
        return {"status": "error", "name": "docker", "message": str(e)[:100]}


def stop_all():
    pids = load_pids()
    print("🛑 Stopping services...")
    for name, cfg in SERVICES.items():
        pid = pids.get(name)
        source = "tracked"
        if not (isinstance(pid, int) and is_running(pid)):
            # Not in our bookkeeping (or stale) — look it up by the port it owns,
            # since it may have been started outside this script.
            pid = find_pid_by_port(cfg["port"]) if cfg.get("port") else None
            source = "external"
        if isinstance(pid, int) and is_running(pid):
            try:
                os.kill(pid, 15)  # SIGTERM
                print(f"  🛑 Sent SIGTERM to {name} (pid {pid}, {source})")
            except Exception as e:
                print(f"  ⚠️  Could not stop {name}: {e}")
        else:
            print(f"  ⏭️  {name} not running")
    # Stop docker
    try:
        subprocess.run(["docker", "compose", "down"], capture_output=True, timeout=30, cwd=WORKSPACE_ROOT / ".docker")
        print("  🛑 Docker stack stopped")
    except Exception:
        pass
    save_pids({})
    print("Done.")


def show_status():
    pids = load_pids()
    print("📊 Service Status")
    for name, cfg in SERVICES.items():
        pid = pids.get(name)
        tracked = is_running(pid) if isinstance(pid, int) else False
        health = check_http(cfg["health"], timeout=2.0) if cfg.get("health") else False
        running = tracked or health
        icon = "✅" if health else "🟡" if running else "❌"
        if health:
            health_str = "healthy"
        elif running:
            health_str = "no health"
        else:
            health_str = "down"
        pid_str = pid if tracked else ("external" if health else "—")
        print(f"  {icon} {name:<15} {health_str:<12} pid={pid_str}")


def main():
    parser = argparse.ArgumentParser(description="Start DeParadigm Media Production Services")
    parser.add_argument("--mlx-only", action="store_true", help="Start only MLX servers")
    parser.add_argument("--comfyui-only", action="store_true", help="Start only ComfyUI")
    parser.add_argument("--docker-only", action="store_true", help="Start only Docker stack")
    parser.add_argument("--render-worker-only", action="store_true", help="Start only the render queue worker pool")
    parser.add_argument("--status", action="store_true", help="Show running status")
    parser.add_argument("--stop", action="store_true", help="Stop all services")
    args = parser.parse_args()

    if args.stop:
        stop_all()
        return

    if args.status:
        show_status()
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    pids = load_pids()
    results = []

    # Determine what to start
    start_mlx = not (args.comfyui_only or args.docker_only or args.render_worker_only)
    start_comfyui = not (args.mlx_only or args.docker_only or args.render_worker_only)
    start_docker_stack = not (args.mlx_only or args.comfyui_only or args.render_worker_only)
    start_render_worker = not (args.mlx_only or args.comfyui_only or args.docker_only)

    print("=" * 60)
    print("🎬 DeParadigm Media Studio Service Launcher")
    print("=" * 60)

    if start_mlx:
        print("\n🧠 MLX Inference Servers")
        for name in ["mlx_qwen32b", "mlx_qwen7b", "mlx_llama4"]:
            cfg = SERVICES[name]
            up = service_already_up(name, cfg, pids)
            if up:
                label = f"pid {up['pid']}" if up["pid"] else "external process"
                print(f"  ✅ {name} already running ({label})")
                results.append(up)
                continue
            r = start_service(name, cfg, LOG_DIR)
            results.append(r)
            if r["status"] in ("ok", "warning"):
                pids[name] = r.get("pid")

    if start_comfyui:
        print("\n🎨 ComfyUI")
        name = "comfyui"
        cfg = SERVICES[name]
        up = service_already_up(name, cfg, pids)
        if up:
            label = f"pid {up['pid']}" if up["pid"] else "external process"
            print(f"  ✅ {name} already running ({label})")
            results.append(up)
        else:
            r = start_service(name, cfg, LOG_DIR)
            results.append(r)
            if r["status"] in ("ok", "warning"):
                pids[name] = r.get("pid")

    if start_render_worker:
        print("\n🎬 Render Queue Worker")
        name = "render_worker"
        cfg = SERVICES[name]
        up = service_already_up(name, cfg, pids)
        if up:
            label = f"pid {up['pid']}" if up["pid"] else "external process"
            print(f"  ✅ {name} already running ({label})")
            results.append(up)
        else:
            r = start_service(name, cfg, LOG_DIR)
            results.append(r)
            if r["status"] in ("ok", "warning"):
                pids[name] = r.get("pid")

    if start_docker_stack:
        print("\n🐳 Docker Stack")
        r = start_docker()
        results.append(r)

    save_pids(pids)

    print("\n" + "=" * 60)
    ok = sum(1 for r in results if r["status"] == "ok")
    warn = sum(1 for r in results if r["status"] == "warning")
    err = sum(1 for r in results if r["status"] == "error")
    print(f"Summary: {ok} ready, {warn} warning, {err} error")
    print(f"Logs: {LOG_DIR}/")
    print("=" * 60)

    if err > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
