from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_config import main


def test_main_returns_error_for_missing_config_path(capsys):
    exit_code = main(["--config", "/ruta/inexistente"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err == ""
    assert "Ruta no encontrada" in captured.out
    assert "/ruta/inexistente" in captured.out
