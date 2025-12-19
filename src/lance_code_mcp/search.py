"""Hybrid search implementation for Lance Code MCP."""

import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .config import load_config
from .embeddings import get_embedding_provider
from .storage import Storage


class SearchError(Exception):
    """Base exception for search errors."""

    pass


@dataclass
class SearchResult:
    """A single search result."""

    id: str  # "{filepath}:{start_line}"
    text: str  # code content
    filepath: str  # relative path
    filename: str  # just filename
    name: str  # symbol name
    type: str  # function/class/method/module
    start_line: int
    end_line: int
    score: float  # combined/final score
    vector_score: float | None = None
    fts_score: float | None = None


@dataclass
class SearchResults:
    """Container for search results."""

    results: list[SearchResult]
    query: str
    search_type: str  # "hybrid", "vector", "fts", "fuzzy"
    elapsed_ms: float


class SearchEngine:
    """Hybrid search engine combining vector, BM25, and fuzzy search."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._storage: Storage | None = None
        self._embedder = None
        self._fts_text_index_created = False
        self._fts_name_index_created = False

    @property
    def storage(self) -> Storage:
        """Lazy-load storage."""
        if self._storage is None:
            config = load_config(self.project_root)
            self._storage = Storage(self.project_root, dimensions=config.embedding_dimensions)
            self._storage.connect()
        return self._storage

    @property
    def embedder(self):
        """Lazy-load embedding provider."""
        if self._embedder is None:
            config = load_config(self.project_root)
            self._embedder = get_embedding_provider(config)
        return self._embedder

    def _get_chunks_table(self):
        """Get the code_chunks table from storage."""
        return self.storage._get_chunks_table()

    def _ensure_fts_text_index(self) -> None:
        """Create FTS index on text column if not exists."""
        if self._fts_text_index_created:
            return
        table = self._get_chunks_table()
        try:
            table.create_fts_index("text", replace=True)
            self._fts_text_index_created = True
        except Exception:
            # Index might already exist or creation failed
            self._fts_text_index_created = True

    def _ensure_fts_name_index(self) -> None:
        """Create FTS index on name column for fuzzy search."""
        if self._fts_name_index_created:
            return
        table = self._get_chunks_table()
        try:
            table.create_fts_index("name", replace=True)
            self._fts_name_index_created = True
        except Exception:
            self._fts_name_index_created = True

    def _row_to_result(
        self,
        row: dict[str, Any],
        score: float = 0.0,
        vector_score: float | None = None,
        fts_score: float | None = None,
    ) -> SearchResult:
        """Convert a LanceDB row to a SearchResult."""
        return SearchResult(
            id=row["id"],
            text=row["text"],
            filepath=row["filepath"],
            filename=row["filename"],
            name=row["name"],
            type=row["type"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            score=score,
            vector_score=vector_score,
            fts_score=fts_score,
        )

    def search(
        self,
        query: str,
        limit: int = 10,
        fuzzy: bool = False,
        bm25_weight: float = 0.5,
    ) -> SearchResults:
        """
        Main search entry point.

        Args:
            query: Search query
            limit: Number of results to return
            fuzzy: If True, use fuzzy symbol name search
            bm25_weight: Weight for BM25 vs vector (0.0 = pure vector, 1.0 = pure BM25)

        Returns:
            SearchResults with matching code chunks
        """
        if not query.strip():
            raise SearchError("Query cannot be empty")

        # Check if index exists
        if self.storage.count_chunks() == 0:
            raise SearchError("No index found. Run 'lcm index' first.")

        start_time = time.perf_counter()

        if fuzzy:
            results = self.fuzzy_search(query, limit)
            search_type = "fuzzy"
        elif bm25_weight <= 0.0:
            results = self.vector_search(query, limit)
            search_type = "vector"
        elif bm25_weight >= 1.0:
            results = self.fts_search(query, limit)
            search_type = "fts"
        else:
            results = self.hybrid_search(query, limit, bm25_weight)
            search_type = "hybrid"

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return SearchResults(
            results=results,
            query=query,
            search_type=search_type,
            elapsed_ms=elapsed_ms,
        )

    def vector_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """
        Pure vector/semantic search.

        Embeds the query and finds similar code chunks by vector distance.
        """
        # Embed the query
        query_vector = self.embedder.embed_single(query)

        # Vector search
        table = self._get_chunks_table()
        rows = table.search(query_vector).limit(limit).to_list()

        results = []
        for row in rows:
            # LanceDB returns _distance for vector search
            # Convert to similarity score (higher is better)
            distance = row.get("_distance", 0)
            similarity = 1.0 / (1.0 + distance)  # Convert distance to similarity
            results.append(
                self._row_to_result(row, score=similarity, vector_score=similarity)
            )

        return results

    def fts_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """
        Pure BM25/keyword full-text search.

        Uses LanceDB's FTS index on the text column.
        """
        self._ensure_fts_text_index()

        table = self._get_chunks_table()
        try:
            rows = table.search(query, query_type="fts").limit(limit).to_list()
        except Exception:
            # FTS might fail if query has special characters or no matches
            return []

        results = []
        for row in rows:
            # LanceDB FTS returns _score for relevance
            fts_score = row.get("_score", 0.0)
            results.append(
                self._row_to_result(row, score=fts_score, fts_score=fts_score)
            )

        return results

    def fuzzy_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """
        Fuzzy search on symbol names with typo tolerance.

        Uses SequenceMatcher for edit distance matching on the name field.
        """
        # Get all chunks and filter by name similarity
        table = self._get_chunks_table()

        # Use to_arrow() and iterate directly to avoid pandas dependency
        arrow_table = table.to_arrow()
        if arrow_table.num_rows == 0:
            return []

        query_lower = query.lower()
        matches: list[tuple[dict, float]] = []

        # Convert to list of dicts for iteration
        rows = arrow_table.to_pylist()

        for row in rows:
            name = row.get("name", "")
            if not name:
                continue

            # Calculate similarity ratio
            ratio = SequenceMatcher(None, query_lower, name.lower()).ratio()

            # Accept matches above threshold
            if ratio > 0.5:
                matches.append((row, ratio))

        # Sort by similarity and take top results
        matches.sort(key=lambda x: x[1], reverse=True)

        results = []
        for row_dict, ratio in matches[:limit]:
            results.append(
                self._row_to_result(row_dict, score=ratio, fts_score=ratio)
            )

        return results

    def hybrid_search(
        self, query: str, limit: int = 10, bm25_weight: float = 0.5
    ) -> list[SearchResult]:
        """
        Hybrid search combining vector and BM25 with RRF reranking.

        Fetches results from both vector and FTS search, then combines
        using Reciprocal Rank Fusion.
        """
        # Fetch more results for better fusion
        fetch_k = limit * 3

        vector_results = self.vector_search(query, limit=fetch_k)
        fts_results = self.fts_search(query, limit=fetch_k)

        # If one method returns nothing, return the other
        if not vector_results and not fts_results:
            return []
        if not vector_results:
            return fts_results[:limit]
        if not fts_results:
            return vector_results[:limit]

        # Combine with RRF
        return self._rerank_rrf(vector_results, fts_results, limit)

    def _rerank_rrf(
        self,
        vector_results: list[SearchResult],
        fts_results: list[SearchResult],
        limit: int,
        k: int = 60,
    ) -> list[SearchResult]:
        """
        Reciprocal Rank Fusion reranking.

        RRF score = sum(1 / (k + rank)) for each ranking list.
        The k parameter (default 60) controls how much to favor higher ranks.
        """
        scores: dict[str, float] = {}
        result_map: dict[str, SearchResult] = {}
        vector_scores: dict[str, float] = {}
        fts_scores: dict[str, float] = {}

        # Score from vector results
        for rank, result in enumerate(vector_results, start=1):
            scores[result.id] = scores.get(result.id, 0) + 1.0 / (k + rank)
            result_map[result.id] = result
            vector_scores[result.id] = result.vector_score or 0

        # Score from FTS results
        for rank, result in enumerate(fts_results, start=1):
            scores[result.id] = scores.get(result.id, 0) + 1.0 / (k + rank)
            if result.id not in result_map:
                result_map[result.id] = result
            fts_scores[result.id] = result.fts_score or 0

        # Sort by combined RRF score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        # Build final results with updated scores
        results = []
        for id in sorted_ids[:limit]:
            result = result_map[id]
            # Update with combined info
            results.append(
                SearchResult(
                    id=result.id,
                    text=result.text,
                    filepath=result.filepath,
                    filename=result.filename,
                    name=result.name,
                    type=result.type,
                    start_line=result.start_line,
                    end_line=result.end_line,
                    score=scores[id],
                    vector_score=vector_scores.get(id),
                    fts_score=fts_scores.get(id),
                )
            )

        return results


def run_search(
    project_root: Path,
    query: str,
    limit: int = 10,
    fuzzy: bool = False,
    bm25_weight: float = 0.5,
) -> SearchResults:
    """
    Entry point for CLI search.

    Args:
        project_root: Path to project root
        query: Search query
        limit: Number of results
        fuzzy: Enable fuzzy symbol matching
        bm25_weight: BM25 weight (0.0-1.0)

    Returns:
        SearchResults
    """
    engine = SearchEngine(project_root)
    return engine.search(query, limit, fuzzy, bm25_weight)
