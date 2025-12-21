"""Integration tests for CLI entry point.

Note: The CLI is TUI-only now. Most functionality is tested via TUI tests
or direct module tests. This file tests the CLI entry point itself.
"""

from lance_code_rag.cli import main


class TestCLIEntry:
    """Tests for the CLI entry point."""

    def test_version_flag(self, cli_runner):
        """--version shows version info."""
        result = cli_runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "lcr" in result.output
        assert "0.1.0" in result.output

    def test_help_flag(self, cli_runner):
        """--help shows usage info."""
        result = cli_runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Lance Code RAG" in result.output
        assert "/init" in result.output
        assert "/search" in result.output
