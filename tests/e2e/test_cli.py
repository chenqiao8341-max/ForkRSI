from pathlib import Path

from typer.testing import CliRunner

from forkmem.cli import app


def test_cli_replay(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(
        app,
        [
            "replay",
            "--case",
            "artifacts/v2/cases/partial_repair_falsified.json",
            "--output",
            str(tmp_path / "replay"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"all_match": true' in result.output
