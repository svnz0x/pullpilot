"""Command-line helpers for interacting with Pullpilot resources."""

from importlib import import_module
from types import ModuleType

sync_defaults: ModuleType = import_module(".sync_defaults", __name__)
validate_config: ModuleType = import_module(".validate_config", __name__)

__all__ = [
    "sync_defaults",
    "validate_config",
]
