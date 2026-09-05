"""Deployment supervisor command construction."""

import importlib.util
from pathlib import Path


SUPERVISOR_PATH = Path(__file__).resolve().parents[2] / "scripts" / "deploy" / "supervisor.py"


def _load_supervisor():
    spec = importlib.util.spec_from_file_location("deploy_supervisor", SUPERVISOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_supervisor_trusts_only_loopback_proxy_headers() -> None:
    supervisor = _load_supervisor()

    assert "--proxy-headers" in supervisor.API_CMD
    assert "--forwarded-allow-ips=127.0.0.1" in supervisor.API_CMD


def test_supervisor_starts_all_workers_when_enabled(monkeypatch) -> None:
    supervisor = _load_supervisor()
    monkeypatch.setenv("RUN_WORKERS", "true")

    commands = supervisor.worker_commands()

    assert len(commands) == 5
    assert {command[-1] for command in commands} == {
        "app.chat.webhook_processor_worker",
        "app.chat.candidate_worker",
        "app.chat.passive_escalation_worker",
        "app.chat.scheduled_task_worker",
        "app.chat.email_delivery_worker",
    }


def test_supervisor_skips_workers_when_disabled(monkeypatch) -> None:
    supervisor = _load_supervisor()
    monkeypatch.setenv("RUN_WORKERS", "false")

    assert supervisor.worker_commands() == []
