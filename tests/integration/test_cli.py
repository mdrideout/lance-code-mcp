"""Integration tests for CLI commands."""

import json
import os
from pathlib import Path

from lance_code_mcp import LCM_DIR, MCP_CONFIG_FILE
from lance_code_mcp.cli import main


class TestInitCommand:
    """Tests for lcm init command."""

    def test_init_creates_project_structure(self, cli_runner):
        """init creates all required files and directories."""
        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(main, ["init"])

            assert result.exit_code == 0

            # Directory exists
            assert Path(LCM_DIR).is_dir()

            # Config file valid
            config_path = Path(LCM_DIR) / "config.json"
            with open(config_path) as f:
                config = json.load(f)
            assert config["embedding_provider"] == "local"

            # Manifest file valid
            manifest_path = Path(LCM_DIR) / "manifest.json"
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert manifest["stats"]["total_files"] == 0

            # MCP config valid
            with open(MCP_CONFIG_FILE) as f:
                mcp = json.load(f)
            assert mcp["mcpServers"]["lance-code-mcp"]["command"] == "lcm"

            # Gitignore updated
            assert LCM_DIR in Path(".gitignore").read_text()

    def test_init_with_embedding_provider(self, cli_runner):
        """init --embedding sets provider and model correctly."""
        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(main, ["init", "--embedding", "openai"])

            assert result.exit_code == 0

            config_path = Path(LCM_DIR) / "config.json"
            with open(config_path) as f:
                config = json.load(f)

            assert config["embedding_provider"] == "openai"
            assert config["embedding_model"] == "text-embedding-3-small"
            assert config["embedding_dimensions"] == 1536

    def test_init_refuses_reinit_without_force(self, cli_runner):
        """init fails on existing project without --force."""
        with cli_runner.isolated_filesystem():
            cli_runner.invoke(main, ["init"])
            result = cli_runner.invoke(main, ["init"])

            assert result.exit_code == 1
            assert "already exists" in result.output

    def test_init_force_reinitializes(self, cli_runner):
        """init --force overwrites existing config."""
        with cli_runner.isolated_filesystem():
            cli_runner.invoke(main, ["init", "--embedding", "local"])
            result = cli_runner.invoke(main, ["init", "--embedding", "gemini", "--force"])

            assert result.exit_code == 0

            with open(Path(LCM_DIR) / "config.json") as f:
                config = json.load(f)
            assert config["embedding_provider"] == "gemini"


class TestStatusCommand:
    """Tests for lcm status command."""

    def test_status_shows_config(self, cli_runner):
        """status displays configuration information."""
        with cli_runner.isolated_filesystem():
            cli_runner.invoke(main, ["init", "--embedding", "gemini"])
            result = cli_runner.invoke(main, ["status"])

            assert result.exit_code == 0
            assert "gemini" in result.output


class TestCleanCommand:
    """Tests for lcm clean command."""

    def test_clean_removes_directory(self, cli_runner):
        """clean --force removes .lance-code-mcp directory."""
        with cli_runner.isolated_filesystem():
            cli_runner.invoke(main, ["init"])
            assert Path(LCM_DIR).exists()

            result = cli_runner.invoke(main, ["clean", "--force"])

            assert result.exit_code == 0
            assert not Path(LCM_DIR).exists()


class TestEnvOverrides:
    """Tests for environment variable overrides."""

    def test_env_overrides_embedding_provider(self, cli_runner):
        """LCM_EMBEDDING_PROVIDER overrides config file."""
        with cli_runner.isolated_filesystem():
            # Init with local
            cli_runner.invoke(main, ["init", "--embedding", "local"])

            # Set env to gemini
            env = os.environ.copy()
            env["LCM_EMBEDDING_PROVIDER"] = "gemini"

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
