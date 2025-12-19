"""Integration tests for the search functionality."""

import os
import shutil
from pathlib import Path

from click.testing import CliRunner

from lance_code_mcp.cli import main
from lance_code_mcp.search import SearchEngine, SearchError, run_search


class TestSearchEngine:
    """Tests for the SearchEngine class."""

    def test_semantic_search_finds_relevant_code(self, tmp_path: Path, sample_project: Path):
        """Vector search finds semantically relevant code."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Search for authentication-related code
            results = run_search(project, "authenticate user", limit=5, bm25_weight=0.0)

            assert len(results.results) > 0
            assert results.search_type == "vector"

            # Should find auth.py content
            filepaths = [r.filepath for r in results.results]
            assert any("auth" in fp for fp in filepaths)

        finally:
            os.chdir(old_cwd)

    def test_keyword_search_finds_exact_match(self, tmp_path: Path, sample_project: Path):
        """BM25 search finds exact keyword matches."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Search for exact function name
            results = run_search(project, "hash_password", limit=5, bm25_weight=1.0)

            assert len(results.results) > 0
            assert results.search_type == "fts"

            # Should find helpers.py
            filepaths = [r.filepath for r in results.results]
            assert any("helpers" in fp for fp in filepaths)

        finally:
            os.chdir(old_cwd)

    def test_hybrid_search_combines_results(self, tmp_path: Path, sample_project: Path):
        """Hybrid search combines vector and BM25 results."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Hybrid search
            results = run_search(project, "password authentication", limit=5, bm25_weight=0.5)

            assert len(results.results) > 0
            assert results.search_type == "hybrid"

        finally:
            os.chdir(old_cwd)

    def test_fuzzy_finds_with_typo(self, tmp_path: Path, sample_project: Path):
        """Fuzzy search finds symbols despite typos."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Search with typo in "authenticate"
            results = run_search(project, "authentcate", limit=5, fuzzy=True)

            assert results.search_type == "fuzzy"
            # Should find authenticate_user despite typo
            names = [r.name for r in results.results if r.name]
            assert any("authenticate" in name.lower() for name in names)

        finally:
            os.chdir(old_cwd)

    def test_search_returns_correct_metadata(self, tmp_path: Path, sample_project: Path):
        """Search results contain correct metadata."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            results = run_search(project, "User", limit=5)

            assert len(results.results) > 0
            result = results.results[0]

            # Check all metadata fields are populated
            assert result.id
            assert result.text
            assert result.filepath
            assert result.filename
            assert result.type in ("function", "class", "method", "module")
            assert result.start_line >= 1
            assert result.end_line >= result.start_line
            assert result.score > 0

        finally:
            os.chdir(old_cwd)


class TestSearchErrors:
    """Tests for search error handling."""

    def test_search_without_index_errors(self, tmp_path: Path, sample_project: Path):
        """Search before indexing raises appropriate error."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            # Initialize but don't index
            runner.invoke(main, ["init"])

            # Search should fail with helpful message
            try:
                run_search(project, "test")
                assert False, "Expected SearchError"
            except SearchError as e:
                assert "No index found" in str(e)

        finally:
            os.chdir(old_cwd)

    def test_empty_query_errors(self, tmp_path: Path, sample_project: Path):
        """Empty query raises appropriate error."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            try:
                run_search(project, "   ")
                assert False, "Expected SearchError"
            except SearchError as e:
                assert "empty" in str(e).lower()

        finally:
            os.chdir(old_cwd)


class TestSearchCLI:
    """Tests for the search CLI command."""

    def test_search_command_outputs_results(self, tmp_path: Path, sample_project: Path):
        """lcm search displays formatted results."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            result = runner.invoke(main, ["search", "password"])

            assert result.exit_code == 0
            assert "Search results for:" in result.output
            assert "score:" in result.output

        finally:
            os.chdir(old_cwd)

    def test_search_with_fuzzy_flag(self, tmp_path: Path, sample_project: Path):
        """lcm search --fuzzy uses fuzzy matching."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            result = runner.invoke(main, ["search", "--fuzzy", "pasword"])

            assert result.exit_code == 0
            assert "search type: fuzzy" in result.output

        finally:
            os.chdir(old_cwd)

    def test_search_with_num_results(self, tmp_path: Path, sample_project: Path):
        """lcm search -n limits results."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            result = runner.invoke(main, ["search", "-n", "2", "def"])

            assert result.exit_code == 0
            # Should only have 2 results
            assert "1." in result.output
            assert "2." in result.output
            # Check we don't have more than 2 results
            lines = result.output.split("\n")
            result_headers = [l for l in lines if l.strip().startswith("1.") or
                            l.strip().startswith("2.") or l.strip().startswith("3.")]
            assert len([h for h in result_headers if h.strip().startswith("3.")]) == 0

        finally:
            os.chdir(old_cwd)

    def test_search_without_init_errors(self, tmp_path: Path, sample_project: Path):
        """Search without init shows error."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        with runner.isolated_filesystem(temp_dir=project):
            # Don't init, just try to search
            result = runner.invoke(main, ["search", "test"])

            assert result.exit_code == 1
            assert "Not initialized" in result.output

    def test_search_no_results(self, tmp_path: Path, sample_project: Path):
        """Search with no matches shows appropriate message."""
        runner = CliRunner()

        project = tmp_path / "project"
        shutil.copytree(sample_project, project)

        old_cwd = os.getcwd()
        try:
            os.chdir(project)

            runner.invoke(main, ["init"])
            runner.invoke(main, ["index"])

            # Search for something unlikely to exist
            result = runner.invoke(main, ["search", "--fuzzy", "xyznonexistent123"])

            assert result.exit_code == 0
            assert "No results found" in result.output

        finally:
            os.chdir(old_cwd)
