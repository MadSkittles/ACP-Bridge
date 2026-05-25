from typer.testing import CliRunner

from acp_bridge.cli import app


def test_cli_exposes_expected_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "devboxes" in result.output
    assert "ping" in result.output
    assert "run" in result.output
    assert "cancel" in result.output
    assert "worker" in result.output


def test_worker_subcommands_are_exposed() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["worker", "--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "install-task" in result.output
    assert "uninstall-task" in result.output
