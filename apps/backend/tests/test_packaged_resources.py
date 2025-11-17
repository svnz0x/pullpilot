from importlib import resources
from pathlib import Path

import pullpilot.scheduler.watch as watch_module
from pullpilot.api import ConfigAPI
from pullpilot.resources import get_resource_path
from pullpilot.schedule import ScheduleStore
from pullpilot.scheduler.watch import DEFAULT_COMMAND, resolve_default_updater_command


def test_bundled_files_accessible(monkeypatch):
    package_root = resources.files("pullpilot").joinpath("resources")

    schema = package_root.joinpath("config", "schema.json")
    updater_conf = package_root.joinpath("config", "updater.conf")
    updater_script = package_root.joinpath("scripts", "updater.sh")

    for resource in (schema, updater_conf, updater_script):
        assert resource.is_file(), f"missing bundled resource: {resource}"
        with resources.as_file(resource) as extracted:
            assert Path(extracted).is_file()

    monkeypatch.setenv("PULLPILOT_TOKEN", "bundled-token")
    api = ConfigAPI()
    assert api.store.schema_path == get_resource_path("config/schema.json")
    assert api.store.config_path == get_resource_path("config/updater.conf")

    schedule_store = ScheduleStore()
    assert schedule_store.schedule_path == get_resource_path("config/pullpilot.schedule")

    monkeypatch.setattr(
        "pullpilot.scheduler.watch._project_root", lambda: Path("/__does_not_exist__"),
    )
    assert resolve_default_updater_command() == str(watch_module.CANONICAL_UPDATER)


def test_ui_bundle_included():
    ui_root = get_resource_path("ui")
    index_path = ui_root / "dist" / "index.html"

    assert index_path.is_file(), "packaged UI bundle is missing index.html"

    assets_dir = ui_root / "dist" / "assets"
    assert assets_dir.is_dir(), "packaged UI bundle is missing the assets directory"
    assert any(assets_dir.iterdir()), "packaged UI bundle assets directory is empty"
