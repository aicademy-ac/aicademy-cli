from typer.testing import CliRunner
from aicademy_cli.main import app

runner = CliRunner()

def test_app_help():
    """Test that the CLI help command works."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Aicademy Practice CLI" in result.stdout

def test_app_version():
    """Test that the CLI version command works."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "aicademy-cli version" in result.stdout
