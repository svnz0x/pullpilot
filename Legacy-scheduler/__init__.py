"""Scheduler package helpers."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType


def _ensure_src_path() -> None:
    """Append the repository ``src`` directory to ``sys.path`` if missing."""

    src_path = Path(__file__).resolve().parents[1] / "src"
    src_str = str(src_path)
    if src_str not in sys.path:
        sys.path.append(src_str)


def load_schedule_module() -> ModuleType:
    """Return the ``pullpilot.schedule`` module with a resilient import."""

    module_name = "pullpilot.schedule"
    try:
        return import_module(module_name)
    except ModuleNotFoundError:
        _ensure_src_path()
        return import_module(module_name)


__all__ = ["load_schedule_module"]

