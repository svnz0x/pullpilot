import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scheduler import run_once


def test_main_empty_args_does_not_consume_process_arguments(monkeypatch):
    sentinel = ["pullpilot", "--at", "2000-01-01T00:00:00Z", "--", "echo", "hi"]
    monkeypatch.setattr(sys, "argv", sentinel.copy())

    with pytest.raises(SystemExit) as excinfo:
        run_once.main([])

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

    monkeypatch.setattr(run_once, "parse_datetime", lambda value: run_once.datetime.now(run_once.timezone.utc))
    monkeypatch.setattr(run_once.subprocess, "run", fake_run)

    exit_code = run_once.main(["--at", "2030-01-01T00:00:00Z", "--", "echo", "hi"])

    assert exit_code == 0
    assert called["command"] == ["echo", "hi"]
    assert called["check"] is True


def test_main_with_invalid_datetime_returns_error_without_traceback(capsys):
    exit_code = run_once.main(["--at", "not-a-date", "echo", "hi"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Invalid datetime value for --at" in captured.err
    assert "Traceback" not in captured.err
