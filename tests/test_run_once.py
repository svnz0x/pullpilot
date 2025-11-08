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
