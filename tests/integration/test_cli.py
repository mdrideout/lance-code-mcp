"""Integration tests for CLI commands."""

import json
import os
from pathlib import Path

from lance_code_rag import LCR_DIR, MCP_CONFIG_FILE
from lance_code_rag.cli import main


class TestInitCommand:
    """Tests for lcr init command."""

    def test_init_creates_project_structure(self, cli_runner):
        """init creates all required files and directories."""
        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(main, ["init", "--embedding", "local", "--no-index"])

            assert result.exit_code == 0

            # Directory exists
            assert Path(LCR_DIR).is_dir()

            # Config file valid
            config_path = Path(LCR_DIR) / "config.json"
            with open(config_path) as f:
                config = json.load(f)
            assert config["embedding_provider"] == "local"

            # Manifest file valid
            manifest_path = Path(LCR_DIR) / "manifest.json"
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert manifest["stats"]["total_files"] == 0

            # MCP config valid - server entry exists with correct structure
            with open(MCP_CONFIG_FILE) as f:
                mcp = json.load(f)
            assert "lance-code-rag" in mcp["mcpServers"]
            # Command is either "lcr" (global) or "uv" (via uv run)
            assert mcp["mcpServers"]["lance-code-rag"]["command"] in ("lcr", "uv")
            assert "LCR_ROOT" in mcp["mcpServers"]["lance-code-rag"]["env"]

            # Gitignore updated
            assert LCR_DIR in Path(".gitignore").read_text()

    def test_init_with_embedding_provider(self, cli_runner):
        """init --embedding sets provider and model correctly."""
        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(main, ["init", "--embedding", "openai", "--no-index"])

            assert result.exit_code == 0

            config_path = Path(LCR_DIR) / "config.json"
            with open(config_path) as f:
                config = json.load(f)

            assert config["embedding_provider"] == "openai"
            assert config["embedding_model"] == "text-embedding-3-small"
            assert config["embedding_dimensions"] == 1536

    def test_init_refuses_reinit_without_force(self, cli_runner):
        """init fails on existing project without --force."""
        with cli_runner.isolated_filesystem():
            cli_runner.invoke(main, ["init", "--embedding", "local", "--no-index"])
            result = cli_runner.invoke(main, ["init", "--embedding", "local", "--no-index"])

            assert result.exit_code == 1
            assert "already exists" in result.output

    def test_init_force_reinitializes(self, cli_runner):
        """init --force overwrites existing config."""
        with cli_runner.isolated_filesystem():
            cli_runner.invoke(main, ["init", "--embedding", "local", "--no-index"])
            result = cli_runner.invoke(
                main, ["init", "--embedding", "gemini", "--force", "--no-index"]
            )

            assert result.exit_code == 0

            with open(Path(LCR_DIR) / "config.json") as f:
                config = json.load(f)
            assert config["embedding_provider"] == "gemini"

    def test_init_auto_indexes(self, cli_runner, sample_project):
        """init --embedding auto-runs indexing by default."""
        with cli_runner.isolated_filesystem():
            # Create a simple file to index
            Path("test.py").write_text("def hello(): pass")

            result = cli_runner.invoke(main, ["init", "--embedding", "local"])

            assert result.exit_code == 0
            assert "Building search index" in result.output
            assert "Ready!" in result.output

            # Verify index was created
            manifest_path = Path(LCR_DIR) / "manifest.json"
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert manifest["stats"]["total_files"] >= 1


class TestStatusCommand:
    """Tests for lcr status command."""

    def test_status_shows_config(self, cli_runner):
        """status displays configuration information."""
        with cli_runner.isolated_filesystem():
            cli_runner.invoke(main, ["init", "--embedding", "gemini", "--no-index"])
            result = cli_runner.invoke(main, ["status"])

            assert result.exit_code == 0
            assert "gemini" in result.output


class TestCleanCommand:
    """Tests for lcr clean command."""

    def test_clean_removes_directory(self, cli_runner):
        """clean --force removes .lance-code-rag directory."""
        with cli_runner.isolated_filesystem():
            cli_runner.invoke(main, ["init", "--embedding", "local", "--no-index"])
            assert Path(LCR_DIR).exists()

            result = cli_runner.invoke(main, ["clean", "--force"])

            assert result.exit_code == 0
            assert not Path(LCR_DIR).exists()


class TestEnvOverrides:
    """Tests for environment variable overrides."""

    def test_env_overrides_embedding_provider(self, cli_runner):
        """LCR_EMBEDDING_PROVIDER overrides config file."""
        with cli_runner.isolated_filesystem():
            # Init with local
            cli_runner.invoke(main, ["init", "--embedding", "local", "--no-index"])

            # Set env to gemini
            env = os.environ.copy()
            env["LCR_EMBEDDING_PROVIDER"] = "gemini"

            result = cli_runner.invoke(main, ["status"], env=env)

            assert result.exit_code == 0
            # Status should show gemini from env override
            assert "gemini" in result.output


class TestRequiresInit:
    """Tests that commands require initialization."""

    def test_commands_require_init(self, cli_runner):
        """Commands fail gracefully when not initialized."""
        with cli_runner.isolated_filesystem():
            for cmd in [["status"], ["index"], ["search", "test"], ["serve"]]:
                result = cli_runner.invoke(main, cmd)
                assert result.exit_code == 1
                assert "init" in result.output.lower()
