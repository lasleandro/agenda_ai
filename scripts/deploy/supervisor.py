"""Container PID 1 for the combined platform image.

Starts the Next.js standalone server (public, on $PORT) and the FastAPI
process (loopback only, on $INTERNAL_API_PORT). Forwards SIGTERM/SIGINT to
both, and exits as soon as either child exits so the host restarts the
container instead of serving half a platform.

No third-party dependency: this must run before anything else is importable.
"""

import os
import signal
import subprocess
import sys
import time

PORT = os.environ.get("PORT", "8080")
INTERNAL_API_PORT = os.environ.get("INTERNAL_API_PORT", "8005")

# Next.js standalone build is copied to /app/frontend in the image.
NEXT_CMD = ["node", "frontend/server.js"]
NEXT_ENV = {
    **os.environ,
    "PORT": PORT,
    "HOSTNAME": "0.0.0.0",
    # Server-side proxy target for /api/* rewrites.
    "INTERNAL_API_URL": os.environ.get(
        "INTERNAL_API_URL", f"http://127.0.0.1:{INTERNAL_API_PORT}"
    ),
}

API_CMD = [
    sys.executable,
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    INTERNAL_API_PORT,
    "--workers",
    os.environ.get("API_WORKERS", "1"),
    "--proxy-headers",
    "--forwarded-allow-ips=127.0.0.1",
]

WORKER_MODULES = (
    "app.chat.webhook_processor_worker",
    "app.chat.candidate_worker",
    "app.chat.passive_escalation_worker",
    "app.chat.scheduled_task_worker",
    "app.chat.email_delivery_worker",
)

_children: list[subprocess.Popen] = []


def worker_commands() -> list[list[str]]:
    """Return worker commands only when the combined platform enables them."""
    if os.environ.get("RUN_WORKERS", "").strip().lower() != "true":
        return []
    return [[sys.executable, "-m", module] for module in WORKER_MODULES]


def _terminate_all(signum=None, _frame=None) -> None:
    for child in _children:
        if child.poll() is None:
            child.terminate()
    deadline = time.time() + 10
    for child in _children:
        remaining = max(0.0, deadline - time.time())
        try:
            child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            child.kill()


def main() -> int:
    signal.signal(signal.SIGTERM, _terminate_all)
    signal.signal(signal.SIGINT, _terminate_all)

    api = subprocess.Popen(API_CMD, cwd="/app/backend")
    _children.append(api)
    web = subprocess.Popen(NEXT_CMD, cwd="/app", env=NEXT_ENV)
    _children.append(web)
    for command in worker_commands():
        _children.append(subprocess.Popen(command, cwd="/app/backend"))

    while True:
        for child in _children:
            code = child.poll()
            if code is not None:
                sys.stderr.write(
                    f"supervisor: child {child.args!r} exited with {code}; "
                    "stopping the platform\n"
                )
                _terminate_all()
                return code or 1
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
