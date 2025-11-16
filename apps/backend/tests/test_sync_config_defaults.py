from pathlib import Path

from pullpilot.cli.sync_defaults import sync_defaults


def test_sync_defaults_uses_overwrite_flag(tmp_path, monkeypatch):
    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()
    nested = defaults_dir / "nested"
    nested.mkdir()
    (nested / "file.txt").write_text("default content", encoding="utf-8")
    (defaults_dir / "root.txt").write_text("root default", encoding="utf-8")

    target_dir = tmp_path / "target"

    monkeypatch.setattr(
        "pullpilot.cli.sync_defaults.get_resource_path",
        lambda _: Path(defaults_dir),
    )

    sync_defaults(target_dir, overwrite=False)

    copied_file = target_dir / "nested" / "file.txt"
    assert copied_file.read_text(encoding="utf-8") == "default content"

    copied_root = target_dir / "root.txt"
    assert copied_root.read_text(encoding="utf-8") == "root default"

    copied_file.write_text("custom content", encoding="utf-8")

    sync_defaults(target_dir, overwrite=False)
    assert copied_file.read_text(encoding="utf-8") == "custom content"

    sync_defaults(target_dir, overwrite=True)
    assert copied_file.read_text(encoding="utf-8") == "default content"
