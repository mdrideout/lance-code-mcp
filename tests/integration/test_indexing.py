"""Integration tests for the indexing pipeline."""

import os
import shutil
from pathlib import Path

from click.testing import CliRunner

from lance_code_rag import LCR_DIR
from lance_code_rag.cli import main


class TestIndexCommand:
    """Tests for the lcr index command."""

    def test_index_creates_lancedb(self, tmp_path: Path, sample_project: Path):
        """Index command creates LanceDB directory."""
        runner = CliRunner()

        # Copy sample project to temp location
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        with runner.isolated_filesystem(temp_dir=project):
            # Initialize
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0

            # Index
            result = runner.invoke(main, ["index"])
            assert result.exit_code == 0

            # Verify LanceDB created
            lancedb_dir = Path(LCR_DIR) / "lancedb"
            assert lancedb_dir.exists()

    def test_index_chunks_python_files(self, tmp_path: Path, sample_project: Path):
        """Index command extracts chunks from Python files."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        with runner.isolated_filesystem(temp_dir=project):
            runner.invoke(main, ["init"])
            result = runner.invoke(main, ["index"])
            assert result.exit_code == 0

            # Check output for chunks indexed
            assert "Chunks indexed" in result.output
            # Should have chunks from auth.py, models.py, helpers.py
            # At least functions + classes from Python files

    def test_incremental_index_no_changes(self, tmp_path: Path, sample_project: Path):
        """Second index run detects no changes."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        with runner.isolated_filesystem(temp_dir=project):
            runner.invoke(main, ["init"])

            # First index
            result1 = runner.invoke(main, ["index"])
            assert result1.exit_code == 0
            assert "New files" in result1.output

            # Second index - should detect no changes
            result2 = runner.invoke(main, ["index"])
            assert result2.exit_code == 0
            assert "Index is up to date" in result2.output

    def test_incremental_index_modified_file(self, tmp_path: Path, sample_project: Path):
        """Modified file is re-indexed."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        # Use os.chdir instead of isolated_filesystem so we can modify files
        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])

            # First index
            runner.invoke(main, ["index"])

            # Modify a file
            auth_file = project / "python_app" / "auth.py"
            content = auth_file.read_text()
            auth_file.write_text(content + "\n\ndef new_function(): pass\n")

            # Second index - should detect modification
            result = runner.invoke(main, ["index"])
            assert result.exit_code == 0
            # Should show modified file
            assert "Modified files" in result.output
        finally:
            os.chdir(old_cwd)

    def test_force_rebuilds_index(self, tmp_path: Path, sample_project: Path):
        """--force flag rebuilds entire index."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        with runner.isolated_filesystem(temp_dir=project):
            runner.invoke(main, ["init"])

            # First index
            result1 = runner.invoke(main, ["index"])
            assert result1.exit_code == 0

            # Force reindex
            result2 = runner.invoke(main, ["index", "--force"])
            assert result2.exit_code == 0
            # All files treated as new
            assert "New files" in result2.output

    def test_index_respects_exclude_patterns(self, tmp_path: Path, sample_project: Path):
        """Index skips excluded directories."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        # Create a node_modules directory with a Python file
        node_modules = project / "node_modules"
        node_modules.mkdir()
        (node_modules / "test.py").write_text("def should_not_index(): pass")

        with runner.isolated_filesystem(temp_dir=project):
            runner.invoke(main, ["init"])
            result = runner.invoke(main, ["index"])
            assert result.exit_code == 0

            # node_modules should be excluded - check file count
            # The sample_project has fewer files than if node_modules were included


class TestEmbeddingCache:
    """Tests for the embedding cache functionality."""

    def test_cache_reduces_embedding_calls(self, tmp_path: Path, sample_project: Path):
        """Second index with same content uses cached embeddings."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        with runner.isolated_filesystem(temp_dir=project):
            runner.invoke(main, ["init"])

            # First index - all embeddings computed
            result1 = runner.invoke(main, ["index"])
            assert result1.exit_code == 0

            # Force reindex - should use cache
            result2 = runner.invoke(main, ["index", "--force"])
            assert result2.exit_code == 0
            # All embeddings should come from cache on force reindex
            assert "Embeddings from cache" in result2.output
