from pullpilot.cli import validate_config as validate_config_cli


def test_package_exposes_validate_config_module():
    from pullpilot.cli import validate_config as imported

    assert imported is validate_config_cli


def test_main_returns_error_for_missing_config_path(capsys):
    exit_code = validate_config_cli.main(["--config", "/ruta/inexistente"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Ruta no encontrada" in captured.err
    assert "/ruta/inexistente" in captured.err
