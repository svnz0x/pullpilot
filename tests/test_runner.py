import os

import pytest

from pullpilot.runner import DEFAULT_PORT, PORT_ENV, parse_args


@pytest.mark.usefixtures("reset_environ")
def test_parse_args_falls_back_to_default_port(monkeypatch):
    monkeypatch.setenv(PORT_ENV, "not-an-int")

    args = parse_args([])

    assert args.port == DEFAULT_PORT


@pytest.mark.usefixtures("reset_environ")
def test_parse_args_accepts_valid_port(monkeypatch):
    monkeypatch.setenv(PORT_ENV, "9001")

    args = parse_args([])

    assert args.port == 9001


@pytest.mark.usefixtures("reset_environ")
def test_cli_argument_overrides_port(monkeypatch):
    monkeypatch.setenv(PORT_ENV, "not-an-int")

    args = parse_args(["--port", "1234"])

    assert args.port == 1234


@pytest.fixture
def reset_environ(monkeypatch):
    original = os.environ.copy()
    for key in list(os.environ):
        if key.startswith("PULLPILOT_"):
            monkeypatch.delenv(key, raising=False)

    yield

    os.environ.clear()
    os.environ.update(original)
