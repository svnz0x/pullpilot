import importlib
import sys

import pytest

from pullpilot.scheduler import run_once

run_once_module = importlib.import_module("pullpilot.scheduler.run_once")


def test_main_empty_args_does_not_consume_process_arguments(monkeypatch):
    sentinel = ["pullpilot", "--at", "2000-01-01T00:00:00Z", "--", "echo", "hi"]
    monkeypatch.setattr(sys, "argv", sentinel.copy())

    with pytest.raises(SystemExit) as excinfo:
        run_once_module.main([])

    assert excinfo.value.code == 2
    assert sys.argv == sentinel


def test_main_strips_command_separator(monkeypatch):
    called = {}

    def fake_run(command, check):
        called["command"] = command
        called["check"] = check

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(
        run_once_module,
        "parse_datetime",
        lambda value: run_once_module.datetime.now(run_once_module.timezone.utc),
    )
    monkeypatch.setattr(run_once_module.subprocess, "run", fake_run)

    exit_code = run_once_module.main(["--at", "2030-01-01T00:00:00Z", "--", "echo", "hi"])

    assert exit_code == 0
    assert called["command"] == ["echo", "hi"]
    assert called["check"] is True


def test_main_with_invalid_datetime_returns_error_without_traceback(capsys):
    exit_code = run_once_module.main(["--at", "not-a-date", "echo", "hi"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Invalid datetime value for --at" in captured.err
    assert "Traceback" not in captured.err


def test_run_once_reexport_calls_main(monkeypatch):
    called = {}

    def fake_main(argv):
        called["argv"] = argv
        return 123

    monkeypatch.setattr(run_once_module, "main", fake_main)

    assert run_once(["--at", "2025-01-01T00:00:00Z"]) == 123
    assert called["argv"] == ["--at", "2025-01-01T00:00:00Z"]
