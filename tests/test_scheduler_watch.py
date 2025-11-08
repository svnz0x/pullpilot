"""Tests for the scheduler watcher helpers."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from pullpilot.schedule import DEFAULT_SCHEDULE_PATH
from scheduler.watch import (
    DEFAULT_SCHEDULE_FILE,
    SchedulerWatcher,
    resolve_default_updater_command,
)


class DummyProcess:
    """Minimal stand-in for ``subprocess.Popen`` return value."""

    def __init__(self, args: List[str]) -> None:
        self.args = args

    def poll(self) -> None:  # pragma: no cover - unused in tests
        return None


def test_run_once_uses_split_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: Dict[str, Any] = {}

    def fake_popen(args: List[str], *popen_args: Any, **popen_kwargs: Any) -> DummyProcess:
        calls["args"] = args
        return DummyProcess(args)

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    schedule_path = tmp_path / "schedule.json"
    cron_path = tmp_path / "schedule.cron"
    watcher = SchedulerWatcher(schedule_path, cron_path, "echo hello world", 1.0)

    watcher._start_process({"mode": "once", "datetime": "2023-09-01T10:00:00Z"})

    expected = [
        sys.executable,
        "-m",
        "scheduler.run_once",
        "--at",
        "2023-09-01T10:00:00Z",
        "--",
        "echo",
        "hello",
        "world",
    ]

    assert calls["args"] == expected


def test_write_cron_file_creates_missing_parent(tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text("{}", encoding="utf-8")

    cron_path = tmp_path / "nested" / "cron" / "pullpilot.cron"
    watcher = SchedulerWatcher(schedule_path, cron_path, "echo hello", 1.0)

    watcher._write_cron_file("* * * * *")

    assert cron_path.parent.is_dir()
    assert cron_path.read_text(encoding="utf-8") == "* * * * * echo hello\n"


def test_watcher_default_schedule_path_matches_store_default() -> None:
    assert DEFAULT_SCHEDULE_FILE == DEFAULT_SCHEDULE_PATH


def test_default_updater_command_prefers_local_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_scripts = tmp_path / "scripts"
    local_scripts.mkdir()
    local_script = local_scripts / "updater.sh"
    local_script.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr("scheduler.watch._project_root", lambda: tmp_path)

    assert resolve_default_updater_command() == str(local_script)


def test_default_updater_command_falls_back_to_container_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("scheduler.watch._project_root", lambda: tmp_path)

    assert resolve_default_updater_command() == "/app/updater.sh"


def test_watch_module_imports_without_src_path(monkeypatch: pytest.MonkeyPatch) -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    resolved_src = src_dir.resolve()

    sanitized_path: List[str] = []
    for entry in sys.path:
        try:
            entry_path = Path(entry or ".").resolve()
        except (OSError, RuntimeError):
            entry_path = Path(entry)
        if entry_path != resolved_src:
            sanitized_path.append(entry)

    assert all(Path(p or ".").resolve() != resolved_src for p in sanitized_path)
    monkeypatch.setattr(sys, "path", sanitized_path)

    for module_name in ["scheduler.watch", "pullpilot.schedule", "pullpilot"]:
        sys.modules.pop(module_name, None)

    module = importlib.import_module("scheduler.watch")

    assert module.DEFAULT_SCHEDULE_PATH is not None
    assert str(resolved_src) in sys.path
