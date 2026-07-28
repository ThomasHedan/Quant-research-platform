"""Tests de la commande `edgelab api serve` (Phase 8)."""

from edgelab.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_api_serve_is_registered_with_host_port_and_reload_options() -> None:
    """`edgelab api serve --help` expose les options attendues sans démarrer de serveur."""
    result = runner.invoke(app, ["api", "serve", "--help"])

    assert result.exit_code == 0
    assert "--host" in result.stdout
    assert "--port" in result.stdout
    assert "--reload" in result.stdout
