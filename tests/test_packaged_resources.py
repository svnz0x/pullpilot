from importlib import resources
from pathlib import Path

from pullpilot.app import ConfigAPI
from pullpilot.resources import get_resource_path
from pullpilot.schedule import ScheduleStore
from pullpilot.scheduler.watch import resolve_default_updater_command


def test_bundled_files_accessible(monkeypatch):
    package_root = resources.files("pullpilot").joinpath("resources")

    schema = package_root.joinpath("config", "schema.json")
    updater_conf = package_root.joinpath("config", "updater.conf")
    updater_script = package_root.joinpath("scripts", "updater.sh")

    for resource in (schema, updater_conf, updater_script):
        assert resource.is_file(), f"missing bundled resource: {resource}"
        with resources.as_file(resource) as extracted:
            assert Path(extracted).is_file()

    api = ConfigAPI()
    assert api.store.schema_path == get_resource_path("config/schema.json")
    assert api.store.config_path == get_resource_path("config/updater.conf")

    schedule_store = ScheduleStore()
    assert schedule_store.schedule_path == get_resource_path("config/pullpilot.schedule")

    monkeypatch.setattr(
        "pullpilot.scheduler.watch._project_root", lambda: Path("/__does_not_exist__"),
    )
    assert Path(resolve_default_updater_command()) == get_resource_path("scripts/updater.sh")
