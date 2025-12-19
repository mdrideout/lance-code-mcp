"""Integration tests for the MCP server functionality."""

import os
import shutil
from pathlib import Path

from click.testing import CliRunner

from lance_code_mcp.cli import main
from lance_code_mcp.config import load_config
from lance_code_mcp.manifest import load_manifest
from lance_code_mcp.server import (
    ServerState,
    check_staleness,
    fuzzy_find_impl,
    get_config_impl,
    get_file_context_impl,
    get_files_impl,
    get_stale_status_impl,
    get_status_impl,
    index_codebase_impl,
    search_code_impl,
)

# Module-level state reference for tests
import lance_code_mcp.server as server_module


def init_server_state(project_root: Path) -> None:
    """Initialize server state for testing."""
    config = load_config(project_root)
    manifest = load_manifest(project_root)
    server_module._state = ServerState(
        project_root=project_root,
        config=config,
        manifest=manifest,
    )


def cleanup_server_state() -> None:
    """Clean up server state after testing."""
    server_module._state = None


class TestSearchCodeTool:
    """Tests for the search_code tool."""

    def test_search_code_returns_results(self, tmp_path: Path, sample_project: Path):
        """search_code tool returns valid results."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            result = search_code_impl("authenticate", top_k=5)

            assert "results" in result
            assert len(result["results"]) > 0
            assert result["query"] == "authenticate"
            assert result["total_results"] > 0

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)

    def test_search_code_includes_staleness_warning_when_stale(
        self, tmp_path: Path, sample_project: Path
    ):
        """search_code includes warning when index is stale."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Modify a file to make index stale
            auth_file = project / "python_app" / "auth.py"
            content = auth_file.read_text()
            auth_file.write_text(content + "\n\ndef new_function(): pass\n")

            init_server_state(project)

            result = search_code_impl("authenticate", top_k=5)

            assert result["warning"] is not None
            assert "stale" in result["warning"].lower()

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)

    def test_search_code_no_warning_when_fresh(
        self, tmp_path: Path, sample_project: Path
    ):
        """search_code has no warning when index is fresh."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            result = search_code_impl("authenticate", top_k=5)

            assert result["warning"] is None

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)

    def test_search_code_supports_search_types(
        self, tmp_path: Path, sample_project: Path
    ):
        """search_code supports different search types."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            # Test different search types
            vector_result = search_code_impl("password", search_type="vector")
            assert vector_result["search_type"] == "vector"

            bm25_result = search_code_impl("password", search_type="bm25")
            assert bm25_result["search_type"] == "fts"

            hybrid_result = search_code_impl("password", search_type="hybrid")
            assert hybrid_result["search_type"] == "hybrid"

            fuzzy_result = search_code_impl("pasword", search_type="fuzzy")
            assert fuzzy_result["search_type"] == "fuzzy"

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)


class TestFuzzyFindTool:
    """Tests for the fuzzy_find tool."""

    def test_fuzzy_find_with_typo(self, tmp_path: Path, sample_project: Path):
        """fuzzy_find finds symbols despite typos."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            # Search with typo
            result = fuzzy_find_impl("authentcate")

            assert "symbols" in result
            # Should find authenticate_user despite typo
            names = [s["name"] for s in result["symbols"]]
            assert any("authenticate" in name.lower() for name in names)

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)

    def test_fuzzy_find_filters_by_type(self, tmp_path: Path, sample_project: Path):
        """fuzzy_find respects symbol_type filter."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            # Filter by function type
            result = fuzzy_find_impl("user", symbol_type="function")

            for symbol in result["symbols"]:
                assert symbol["type"] == "function"

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)


class TestIndexCodebaseTool:
    """Tests for the index_codebase tool."""

    def test_index_codebase_runs_indexing(self, tmp_path: Path, sample_project: Path):
        """index_codebase tool triggers indexing."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])

            init_server_state(project)

            result = index_codebase_impl()

            assert result["success"] is True
            assert result["files_scanned"] > 0
            assert result["chunks_added"] > 0

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)


class TestGetFileContextTool:
    """Tests for the get_file_context tool."""

    def test_get_file_context_returns_chunks(
        self, tmp_path: Path, sample_project: Path
    ):
        """get_file_context returns all chunks for a file."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            result = get_file_context_impl("python_app/auth.py")

            assert result["filepath"] == "python_app/auth.py"
            assert result["total_chunks"] > 0
            assert len(result["chunks"]) > 0

            # Check chunk structure
            chunk = result["chunks"][0]
            assert "id" in chunk
            assert "text" in chunk
            assert "type" in chunk

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)


class TestGetStaleStatusTool:
    """Tests for the get_stale_status tool."""

    def test_get_stale_status_detects_changes(
        self, tmp_path: Path, sample_project: Path
    ):
        """get_stale_status detects when files have changed."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Modify a file
            auth_file = project / "python_app" / "auth.py"
            content = auth_file.read_text()
            auth_file.write_text(content + "\n\ndef another_new_function(): pass\n")

            init_server_state(project)

            result = get_stale_status_impl()

            assert result["is_stale"] is True
            assert result["stale_file_count"] > 0

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)

    def test_get_stale_status_no_changes(self, tmp_path: Path, sample_project: Path):
        """get_stale_status reports no staleness when unchanged."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            result = get_stale_status_impl()

            assert result["is_stale"] is False
            assert result["stale_file_count"] == 0

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)


class TestResources:
    """Tests for MCP resources."""

    def test_status_resource(self, tmp_path: Path, sample_project: Path):
        """lcm://status returns correct status info."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            result = get_status_impl()

            assert result["initialized"] is True
            assert result["index_exists"] is True
            assert result["total_files"] > 0
            assert result["total_chunks"] > 0
            assert result["embedding_provider"] == "local"

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)

    def test_config_resource(self, tmp_path: Path, sample_project: Path):
        """lcm://config returns configuration."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])

            init_server_state(project)

            result = get_config_impl()

            assert "embedding_provider" in result
            assert "embedding_model" in result
            assert "extensions" in result

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)

    def test_files_resource(self, tmp_path: Path, sample_project: Path):
        """lcm://files returns indexed file list."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            init_server_state(project)

            result = get_files_impl()

            assert result["total_files"] > 0
            assert len(result["files"]) > 0

            # Check file structure
            file_info = result["files"][0]
            assert "filepath" in file_info
            assert "chunk_count" in file_info
            assert "types" in file_info

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)


class TestStalenessDetection:
    """Tests for staleness detection utility."""

    def test_check_staleness_detects_new_file(
        self, tmp_path: Path, sample_project: Path
    ):
        """Staleness detection finds new files."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Add a new file
            new_file = project / "python_app" / "new_module.py"
            new_file.write_text("def new_function(): pass\n")

            init_server_state(project)
            state = server_module._state

            staleness = check_staleness(state)

            assert staleness.is_stale is True
            assert any("new_module.py" in f for f in staleness.stale_files)

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)

    def test_check_staleness_detects_deleted_file(
        self, tmp_path: Path, sample_project: Path
    ):
        """Staleness detection finds deleted files."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Delete a file
            helpers_file = project / "python_app" / "utils" / "helpers.py"
            helpers_file.unlink()

            init_server_state(project)
            state = server_module._state

            staleness = check_staleness(state)

            assert staleness.is_stale is True
            assert any("helpers.py" in f for f in staleness.stale_files)

        finally:
            cleanup_server_state()
            os.chdir(old_cwd)
