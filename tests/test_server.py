import base64
from http import HTTPStatus
from pathlib import Path


import pytest

from pullpilot.config import ConfigStore
from pullpilot.schedule import ScheduleStore
from pullpilot.app import ConfigAPI, create_app


@pytest.fixture()
def allow_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PULLPILOT_ALLOW_ANONYMOUS", "1")


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    schema = Path(__file__).resolve().parents[1] / "config" / "schema.json"
    config_path = tmp_path / "updater.conf"
    return ConfigStore(config_path, schema)


@pytest.fixture()
def schedule_store(tmp_path: Path) -> ScheduleStore:
    schedule_path = tmp_path / "pullpilot.schedule"
    return ScheduleStore(schedule_path)


def test_get_returns_defaults(
    allow_anonymous: None, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.OK
    assert body["values"]["BASE_DIR"] == "/srv/compose"


def test_get_includes_schema_metadata(
    allow_anonymous: None, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.OK
    schema = body.get("schema", {})
    variables = {entry["name"]: entry for entry in schema.get("variables", [])}
    assert "PRUNE_VOLUMES" in variables
    assert variables["PRUNE_VOLUMES"]["description"]
    assert body.get("meta", {}).get("multiline_fields") == ["COMPOSE_PROJECTS_FILE"]


def test_put_updates_config_and_multiline(
    allow_anonymous: None,
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    projects_path = tmp_path / "projects.txt"
    values["BASE_DIR"] = str(tmp_path / "compose")
    values["LOG_RETENTION_DAYS"] = 30
    values["SMTP_READ_ENVELOPE"] = False
    values["COMPOSE_PROJECTS_FILE"] = str(projects_path)
    multiline = {"COMPOSE_PROJECTS_FILE": "/tmp/alpha\n/tmp/beta\n"}

    status, response = api.handle_request(
        "PUT", "/config", {"values": values, "multiline": multiline}
    )
    assert status == HTTPStatus.OK
    assert response["values"]["LOG_RETENTION_DAYS"] == 30
    assert Path(values["COMPOSE_PROJECTS_FILE"]).read_text(encoding="utf-8") == multiline[
        "COMPOSE_PROJECTS_FILE"
    ]
    text = store.config_path.read_text(encoding="utf-8")
    assert "SMTP_READ_ENVELOPE=false" in text
    assert "LOG_RETENTION_DAYS=30" in text


def test_put_returns_validation_errors(
    allow_anonymous: None, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)
    status, body = api.handle_request(
        "PUT",
        "/config",
        {"values": {"BASE_DIR": "", "LOG_RETENTION_DAYS": 0}},
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert any(error["field"] == "BASE_DIR" for error in body["details"])


def test_requests_rejected_without_credentials(monkeypatch, store: ConfigStore, schedule_store: ScheduleStore) -> None:
    monkeypatch.delenv("PULLPILOT_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.delenv("PULLPILOT_USERNAME", raising=False)
    monkeypatch.delenv("PULLPILOT_PASSWORD", raising=False)
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"

    status, body = api.handle_request("PUT", "/config", {"values": {}})
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"


def test_token_auth_blocks_unauthenticated_access(
    monkeypatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.setenv("PULLPILOT_TOKEN", "super-secret")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"

    status, body = api.handle_request("GET", "/config", headers={"Authorization": "Bearer super-secret"})
    assert status == HTTPStatus.OK


def test_explicit_anonymous_mode_allows_requests(
    monkeypatch: pytest.MonkeyPatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.setenv("PULLPILOT_ALLOW_ANONYMOUS", "true")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.OK

    status, updated = api.handle_request("PUT", "/config", {"values": body["values"]})
    assert status == HTTPStatus.OK
    assert updated["values"] == body["values"]


def test_legacy_env_vars_supported(
    monkeypatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setenv("PULLPILOT_UI_TOKEN", "legacy-secret")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"

    status, body = api.handle_request("GET", "/config", headers={"Authorization": "Bearer legacy-secret"})
    assert status == HTTPStatus.OK


def test_basic_auth_accepts_valid_credentials(
    monkeypatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setenv("PULLPILOT_USERNAME", "demo")
    monkeypatch.setenv("PULLPILOT_PASSWORD", "pass")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, _ = api.handle_request("GET", "/config")
    assert status == HTTPStatus.UNAUTHORIZED

    credentials = base64.b64encode(b"demo:pass").decode("ascii")
    status, _ = api.handle_request("GET", "/config", headers={"Authorization": f"Basic {credentials}"})
    assert status == HTTPStatus.OK


def test_schedule_get_returns_defaults(
    allow_anonymous: None, schedule_store: ScheduleStore, store: ConfigStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/schedule")
    assert status == HTTPStatus.OK
    assert body["mode"] == "cron"
    assert body["expression"] == "0 4 * * *"


def test_schedule_put_accepts_valid_cron(
    allow_anonymous: None, schedule_store: ScheduleStore, store: ConfigStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("PUT", "/schedule", {"mode": "cron", "expression": "15 2 * * 1"})
    assert status == HTTPStatus.OK
    assert body["expression"] == "15 2 * * 1"
    saved = schedule_store.load()
    assert saved.expression == "15 2 * * 1"


def test_schedule_put_rejects_invalid_expression(
    allow_anonymous: None, schedule_store: ScheduleStore, store: ConfigStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("PUT", "/schedule", {"mode": "cron", "expression": "bad"})
    assert status == HTTPStatus.BAD_REQUEST
    assert body["error"] == "validation failed"
    assert body["details"][0]["field"] == "expression"


def test_schedule_put_accepts_datetime(
    allow_anonymous: None, schedule_store: ScheduleStore, store: ConfigStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request(
        "PUT",
        "/schedule",
        {"mode": "once", "datetime": "2030-05-10T12:30:00+02:00"},
    )
    assert status == HTTPStatus.OK
    assert body["mode"] == "once"
    assert body["datetime"].endswith("+00:00")


def test_fastapi_get_propagates_error(
    allow_anonymous: None,
    monkeypatch: pytest.MonkeyPatch,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    original_handle_request = ConfigAPI.handle_request

    def fake_handle_request(
        self: ConfigAPI,
        method: str,
        path: str,
        payload=None,
        headers=None,
    ):
        if method == "GET" and path == "/config":
            return HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "boom"}
        return original_handle_request(self, method, path, payload, headers)

    monkeypatch.setattr(ConfigAPI, "handle_request", fake_handle_request)

    app = create_app(store=store, schedule_store=schedule_store)
    client = TestClient(app)

    response = client.get("/config")
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
