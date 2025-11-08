import pytest

from pullpilot.runner import DEFAULT_PORT, parse_args


def test_parse_args_uses_default_port():
    args = parse_args([])

    assert args.port == DEFAULT_PORT


def test_cli_argument_overrides_port():
    args = parse_args(["--port", "1234"])

    assert args.port == 1234


def test_cli_argument_requires_integer_port():
    with pytest.raises(SystemExit):
        parse_args(["--port", "not-an-int"])
