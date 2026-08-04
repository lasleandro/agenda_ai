#!/usr/bin/env python3
"""
Agenda AI - Server Launcher
============================

Starts both the FastAPI backend (port 8005) and the Next.js frontend
dev server (port 3000).

Usage:
    python start_server.py

Access:
    Frontend  → http://localhost:3000
    Backend   → http://localhost:8005/docs (Swagger UI)
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

PYTHON_BIN = os.path.expanduser("~/anaconda3/envs/agenda/bin/python3.11")

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def _banner():
    print("=" * 80)
    print("  Agenda AI - WhatsApp Schedule Copilot")
    print("=" * 80)
    print(f"  Python:   {PYTHON_BIN}")
    print(f"  Backend:  {BACKEND_DIR}")
    print(f"  Frontend: {FRONTEND_DIR}")
    print()


def _check_prereqs():
    """Fail early if required paths are missing."""
    if not PYTHON_BIN or not Path(PYTHON_BIN).exists():
        print(f"  ERROR: conda env 'agenda' Python not found at {PYTHON_BIN}")
        sys.exit(1)
    if not BACKEND_DIR.exists():
        print(f"  ERROR: backend directory not found at {BACKEND_DIR}")
        sys.exit(1)
    if not FRONTEND_DIR.exists():
        print(f"  ERROR: frontend directory not found at {FRONTEND_DIR}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

_processes: list[subprocess.Popen] = []


def _start_backend() -> subprocess.Popen:
    print("  Starting FastAPI backend on port 8005 ...")
    proc = subprocess.Popen(
        [
            PYTHON_BIN, "-m", "uvicorn", "app.main:app",
            "--host", "0.0.0.0",
            "--port", "8005",
            "--reload",
        ],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _processes.append(proc)
    return proc


def _start_frontend() -> subprocess.Popen | None:
    package_json = FRONTEND_DIR / "package.json"
    if not package_json.exists():
        print("  Frontend not yet scaffolded (no package.json). Skipping.")
        return None
    print("  Starting Next.js dev server on port 3000 ...")
    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _processes.append(proc)
    return proc


def _cleanup(*_):
    print("\n  Stopping servers ...")
    for proc in _processes:
        proc.terminate()
    for proc in _processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("  All servers stopped.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _banner()
    _check_prereqs()

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    backend = _start_backend()
    frontend = _start_frontend()

    # Give servers a moment to start
    time.sleep(2)

    print()
    print("=" * 80)
    if frontend is not None:
        print("  Frontend  -> http://localhost:3000")
    print("  Backend   -> http://localhost:8005 (API)")
    print("  Swagger   -> http://localhost:8005/docs")
    print()
    print("  Press Ctrl+C to stop all servers.")
    print("=" * 80)
    print()

    # Tail process outputs
    active = [("backend", backend)]
    if frontend is not None:
        active.append(("frontend", frontend))

    try:
        while True:
            for label, proc in active:
                line = proc.stdout.readline()
                if line:
                    print(f"  [{label}] {line.rstrip()}")
                if proc.poll() is not None:
                    print(f"  [{label}] process exited with code {proc.returncode}")
                    _cleanup()
            time.sleep(0.1)
    except KeyboardInterrupt:
        _cleanup()


if __name__ == "__main__":
    main()
