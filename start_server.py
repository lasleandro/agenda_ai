#!/usr/bin/env python3
"""
Tennis OS - Server Launcher
============================

Starts both the FastAPI backend (port 8005) and the Next.js frontend
dev server (port 3010 — pinned, not 3000, since other local projects
commonly occupy 3000).

Usage:
    python start_server.py            # backend + frontend
    python start_server.py --tunnel   # also expose the backend via a
                                       # cloudflared quick tunnel, for
                                       # registering the YCloud webhook
                                       # (see docs/local_dev_webhook_tunnel.md)
    python start_server.py --worker   # also run candidate, ambiguity,
                                       # scheduled-task, auth-email, and
                                       # webhook-processor workers

Access:
    Frontend  → http://localhost:3010
    Backend   → http://localhost:8005/docs (Swagger UI)
"""

import argparse
import glob
import os
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
TUNNEL_DOC = PROJECT_ROOT / "docs" / "local_dev_webhook_tunnel.md"

PYTHON_BIN = os.path.expanduser("~/anaconda3/envs/agenda/bin/python3.11")

# Pinned rather than left to Next's auto-fallback, since 3000 is commonly
# occupied by other projects on this machine and an unpredictable port
# breaks anything that links to the frontend (docs, bookmarks, etc.).
FRONTEND_PORT = 3010

TRYCLOUDFLARE_URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def _find_npm() -> str | None:
    """Resolve npm even when nvm hasn't exported it onto PATH in this shell."""
    npm = shutil.which("npm")
    if npm:
        return npm
    nvm_npms = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/npm")))
    return nvm_npms[-1] if nvm_npms else None


def _npm_env(npm_bin: str) -> dict:
    """npm's shebang is `#!/usr/bin/env node` — make sure node's directory
    (e.g. nvm's) is on PATH for the child process, since conda activation
    can knock it off PATH in the parent shell."""
    env = os.environ.copy()
    node_dir = str(Path(npm_bin).parent)
    if node_dir not in env.get("PATH", ""):
        env["PATH"] = f"{node_dir}:{env.get('PATH', '')}"
    return env


def _find_cloudflared() -> str | None:
    cloudflared = shutil.which("cloudflared")
    if cloudflared:
        return cloudflared
    local_bin = os.path.expanduser("~/.local/bin/cloudflared")
    return local_bin if Path(local_bin).exists() else None


def _update_tunnel_doc(url: str):
    """Keep docs/local_dev_webhook_tunnel.md's recorded URL in sync."""
    if not TUNNEL_DOC.exists():
        return
    text = TUNNEL_DOC.read_text()
    text = re.sub(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", url, text)
    text = re.sub(r"(\| Started \| ).*( \|)", rf"\g<1>{time.strftime('%Y-%m-%d')}\g<2>", text)
    TUNNEL_DOC.write_text(text)

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def _banner():
    print("=" * 80)
    print("  Tennis OS - WhatsApp Schedule Copilot")
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


def _popen(args, **kwargs) -> subprocess.Popen:
    """subprocess.Popen wrapper that makes the child its own process-group
    leader (start_new_session=True), so _cleanup() can signal the whole
    group — npm's actual `next-server` child, uvicorn's --reload worker,
    etc. — not just the immediate child. A plain proc.terminate() only
    reaches that one immediate process; both npm and uvicorn --reload spawn
    a real child that doesn't receive a forwarded SIGTERM, so Ctrl+C left
    them running as unmanaged zombies that outlived every subsequent
    restart (observed: a stuck next-server process survived 3+ restarts
    because _start_frontend only checked "is the port listening", never
    whether the process behind it still responds)."""
    proc = subprocess.Popen(args, start_new_session=True, **kwargs)
    _processes.append(proc)
    return proc


def _start_backend() -> subprocess.Popen:
    print("  Starting FastAPI backend on port 8005 ...")
    return _popen(
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


def _start_frontend() -> subprocess.Popen | None:
    package_json = FRONTEND_DIR / "package.json"
    if not package_json.exists():
        print("  Frontend not yet scaffolded (no package.json). Skipping.")
        return None
    npm_bin = _find_npm()
    if not npm_bin:
        print("  ERROR: npm not found (checked PATH and ~/.nvm/versions/node/*/bin). Skipping frontend.")
        return None
    if _port_is_listening(FRONTEND_PORT):
        if _frontend_is_healthy(FRONTEND_PORT):
            print(f"  Reusing existing Next.js dev server on port {FRONTEND_PORT} ...")
            return None
        print(
            f"  Port {FRONTEND_PORT} is occupied by an unresponsive process "
            "(stale dev server) — freeing it before starting a fresh one ..."
        )
        _free_port(FRONTEND_PORT)
    print(f"  Starting Next.js dev server on port {FRONTEND_PORT} ...")
    return _popen(
        [npm_bin, "run", "dev", "--", "--port", str(FRONTEND_PORT)],
        cwd=str(FRONTEND_DIR),
        env=_npm_env(npm_bin),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _frontend_is_healthy(port: int) -> bool:
    """A port accepting TCP connections doesn't mean the process behind it
    is actually serving requests — a hung Next.js dev server still accepts
    connections but never responds. Require an actual HTTP response."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3):
            return True
    except Exception:
        return False


def _free_port(port: int) -> None:
    """Kill whatever is bound to `port`, even if it wasn't started by this
    script invocation (e.g. a zombie left behind by an earlier session's
    Ctrl+C not reaching a grandchild process)."""
    subprocess.run(["fuser", "-k", f"{port}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if not _port_is_listening(port):
            return
        time.sleep(0.25)


def _start_tunnel() -> subprocess.Popen | None:
    cloudflared_bin = _find_cloudflared()
    if not cloudflared_bin:
        print("  ERROR: cloudflared not found (checked PATH and ~/.local/bin). Skipping tunnel.")
        return None
    print("  Starting cloudflared tunnel -> http://localhost:8005 ...")
    return _popen(
        [cloudflared_bin, "tunnel", "--url", "http://localhost:8005"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _start_worker() -> subprocess.Popen:
    print("  Starting appointment candidate worker ...")
    return _popen(
        [PYTHON_BIN, "-m", "app.chat.candidate_worker"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _start_escalation_worker() -> subprocess.Popen:
    print("  Starting passive escalation worker ...")
    return _popen(
        [PYTHON_BIN, "-m", "app.chat.passive_escalation_worker"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _start_scheduled_task_worker() -> subprocess.Popen:
    print("  Starting scheduled task worker ...")
    return _popen(
        [PYTHON_BIN, "-m", "app.chat.scheduled_task_worker"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _start_email_delivery_worker() -> subprocess.Popen:
    print("  Starting authentication email delivery worker ...")
    return _popen(
        [PYTHON_BIN, "-m", "app.chat.email_delivery_worker"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _start_webhook_processor_worker() -> subprocess.Popen:
    print("  Starting webhook processor worker ...")
    return _popen(
        [PYTHON_BIN, "-m", "app.chat.webhook_processor_worker"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stream_output(label: str, proc: subprocess.Popen, out: "queue.Queue[tuple[str, str | None]]"):
    """Feed one process's stdout, line by line, into the shared queue. Runs
    in its own thread per process so a quiet process (e.g. backend between
    requests) can never block the main loop from seeing another process's
    (e.g. tunnel's) output that already arrived — see the readline()-in-a-
    round-robin bug this replaced."""
    for line in proc.stdout:
        out.put((label, line.rstrip()))
    out.put((label, None))  # sentinel: this process's stdout closed


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    """Signal proc's whole process group (see _popen: every child is its
    own group leader), not just the immediate process — required to reach
    npm's actual next-server child and uvicorn --reload's worker process."""
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except ProcessLookupError:
        pass  # already gone


def _cleanup(*_):
    print("\n  Stopping servers ...")
    for proc in _processes:
        _signal_group(proc, signal.SIGTERM)
    for proc in _processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _signal_group(proc, signal.SIGKILL)
            proc.wait(timeout=5)
    print("  All servers stopped.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tunnel", action="store_true",
        help="also start a cloudflared quick tunnel exposing the backend, for the YCloud webhook",
    )
    parser.add_argument(
        "--worker", action="store_true",
        help="also run candidate, ambiguity-escalation, scheduled-task, "
        "auth-email, and webhook-processor workers",
    )
    args = parser.parse_args()

    _banner()
    _check_prereqs()

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    backend = _start_backend()
    frontend_was_running = _port_is_listening(FRONTEND_PORT)
    frontend = _start_frontend()
    tunnel = _start_tunnel() if args.tunnel else None
    worker = _start_worker() if args.worker else None
    escalation_worker = _start_escalation_worker() if args.worker else None
    scheduled_task_worker = _start_scheduled_task_worker() if args.worker else None
    email_delivery_worker = _start_email_delivery_worker() if args.worker else None
    webhook_processor_worker = (
        _start_webhook_processor_worker() if args.worker else None
    )

    # Give servers a moment to start
    time.sleep(2)

    print()
    print("=" * 80)
    if frontend is not None or frontend_was_running:
        print(f"  Frontend  -> http://localhost:{FRONTEND_PORT}")
    print("  Backend   -> http://localhost:8005 (API)")
    print("  Swagger   -> http://localhost:8005/docs")
    if tunnel is not None:
        print("  Webhook tunnel -> starting, URL will appear below once ready ...")
    if worker is not None:
        print("  Candidate worker -> polling pending_processing")
        print("  Escalation worker -> polling durable ambiguity delivery")
        print("  Scheduled task worker -> polling due tenant tasks")
        print("  Email delivery worker -> polling durable auth emails")
        print("  Webhook processor worker -> draining webhook_receipts")
    print()
    print("  Press Ctrl+C to stop all servers.")
    print("=" * 80)
    print()

    # Tail process outputs
    active = [("backend", backend)]
    if frontend is not None:
        active.append(("frontend", frontend))
    if tunnel is not None:
        active.append(("tunnel", tunnel))
    if worker is not None:
        active.append(("worker", worker))
    if escalation_worker is not None:
        active.append(("escalation-worker", escalation_worker))
    if scheduled_task_worker is not None:
        active.append(("scheduled-task-worker", scheduled_task_worker))
    if email_delivery_worker is not None:
        active.append(("email-delivery-worker", email_delivery_worker))
    if webhook_processor_worker is not None:
        active.append(("webhook-processor-worker", webhook_processor_worker))

    tunnel_url_announced = False
    output_queue: "queue.Queue[tuple[str, str | None]]" = queue.Queue()
    for label, proc in active:
        threading.Thread(
            target=_stream_output, args=(label, proc, output_queue), daemon=True
        ).start()

    try:
        while True:
            try:
                label, line = output_queue.get(timeout=0.5)
            except queue.Empty:
                for check_label, proc in active:
                    if proc.poll() is not None:
                        print(f"  [{check_label}] process exited with code {proc.returncode}")
                        _cleanup()
                continue

            if line is None:
                # This process's stdout closed — it has exited (or is about
                # to); poll() gives the real exit code.
                proc = next(p for lbl, p in active if lbl == label)
                proc.wait()
                print(f"  [{label}] process exited with code {proc.returncode}")
                _cleanup()
                continue

            print(f"  [{label}] {line}")
            if label == "tunnel" and not tunnel_url_announced:
                match = TRYCLOUDFLARE_URL_RE.search(line)
                if match:
                    url = match.group(0)
                    tunnel_url_announced = True
                    _update_tunnel_doc(url)
                    print()
                    print("=" * 80)
                    print(f"  Webhook URL (register in YCloud): {url}/webhooks/ycloud")
                    print(f"  Recorded in {TUNNEL_DOC.relative_to(PROJECT_ROOT)}")
                    print("=" * 80)
                    print()
    except KeyboardInterrupt:
        _cleanup()


if __name__ == "__main__":
    main()
