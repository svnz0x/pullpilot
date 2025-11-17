from http import HTTPStatus
from importlib import resources
from pathlib import Path

import pytest
from fastapi import FastAPI
import pullpilot.scheduler.watch as watch_module
from pullpilot.api import ConfigAPI
from pullpilot.resources import get_resource_path, resource_exists
from pullpilot.schedule import ScheduleStore
from pullpilot.scheduler.watch import DEFAULT_COMMAND, resolve_default_updater_command
from pullpilot.ui.application import configure_application


class _DummyAuthenticator:
    configured = True

    @staticmethod
    def authorize(headers):  # pragma: no cover - trivial helper
        return True


class _DummyAPI:
    def __init__(self) -> None:
        self.authenticator = _DummyAuthenticator()

    @staticmethod
    def handle_request(method, path, payload=None, headers=None):  # pragma: no cover - helper
        return HTTPStatus.OK, {}


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
    if not resource_exists("ui"):
        pytest.skip("UI bundle not built; skipping packaged resource assertion")

    ui_root = get_resource_path("ui")
    index_path = ui_root / "dist" / "index.html"

    assert index_path.is_file(), "packaged UI bundle is missing index.html"

    assets_dir = ui_root / "dist" / "assets"
    assert assets_dir.is_dir(), "packaged UI bundle is missing the assets directory"
    assert any(assets_dir.iterdir()), "packaged UI bundle assets directory is empty"


def test_configure_application_mounts_packaged_assets(monkeypatch, tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "chunk.js").write_text("console.log('hi');", encoding="utf-8")
    (dist_dir / "manifest.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "pullpilot.ui.application.resource_exists", lambda relative: relative == "ui"
    )
    monkeypatch.setattr(
        "pullpilot.ui.application.get_resource_path", lambda relative: tmp_path
    )

    app = FastAPI()
    configure_application(app, _DummyAPI())

    asset_mounts = [route for route in app.routes if getattr(route, "path", None) == "/ui/assets"]
    assert asset_mounts, "packaged assets should be mounted when available"

    src_mounts = [route for route in app.routes if getattr(route, "path", None) == "/ui/src"]
    assert not src_mounts, "source assets should not be mounted when packaged assets exist"


def test_configure_application_falls_back_when_bundle_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("pullpilot.ui.application.resource_exists", lambda relative: False)

    def _unexpected_call(relative):  # pragma: no cover - sanity helper
        raise AssertionError("get_resource_path should not be called when resources are missing")

    monkeypatch.setattr("pullpilot.ui.application.get_resource_path", _unexpected_call)

    source_root = tmp_path / "alt-tree" / "frontend"
    src_dir = source_root / "src"
    src_dir.mkdir(parents=True)
    index_html = "<html><body>fallback</body></html>"
    styles_css = "body { color: #f0f; }"
    script_js = "console.log('fallback');"
    (source_root / "index.html").write_text(index_html, encoding="utf-8")
    (src_dir / "styles.css").write_text(styles_css, encoding="utf-8")
    (src_dir / "app.js").write_text(script_js, encoding="utf-8")

    missing_candidate = tmp_path / "does-not-exist"
    monkeypatch.setattr(
        "pullpilot.ui.application._iter_ui_source_candidates",
        lambda: (missing_candidate, source_root),
    )

    app = FastAPI()
    configure_application(app, _DummyAPI())

    src_mounts = [route for route in app.routes if getattr(route, "path", None) == "/ui/src"]
    assert len(src_mounts) == 1, "source assets must be mounted exactly once when bundling fails"
    assert Path(src_mounts[0].app.directory) == src_dir

    asset_mounts = [route for route in app.routes if getattr(route, "path", None) == "/ui/assets"]
    assert not asset_mounts, "packaged assets should not be mounted when the bundle is missing"

    ui_page = next(route for route in app.routes if getattr(route, "path", None) == "/ui/")
    response = ui_page.endpoint()
    assert response.body.decode("utf-8") == index_html

    styles_route = next(route for route in app.routes if getattr(route, "path", None) == "/ui/styles.css")
    styles_response = styles_route.endpoint()
    assert Path(styles_response.path) == src_dir / "styles.css"

    script_route = next(route for route in app.routes if getattr(route, "path", None) == "/ui/app.js")
    script_response = script_route.endpoint()
    assert Path(script_response.path) == src_dir / "app.js"
