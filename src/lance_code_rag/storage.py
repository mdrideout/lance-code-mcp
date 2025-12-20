"""LanceDB storage wrapper for Lance Code RAG."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from . import LANCEDB_DIR, LCR_DIR


@dataclass
class CodeChunk:
    """A code chunk ready for storage."""

    id: str  # Unique ID: "{filepath}:{start_line}"
    vector: list[float]  # Embedding vector
    text: str  # Code content
    content_hash: str  # SHA256 of text (for cache lookup)
    filepath: str  # Relative path to source file
    filename: str  # Just the filename
    extension: str  # File extension (e.g., ".py")
    type: str  # Chunk type: "function", "class", "method", "module"
    name: str  # Symbol name (e.g., function name) or empty
    start_line: int  # 1-indexed start line
    end_line: int  # 1-indexed end line
    file_hash: str  # Hash of source file (for staleness check)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for LanceDB insertion."""
        return {
            "id": self.id,
            "vector": self.vector,
            "text": self.text,
            "content_hash": self.content_hash,
            "filepath": self.filepath,
            "filename": self.filename,
            "extension": self.extension,
            "type": self.type,
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "file_hash": self.file_hash,
        }


@dataclass
class CachedEmbedding:
    """A cached embedding entry."""

    content_hash: str  # SHA256 of chunk text (primary key)
    vector: list[float]  # The embedding
    created_at: str  # ISO timestamp

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for LanceDB insertion."""
        return {
            "content_hash": self.content_hash,
            "vector": self.vector,
            "created_at": self.created_at,
        }


class Storage:
    """LanceDB wrapper for code chunks and embedding cache."""

    CHUNKS_TABLE = "code_chunks"
    CACHE_TABLE = "embedding_cache"

    def __init__(self, project_root: Path, dimensions: int = 768):
        self.project_root = project_root
        self.dimensions = dimensions
        self.db_path = project_root / LCR_DIR / LANCEDB_DIR
        self._db: lancedb.DBConnection | None = None

    def connect(self) -> None:
        """Initialize database connection and create tables if needed."""
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.db_path))

    def close(self) -> None:
        """Close database connection."""
        self._db = None

    @property
    def db(self) -> lancedb.DBConnection:
        """Get the database connection, connecting if needed."""
        if self._db is None:
            self.connect()
        return self._db  # type: ignore

    def _get_chunks_table(self) -> lancedb.table.Table:
        """Get or create the code_chunks table."""
        if self.CHUNKS_TABLE in self.db.list_tables().tables:
            return self.db.open_table(self.CHUNKS_TABLE)

        # Create empty table with schema
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.dimensions)),
            pa.field("text", pa.string()),
            pa.field("content_hash", pa.string()),
            pa.field("filepath", pa.string()),
            pa.field("filename", pa.string()),
            pa.field("extension", pa.string()),
            pa.field("type", pa.string()),
            pa.field("name", pa.string()),
            pa.field("start_line", pa.int32()),
            pa.field("end_line", pa.int32()),
            pa.field("file_hash", pa.string()),
        ])
        return self.db.create_table(self.CHUNKS_TABLE, schema=schema)

    def _get_cache_table(self) -> lancedb.table.Table:
        """Get or create the embedding_cache table."""
        if self.CACHE_TABLE in self.db.list_tables().tables:
            return self.db.open_table(self.CACHE_TABLE)

        # Create empty table with schema
        schema = pa.schema([
            pa.field("content_hash", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.dimensions)),
            pa.field("created_at", pa.string()),
        ])
        return self.db.create_table(self.CACHE_TABLE, schema=schema)

    # Code chunks operations

    def upsert_chunks(self, chunks: list[CodeChunk]) -> None:
        """Insert or update code chunks."""
        if not chunks:
            return

        table = self._get_chunks_table()
        data = [chunk.to_dict() for chunk in chunks]

        # Delete existing chunks with same IDs first
        chunk_ids = [chunk.id for chunk in chunks]
        self._delete_by_ids(table, chunk_ids)

        # Insert new chunks
        table.add(data)

    def _delete_by_ids(self, table: lancedb.table.Table, ids: list[str]) -> None:
        """Delete rows by ID from a table."""
        if not ids:
            return
        # Build filter expression for deletion
        id_list = ", ".join(f"'{id}'" for id in ids)
        table.delete(f"id IN ({id_list})")

    def delete_chunks_by_filepath(self, filepath: str) -> int:
        """Delete all chunks for a given file. Returns count deleted."""
        table = self._get_chunks_table()
        try:
            # Get count before deletion
            before_count = table.count_rows()
            table.delete(f"filepath = '{filepath}'")
            after_count = table.count_rows()
            return before_count - after_count
        except Exception:
            return 0

    def delete_chunks_by_filepaths(self, filepaths: list[str]) -> int:
        """Delete chunks for multiple files. Returns count deleted."""
        if not filepaths:
            return 0

        total_deleted = 0
        for filepath in filepaths:
            total_deleted += self.delete_chunks_by_filepath(filepath)
        return total_deleted

    def get_chunks_by_filepath(self, filepath: str) -> list[dict[str, Any]]:
        """Get all chunks for a file."""
        table = self._get_chunks_table()
        try:
            result = table.search().where(f"filepath = '{filepath}'", prefilter=True).to_list()
            return result
        except Exception:
            return []

    def get_all_filepaths(self) -> set[str]:
        """Get all unique filepaths in the index."""
        table = self._get_chunks_table()
        try:
            arrow_table = table.to_arrow()
            if arrow_table.num_rows == 0:
                return set()
            return set(arrow_table.column("filepath").to_pylist())
        except Exception:
            return set()

    def count_chunks(self) -> int:
        """Count total chunks in the index."""
        try:
            table = self._get_chunks_table()
            return table.count_rows()
        except Exception:
            return 0

    # Embedding cache operations

    def get_cached_embeddings(self, content_hashes: list[str]) -> dict[str, list[float]]:
        """
        Look up cached embeddings by content hash.

        Returns:
            Dict mapping content_hash -> vector for found entries
        """
        if not content_hashes:
            return {}

        table = self._get_cache_table()
        result: dict[str, list[float]] = {}

        try:
            # Query for each hash
            hash_list = ", ".join(f"'{h}'" for h in content_hashes)
            rows = table.search().where(
                f"content_hash IN ({hash_list})", prefilter=True
            ).to_list()

            for row in rows:
                result[row["content_hash"]] = list(row["vector"])
        except Exception:
            pass

        return result

    def cache_embeddings(self, embeddings: list[CachedEmbedding]) -> None:
        """Store embeddings in cache."""
        if not embeddings:
            return

        table = self._get_cache_table()
        data = [emb.to_dict() for emb in embeddings]

        # Delete existing entries with same hashes first
        hashes = [emb.content_hash for emb in embeddings]
        hash_list = ", ".join(f"'{h}'" for h in hashes)
        try:
            table.delete(f"content_hash IN ({hash_list})")
        except Exception:
            pass

        # Insert new entries
        table.add(data)

    def count_cached_embeddings(self) -> int:
        """Count entries in embedding cache."""
        try:
            table = self._get_cache_table()
            return table.count_rows()
        except Exception:
            return 0

    def clear_all(self) -> None:
        """Clear all data from storage. Used for force reindex."""
        try:
            if self.CHUNKS_TABLE in self.db.list_tables().tables:
                self.db.drop_table(self.CHUNKS_TABLE)
            # Note: We keep the cache - it's content-addressed and still valid
        except Exception:
            pass
