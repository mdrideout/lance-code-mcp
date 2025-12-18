"""Shared test fixtures for lance-code-mcp."""

from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_project():
    """Path to the fixture sample project."""
    return Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture
def initialized_project(tmp_path, cli_runner):
    """A temporary project with lcm init already run."""
    from lance_code_mcp.cli import main

    with cli_runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = cli_runner.invoke(main, ["init"])
        assert result.exit_code == 0, f"init failed: {result.output}"
        yield Path(td)
