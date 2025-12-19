"""MCP server implementation for Lance Code MCP."""

from dataclasses import dataclass, field
from pathlib import Path

from fastmcp import FastMCP

from .config import LCMConfig, load_config
from .indexer import run_index
from .manifest import Manifest, load_manifest
from .merkle import MerkleTree
from .search import SearchEngine
from .storage import Storage


@dataclass
class StalenessInfo:
    """Information about index staleness."""

    is_stale: bool
    stale_files: list[str]
    message: str


@dataclass
class ServerState:
    """Shared state for MCP server components."""

    project_root: Path
    config: LCMConfig
    manifest: Manifest | None
    _search_engine: SearchEngine | None = field(default=None, repr=False)
    _storage: Storage | None = field(default=None, repr=False)

    @property
    def search_engine(self) -> SearchEngine:
        """Lazy-load search engine."""
        if self._search_engine is None:
            self._search_engine = SearchEngine(self.project_root)
        return self._search_engine

    @property
    def storage(self) -> Storage:
        """Lazy-load storage."""
        if self._storage is None:
            self._storage = Storage(self.project_root, self.config.embedding_dimensions)
            self._storage.connect()
        return self._storage


# Module-level singleton for server state
_state: ServerState | None = None


def get_state() -> ServerState:
    """Get the server state, raising if not initialized."""
    if _state is None:
        raise RuntimeError("Server not initialized. Call init_server() first.")
    return _state


def check_staleness(state: ServerState) -> StalenessInfo:
    """
    Check if the index is stale by comparing manifest tree with current filesystem.

    Uses Merkle tree root hash for fast comparison.
    """
    if state.manifest is None or state.manifest.tree is None:
        return StalenessInfo(
            is_stale=True,
            stale_files=[],
            message="No index found. Run 'lcm index' or use index_codebase tool.",
        )

    # Build current tree from filesystem
    old_tree = MerkleTree.from_dict(state.manifest.tree)
    new_tree = MerkleTree.build(
        state.project_root,
        state.config.extensions,
        state.config.exclude_patterns,
        previous_tree=old_tree,  # Use mtime optimization
    )

    # Quick root hash comparison
    if old_tree.root and new_tree.root and old_tree.root.hash == new_tree.root.hash:
        return StalenessInfo(is_stale=False, stale_files=[], message="Index is up to date.")

    # Get detailed diff
    diff = old_tree.compare(new_tree)
    stale_files = diff.new + diff.modified + diff.deleted

    return StalenessInfo(
        is_stale=True,
        stale_files=stale_files,
        message=f"Index is stale. {len(stale_files)} file(s) changed since last index.",
    )


# =============================================================================
# Tool Implementation Functions (for testing)
# =============================================================================


def search_code_impl(
    query: str,
    top_k: int = 10,
    search_type: str = "hybrid",
    bm25_weight: float = 0.5,
) -> dict:
    """Search the codebase using hybrid semantic + keyword search."""
    state = get_state()

    # Check staleness
    staleness = check_staleness(state)

    # Determine search parameters based on search_type
    fuzzy = search_type == "fuzzy"
    if search_type == "vector":
        bm25_weight = 0.0
    elif search_type == "bm25":
        bm25_weight = 1.0

    # Execute search
    results = state.search_engine.search(
        query=query,
        limit=top_k,
        fuzzy=fuzzy,
        bm25_weight=bm25_weight,
    )

    return {
        "results": [
            {
                "id": r.id,
                "text": r.text,
                "filepath": r.filepath,
                "filename": r.filename,
                "name": r.name,
                "type": r.type,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "score": r.score,
            }
            for r in results.results
        ],
        "query": query,
        "search_type": results.search_type,
        "elapsed_ms": results.elapsed_ms,
        "total_results": len(results.results),
        "warning": staleness.message if staleness.is_stale else None,
    }


def fuzzy_find_impl(
    symbol_name: str,
    symbol_type: str | None = None,
) -> dict:
    """Find symbols (functions, classes, methods) by name with typo tolerance."""
    state = get_state()

    # Check staleness
    staleness = check_staleness(state)

    # Use fuzzy search
    results = state.search_engine.fuzzy_search(symbol_name, limit=20)

    # Filter by type if specified
    if symbol_type:
        results = [r for r in results if r.type == symbol_type]

    return {
        "symbols": [
            {
                "name": r.name,
                "type": r.type,
                "filepath": r.filepath,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "score": r.score,
            }
            for r in results[:10]
        ],
        "query": symbol_name,
        "warning": staleness.message if staleness.is_stale else None,
    }


def index_codebase_impl(force: bool = False) -> dict:
    """Index or re-index the codebase for search."""
    state = get_state()

    # Run indexing
    stats = run_index(state.project_root, force=force, verbose=False)

    # Reload manifest to pick up changes
    state.manifest = load_manifest(state.project_root)

    return {
        "success": True,
        "files_scanned": stats.files_scanned,
        "files_new": stats.files_new,
        "files_modified": stats.files_modified,
        "files_deleted": stats.files_deleted,
        "chunks_added": stats.chunks_added,
        "chunks_deleted": stats.chunks_deleted,
        "message": (
            "Indexing complete."
            if stats.files_new or stats.files_modified or stats.files_deleted
            else "Index is already up to date."
        ),
    }


def get_file_context_impl(
    filepath: str,
    include_related: bool = False,
) -> dict:
    """Get all indexed code chunks from a specific file."""
    state = get_state()

    chunks = state.storage.get_chunks_by_filepath(filepath)

    result = {
        "filepath": filepath,
        "chunks": [
            {
                "id": c["id"],
                "text": c["text"],
                "name": c["name"],
                "type": c["type"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
            }
            for c in chunks
        ],
        "total_chunks": len(chunks),
    }

    if include_related:
        # Search for references to this file by filename
        filename = Path(filepath).name
        related_results = state.search_engine.fts_search(filename, limit=10)
        result["related"] = [
            {
                "filepath": r.filepath,
                "name": r.name,
                "type": r.type,
                "score": r.score,
            }
            for r in related_results
            if r.filepath != filepath
        ]

    return result


def get_stale_status_impl() -> dict:
    """Check if the search index is outdated."""
    state = get_state()
    staleness = check_staleness(state)

    return {
        "is_stale": staleness.is_stale,
        "message": staleness.message,
        "stale_files": staleness.stale_files[:20],  # Limit to first 20
        "stale_file_count": len(staleness.stale_files),
    }


def get_status_impl() -> dict:
    """Current index status, statistics, and staleness information."""
    state = get_state()
    staleness = check_staleness(state)

    return {
        "initialized": True,
        "index_exists": state.manifest is not None and state.manifest.tree is not None,
        "is_stale": staleness.is_stale,
        "total_files": state.manifest.stats.total_files if state.manifest else 0,
        "total_chunks": state.manifest.stats.total_chunks if state.manifest else 0,
        "last_updated": state.manifest.updated_at.isoformat() if state.manifest else None,
        "embedding_provider": state.config.embedding_provider,
        "embedding_model": state.config.embedding_model,
    }


def get_config_impl() -> dict:
    """Current Lance Code MCP configuration."""
    state = get_state()
    return state.config.model_dump()


def get_files_impl() -> dict:
    """List of all indexed files with chunk counts."""
    state = get_state()

    # Get all unique filepaths
    filepaths = state.storage.get_all_filepaths()

    # Build file list with chunk counts
    files = []
    for filepath in sorted(filepaths):
        chunks = state.storage.get_chunks_by_filepath(filepath)
        files.append(
            {
                "filepath": filepath,
                "chunk_count": len(chunks),
                "types": list({c["type"] for c in chunks}),
            }
        )

    return {
        "files": files,
        "total_files": len(files),
    }


# =============================================================================
# FastMCP Server and MCP Tool/Resource Wrappers
# =============================================================================

mcp = FastMCP("Lance Code MCP")


@mcp.tool
def search_code(
    query: str,
    top_k: int = 10,
    search_type: str = "hybrid",
    bm25_weight: float = 0.5,
) -> dict:
    """
    Search the codebase using hybrid semantic + keyword search.

    Args:
        query: Search query text
        top_k: Number of results to return (default: 10)
        search_type: One of "hybrid", "vector", "bm25", "fuzzy" (default: "hybrid")
        bm25_weight: Weight for BM25 vs vector search, 0.0-1.0 (default: 0.5)

    Returns:
        Search results with code chunks, scores, and optional staleness warning.
    """
    return search_code_impl(query, top_k, search_type, bm25_weight)


@mcp.tool
def fuzzy_find(
    symbol_name: str,
    symbol_type: str | None = None,
) -> dict:
    """
    Find symbols (functions, classes, methods) by name with typo tolerance.

    Args:
        symbol_name: Name to search for (typos allowed)
        symbol_type: Filter by type: "function", "class", "method", or None for all

    Returns:
        Matching symbols with names, types, locations, and similarity scores.
    """
    return fuzzy_find_impl(symbol_name, symbol_type)


@mcp.tool
def index_codebase(force: bool = False) -> dict:
    """
    Index or re-index the codebase for search.

    Args:
        force: If True, rebuild entire index from scratch. Otherwise incremental.

    Returns:
        Indexing statistics including files processed and chunks created.
    """
    return index_codebase_impl(force)


@mcp.tool
def get_file_context(
    filepath: str,
    include_related: bool = False,
) -> dict:
    """
    Get all indexed code chunks from a specific file.

    Args:
        filepath: Relative path to the file
        include_related: If True, also find chunks that reference this file

    Returns:
        All chunks from the file with their metadata.
    """
    return get_file_context_impl(filepath, include_related)


@mcp.tool
def get_stale_status() -> dict:
    """
    Check if the search index is outdated.

    Returns:
        Staleness information including changed files if any.
    """
    return get_stale_status_impl()


@mcp.resource("lcm://status")
def get_status() -> dict:
    """Current index status, statistics, and staleness information."""
    return get_status_impl()


@mcp.resource("lcm://config")
def get_config() -> dict:
    """Current Lance Code MCP configuration."""
    return get_config_impl()


@mcp.resource("lcm://files")
def get_files() -> dict:
    """List of all indexed files with chunk counts."""
    return get_files_impl()


# =============================================================================
# Server Entry Point
# =============================================================================


def run_server(project_root: Path, port: int | None = None) -> None:
    """
    Start the MCP server.

    Args:
        project_root: Path to the project root
        port: If provided, use HTTP transport on this port. Otherwise use stdio.
    """
    global _state

    # Load config and manifest
    config = load_config(project_root)
    manifest = load_manifest(project_root)

    # Initialize state
    _state = ServerState(
        project_root=project_root,
        config=config,
        manifest=manifest,
    )

    # Run server
    if port is not None:
        mcp.run(transport="sse", host="127.0.0.1", port=port)
    else:
        mcp.run()  # stdio (default)
