"""Integration tests for the search functionality."""

from pathlib import Path

from lance_code_rag.search import SearchError, run_search


class TestSearchEngine:
    """Tests for the SearchEngine class."""

    def test_semantic_search_finds_relevant_code(self, indexed_project: Path):
        """Vector search finds semantically relevant code."""
        # Search for authentication-related code
        results = run_search(indexed_project, "authenticate user", limit=5, bm25_weight=0.0)

        assert len(results.results) > 0
        assert results.search_type == "vector"

        # Should find auth.py content
        filepaths = [r.filepath for r in results.results]
        assert any("auth" in fp for fp in filepaths)

    def test_keyword_search_finds_exact_match(self, indexed_project: Path):
        """BM25 search finds exact keyword matches."""
        # Search for exact function name
        results = run_search(indexed_project, "hash_password", limit=5, bm25_weight=1.0)

        assert len(results.results) > 0
        assert results.search_type == "fts"

        # Should find helpers.py
        filepaths = [r.filepath for r in results.results]
        assert any("helpers" in fp for fp in filepaths)

    def test_hybrid_search_combines_results(self, indexed_project: Path):
        """Hybrid search combines vector and BM25 results."""
        # Hybrid search
        results = run_search(indexed_project, "password authentication", limit=5, bm25_weight=0.5)

        assert len(results.results) > 0
        assert results.search_type == "hybrid"

    def test_fuzzy_finds_with_typo(self, indexed_project: Path):
        """Fuzzy search finds symbols despite typos."""
        # Search with typo in "authenticate"
        results = run_search(indexed_project, "authentcate", limit=5, fuzzy=True)

        assert results.search_type == "fuzzy"
        # Should find authenticate_user despite typo
        names = [r.name for r in results.results if r.name]
        assert any("authenticate" in name.lower() for name in names)

    def test_search_returns_correct_metadata(self, indexed_project: Path):
        """Search results contain correct metadata."""
        results = run_search(indexed_project, "User", limit=5)

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


class TestSearchErrors:
    """Tests for search error handling."""

    def test_search_without_index_errors(self, initialized_project: Path):
        """Search before indexing raises appropriate error."""
        # Project is initialized but not indexed
        try:
            run_search(initialized_project, "test")
            assert False, "Expected SearchError"
        except SearchError as e:
            assert "No index found" in str(e)

    def test_empty_query_errors(self, indexed_project: Path):
        """Empty query raises appropriate error."""
        try:
            run_search(indexed_project, "   ")
            assert False, "Expected SearchError"
        except SearchError as e:
            assert "empty" in str(e).lower()


class TestSearchLimits:
    """Tests for search result limits."""

    def test_limit_restricts_results(self, indexed_project: Path):
        """limit parameter restricts number of results."""
        results_2 = run_search(indexed_project, "def", limit=2)
        results_5 = run_search(indexed_project, "def", limit=5)

        assert len(results_2.results) <= 2
        assert len(results_5.results) <= 5

    def test_fuzzy_no_results_for_nonsense(self, indexed_project: Path):
        """Fuzzy search returns empty for completely unrelated query."""
        results = run_search(indexed_project, "xyznonexistent123", limit=5, fuzzy=True)
        assert len(results.results) == 0
