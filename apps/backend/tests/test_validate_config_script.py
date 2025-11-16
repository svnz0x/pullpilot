from pullpilot.cli.validate_config import main


def test_main_returns_error_for_missing_config_path(capsys):
    exit_code = main(["--config", "/ruta/inexistente"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Ruta no encontrada" in captured.err
    assert "/ruta/inexistente" in captured.err
