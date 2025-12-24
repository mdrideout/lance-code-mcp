"""Indexing pipeline orchestration for Lance Code RAG."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# Progress callback signature: (current_file_index, total_files, stage)
ProgressCallback = Callable[[int, int, str], None]

from .chunker import Chunk, Chunker
from .config import LCRConfig, load_config
from .embeddings import EmbeddingProvider, get_embedding_provider
from .manifest import ManifestStats, create_empty_manifest, load_manifest, save_manifest
from .merkle import MerkleTree, TreeDiff, compute_file_hash
from .storage import CachedEmbedding, CodeChunk, Storage


@dataclass
class IndexStats:
    """Statistics from an indexing run."""

    files_scanned: int = 0
    files_new: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    chunks_added: int = 0
    chunks_deleted: int = 0
    embeddings_computed: int = 0
    embeddings_cached: int = 0


class Indexer:
    """Orchestrates the indexing pipeline."""

    def __init__(
        self,
        project_root: Path,
        config: LCRConfig | None = None,
        verbose: bool = False,
        console: Console | None = None,
    ):
        self.project_root = project_root
        self.config = config or load_config(project_root)
        self.verbose = verbose
        self.console = console or Console()

        self._storage: Storage | None = None
        self._embedder: EmbeddingProvider | None = None
        self._chunker: Chunker | None = None

    @property
    def storage(self) -> Storage:
        """Lazy-load storage connection."""
        if self._storage is None:
            self._storage = Storage(self.project_root, self.config.embedding_dimensions)
            self._storage.connect()
        return self._storage

    @property
    def embedder(self) -> EmbeddingProvider:
        """Lazy-load embedding provider."""
        if self._embedder is None:
            self._embedder = get_embedding_provider(self.config)
        return self._embedder

    @property
    def chunker(self) -> Chunker:
        """Lazy-load chunker."""
        if self._chunker is None:
            self._chunker = Chunker()
        return self._chunker

    def index(
        self,
        force: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> IndexStats:
        """
        Run the indexing pipeline.

        Args:
            force: If True, rebuild entire index ignoring existing state
            progress_callback: Optional callback for progress updates (current, total, stage)

        Returns:
            IndexStats with counts of processed files and chunks
        """
        stats = IndexStats()

        # Get changes to process
        new_tree, diff = self._get_changes(force)

        if force:
            # Clear existing chunks on force
            self.storage.clear_all()

        stats.files_scanned = self._count_files(new_tree)
        stats.files_new = len(diff.new)
        stats.files_modified = len(diff.modified)
        stats.files_deleted = len(diff.deleted)

        if not diff.has_changes:
            if self.verbose:
                self.console.print("[green]Index is up to date.[/green]")
            self._update_manifest(new_tree, stats)
            return stats

        # Process changes with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
            disable=not self.verbose,
        ) as progress:
            # Process deleted files
            if diff.deleted:
                task = progress.add_task("Removing deleted files...", total=len(diff.deleted))
                stats.chunks_deleted = self.storage.delete_chunks_by_filepaths(diff.deleted)
                progress.update(task, completed=len(diff.deleted))

            # Process new and modified files
            files_to_process = diff.new + diff.modified
            if files_to_process:
                total_files = len(files_to_process)
                task = progress.add_task("Indexing files...", total=total_files)
                for i, filepath in enumerate(files_to_process):
                    # Report progress before processing each file
                    if progress_callback:
                        progress_callback(i, total_files, "indexing")

                    chunks_added, computed, cached = self._process_file(filepath)
                    stats.chunks_added += chunks_added
                    stats.embeddings_computed += computed
                    stats.embeddings_cached += cached
                    progress.update(task, advance=1)

                # Report completion
                if progress_callback:
                    progress_callback(total_files, total_files, "complete")

        # Update manifest with new tree
        self._update_manifest(new_tree, stats)

        return stats

    def _get_changes(self, force: bool) -> tuple[MerkleTree, TreeDiff]:
        """
        Determine which files need processing.

        Returns:
            Tuple of (new_tree, diff)
        """
        # Load existing tree from manifest first (for mtime optimization)
        manifest = load_manifest(self.project_root)
        old_tree: MerkleTree | None = None
        if manifest is not None and manifest.tree is not None:
            old_tree = MerkleTree.from_dict(manifest.tree)

        # Build current tree from filesystem, using previous tree for mtime caching
        new_tree = MerkleTree.build(
            self.project_root,
            self.config.extensions,
            self.config.exclude_patterns,
            previous_tree=old_tree if not force else None,
        )

        # Log mtime cache stats if verbose
        if self.verbose and new_tree.build_stats:
            stats = new_tree.build_stats
            if stats.total_files > 0:
                self.console.print(
                    f"[dim]Tree build: {stats.files_hashed} hashed, "
                    f"{stats.files_mtime_cached} cached "
                    f"({stats.cache_hit_rate:.0%} hit rate)[/dim]"
                )

        if force or old_tree is None:
            # Treat all files as new
            diff = TreeDiff()
            if new_tree.root:
                from .merkle import _collect_all_files
                _collect_all_files(new_tree.root, diff.new)
            return new_tree, diff

        diff = old_tree.compare(new_tree)
        return new_tree, diff

    def _process_file(self, filepath: str) -> tuple[int, int, int]:
        """
        Process a single file (new or modified).

        Returns:
            Tuple of (chunks_added, embeddings_computed, embeddings_cached)
        """
        abs_path = self.project_root / filepath

        # Read file content
        try:
            content = abs_path.read_text()
        except OSError:
            return 0, 0, 0

        # Compute file hash
        try:
            file_hash = compute_file_hash(abs_path)
        except OSError:
            return 0, 0, 0

        # Delete existing chunks for this file (for modified files)
        self.storage.delete_chunks_by_filepath(filepath)

        # Chunk the file
        chunks = self.chunker.chunk_file(abs_path, content)
        if not chunks:
            return 0, 0, 0

        # Get embeddings with caching
        chunk_vectors, computed, cached = self._embed_chunks_with_cache(chunks)

        # Create CodeChunk objects for storage
        code_chunks = []
        for chunk, vector in chunk_vectors:
            code_chunks.append(CodeChunk(
                id=f"{filepath}:{chunk.start_line}",
                vector=vector,
                text=chunk.text,
                content_hash=chunk.content_hash,
                filepath=filepath,
                filename=abs_path.name,
                extension=abs_path.suffix,
                type=chunk.type,
                name=chunk.name,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                file_hash=file_hash,
            ))

        # Store chunks
        self.storage.upsert_chunks(code_chunks)

        return len(code_chunks), computed, cached

    def _embed_chunks_with_cache(
        self,
        chunks: list[Chunk],
    ) -> tuple[list[tuple[Chunk, list[float]]], int, int]:
        """
        Get embeddings for chunks, using cache where possible.

        Returns:
            Tuple of (list of (chunk, vector) tuples, computed_count, cached_count)
        """
        if not chunks:
            return [], 0, 0

        # Get content hashes
        content_hashes = [chunk.content_hash for chunk in chunks]

        # Check cache
        cached = self.storage.get_cached_embeddings(content_hashes)

        # Separate cached and uncached chunks
        result: list[tuple[Chunk, list[float]]] = []
        to_embed: list[tuple[int, Chunk]] = []  # (index, chunk)

        for i, chunk in enumerate(chunks):
            if chunk.content_hash in cached:
                result.append((chunk, cached[chunk.content_hash]))
            else:
                to_embed.append((i, chunk))

        cached_count = len(chunks) - len(to_embed)
        computed_count = len(to_embed)

        # Embed uncached chunks
        if to_embed:
            texts = [chunk.text for _, chunk in to_embed]
            vectors = self.embedder.embed(texts)

            # Store in cache
            cache_entries = []
            for (_, chunk), vector in zip(to_embed, vectors):
                result.append((chunk, vector))
                cache_entries.append(CachedEmbedding(
                    content_hash=chunk.content_hash,
                    vector=vector,
                    created_at=datetime.now(UTC).isoformat(),
                ))
            self.storage.cache_embeddings(cache_entries)

        # Sort result back to original order
        result.sort(key=lambda x: chunks.index(x[0]))

        return result, computed_count, cached_count

    def _count_files(self, tree: MerkleTree) -> int:
        """Count total files in a Merkle tree."""
        if tree.root is None:
            return 0

        count = 0

        def visit(node):
            nonlocal count
            if node.type == "file":
                count += 1
            else:
                for child in node.children.values():
                    visit(child)

        visit(tree.root)
        return count

    def _update_manifest(self, tree: MerkleTree, stats: IndexStats) -> None:
        """Save updated manifest with new tree and stats."""
        manifest = load_manifest(self.project_root) or create_empty_manifest()
        manifest.tree = tree.to_dict()
        manifest.stats = ManifestStats(
            total_files=stats.files_scanned,
            total_chunks=self.storage.count_chunks(),
        )
        save_manifest(manifest, self.project_root)

    def close(self) -> None:
        """Clean up resources."""
        if self._storage:
            self._storage.close()


def run_index(
    project_root: Path,
    force: bool = False,
    verbose: bool = False,
    console: Console | None = None,
    progress_callback: ProgressCallback | None = None,
) -> IndexStats:
    """
    Run indexing with progress display.

    This is the main entry point called by the CLI.

    Args:
        project_root: Path to the project root
        force: If True, rebuild entire index
        verbose: If True, show detailed progress in terminal
        console: Rich console for output
        progress_callback: Optional callback for progress updates (current, total, stage)
    """
    console = console or Console()
    indexer = Indexer(project_root, verbose=verbose, console=console)

    try:
        stats = indexer.index(force=force, progress_callback=progress_callback)
        return stats
    finally:
        indexer.close()
