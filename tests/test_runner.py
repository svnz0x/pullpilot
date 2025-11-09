import pytest

from pullpilot.runner import DEFAULT_PORT, _copy_missing_config, parse_args


def test_parse_args_uses_default_port():
    args = parse_args([])

    assert args.port == DEFAULT_PORT


def test_cli_argument_overrides_port():
    args = parse_args(["--port", "1234"])

    assert args.port == 1234


def test_cli_argument_requires_integer_port():
    with pytest.raises(SystemExit):
        parse_args(["--port", "not-an-int"])


def test_copy_missing_config_merges_subdirectories(tmp_path):
    config_dir = tmp_path / "config"
    defaults_dir = tmp_path / "config.defaults"

    existing_dir = config_dir / "services"
    existing_dir.mkdir(parents=True)
    existing_file = existing_dir / "custom.yaml"
    existing_file.write_text("custom")

    services_defaults = defaults_dir / "services"
    services_defaults.mkdir(parents=True)
    (services_defaults / "custom.yaml").write_text("default")
    (services_defaults / "new.yaml").write_text("new value")

    nested_defaults = services_defaults / "deep"
    nested_defaults.mkdir()
    (nested_defaults / "nested.yaml").write_text("nested value")

    (defaults_dir / "global.yaml").write_text("global value")

    _copy_missing_config(config_dir, defaults_dir)

    assert existing_file.read_text() == "custom"
    assert (config_dir / "global.yaml").read_text() == "global value"
    assert (existing_dir / "new.yaml").read_text() == "new value"
    assert (existing_dir / "deep" / "nested.yaml").read_text() == "nested value"
