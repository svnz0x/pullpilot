from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from pullpilot import resources as resources_module
from pullpilot.resources import get_resource_path, resource_exists


def test_resource_exists_for_existing_file():
    assert resource_exists("config/schema.json")


def test_resource_exists_for_existing_directory():
    assert resource_exists("config")


def test_resource_exists_for_missing_resource():
    assert not resource_exists("__does_not_exist__/missing.txt")


def test_cached_directory_matches_packaged_contents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    package_root = tmp_path / "package"
    origin_dir = package_root / "data"
    origin_dir.mkdir(parents=True)
    resource_file = origin_dir / "example.txt"
    resource_file.write_text("original")

    cache_root = tmp_path / "cache"

    class DummyResources:
        @staticmethod
        def files(name: str) -> Path:
            assert name == resources_module.__name__
            return package_root

        @staticmethod
        @contextlib.contextmanager
        def as_file(traversable: Path):
            yield traversable

    monkeypatch.setattr(resources_module, "resources", DummyResources)
    monkeypatch.setattr(resources_module, "_CACHE_DIR", cache_root)

    cached = get_resource_path("data")
    cached_file = cached / resource_file.name
    assert cached_file.exists()
    assert cached_file.read_text() == "original"

    resource_file.write_text("updated")

    cached = get_resource_path("data")
    cached_file = cached / "example.txt"
    assert cached_file.read_text() == "original"

    cached = get_resource_path("data", refresh=True)
    cached_file = cached / "example.txt"
    assert cached_file.read_text() == "updated"
