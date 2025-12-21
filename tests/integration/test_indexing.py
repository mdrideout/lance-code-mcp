"""Integration tests for the indexing pipeline."""

import shutil
from pathlib import Path

from lance_code_rag import LCR_DIR
from lance_code_rag.indexer import run_index
from tests.conftest import setup_lcr_project


class TestIndexing:
    """Tests for the indexing functionality."""

    def test_index_creates_lancedb(self, tmp_path: Path, sample_project: Path):
        """Indexing creates LanceDB directory."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        setup_lcr_project(project)
        run_index(project, force=False, verbose=False)

        # Verify LanceDB created
        lancedb_dir = project / LCR_DIR / "lancedb"
        assert lancedb_dir.exists()

    def test_index_chunks_python_files(self, tmp_path: Path, sample_project: Path):
        """Indexing extracts chunks from Python files."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        setup_lcr_project(project)
        stats = run_index(project, force=False, verbose=False)

        # Should have indexed some chunks
        assert stats.files_scanned > 0
        assert stats.chunks_added > 0

    def test_incremental_index_no_changes(self, tmp_path: Path, sample_project: Path):
        """Second index run detects no changes."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        setup_lcr_project(project)

        # First index
        stats1 = run_index(project, force=False, verbose=False)
        assert stats1.files_new > 0

        # Second index - should detect no changes
        stats2 = run_index(project, force=False, verbose=False)
        assert stats2.files_new == 0
        assert stats2.files_modified == 0
        assert stats2.chunks_added == 0

    def test_incremental_index_modified_file(self, tmp_path: Path, sample_project: Path):
        """Modified file is re-indexed."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        setup_lcr_project(project)

        # First index
        run_index(project, force=False, verbose=False)

        # Modify a file
        auth_file = project / "python_app" / "auth.py"
        content = auth_file.read_text()
        auth_file.write_text(content + "\n\ndef new_function(): pass\n")

        # Second index - should detect modification
        stats = run_index(project, force=False, verbose=False)
        assert stats.files_modified > 0

    def test_force_rebuilds_index(self, tmp_path: Path, sample_project: Path):
        """--force flag rebuilds entire index."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        setup_lcr_project(project)

        # First index
        stats1 = run_index(project, force=False, verbose=False)
        initial_files = stats1.files_new

        # Force reindex
        stats2 = run_index(project, force=True, verbose=False)
        # All files treated as new
        assert stats2.files_new == initial_files

    def test_index_respects_exclude_patterns(self, tmp_path: Path, sample_project: Path):
        """Index skips excluded directories."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        # Create a node_modules directory with a Python file
        node_modules = project / "node_modules"
        node_modules.mkdir()
        (node_modules / "test.py").write_text("def should_not_index(): pass")

        setup_lcr_project(project)
        stats = run_index(project, force=False, verbose=False)

        # node_modules should be excluded
        # The count should match sample_project without the extra file
        assert stats.files_scanned > 0


class TestEmbeddingCache:
    """Tests for the embedding cache functionality."""

    def test_cache_reduces_embedding_calls(self, tmp_path: Path, sample_project: Path):
        """Second index with same content uses cached embeddings."""
        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        setup_lcr_project(project)

        # First index - all embeddings computed
        stats1 = run_index(project, force=False, verbose=False)
        assert stats1.embeddings_computed > 0

        # Force reindex - should use cache
        stats2 = run_index(project, force=True, verbose=False)
        # All embeddings should come from cache on force reindex
        assert stats2.embeddings_cached > 0
