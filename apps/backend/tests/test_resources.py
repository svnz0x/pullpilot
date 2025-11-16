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

    copy_calls = 0

    original_copy_directory = resources_module._copy_directory

    def counting_copy_directory(source, destination):
        nonlocal copy_calls
        copy_calls += 1
        return original_copy_directory(source, destination)

    monkeypatch.setattr(resources_module, "_copy_directory", counting_copy_directory)

    cached = get_resource_path("data")
    cached_file = cached / resource_file.name
    assert cached_file.exists()
    assert copy_calls == 1

    resource_file.unlink()

    cached = get_resource_path("data")
    cached_file = cached / "example.txt"
    assert not cached_file.exists()
    assert copy_calls == 2


def test_cached_file_reused_when_unmodified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    copy_calls = 0
    original_copy_file = resources_module._copy_file

    def counting_copy_file(source, destination):
        nonlocal copy_calls
        copy_calls += 1
        return original_copy_file(source, destination)

    monkeypatch.setattr(resources_module, "_copy_file", counting_copy_file)

    cached_file_path = get_resource_path("data/example.txt")
    assert cached_file_path.exists()
    assert cached_file_path.read_text() == "original"
    assert copy_calls == 1

    cached_file_path = get_resource_path("data/example.txt")
    assert cached_file_path.exists()
    assert cached_file_path.read_text() == "original"
    assert copy_calls == 1


def test_cached_directory_reused_when_unmodified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    package_root = tmp_path / "package"
    origin_dir = package_root / "data"
    nested_dir = origin_dir / "nested"
    nested_dir.mkdir(parents=True)
    resource_file = nested_dir / "example.txt"
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

    copy_calls = 0
    original_copy_directory = resources_module._copy_directory
    target_directory = cache_root / "data"

    def counting_copy_directory(source, destination):
        nonlocal copy_calls
        if destination == target_directory:
            copy_calls += 1
        return original_copy_directory(source, destination)

    monkeypatch.setattr(resources_module, "_copy_directory", counting_copy_directory)

    cached_dir_path = get_resource_path("data")
    cached_file_path = cached_dir_path / "nested/example.txt"
    assert cached_file_path.exists()
    assert cached_file_path.read_text() == "original"
    assert copy_calls == 1

    cached_dir_path = get_resource_path("data")
    cached_file_path = cached_dir_path / "nested/example.txt"
    assert cached_file_path.exists()
    assert cached_file_path.read_text() == "original"
    assert copy_calls == 1
