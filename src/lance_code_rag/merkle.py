"""Merkle tree implementation for change detection in Lance Code RAG."""

from __future__ import annotations

import fnmatch
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class TreeBuildStats:
    """Statistics from building a Merkle tree."""

    files_hashed: int = 0  # Files where content was read and hashed
    files_mtime_cached: int = 0  # Files where hash was reused due to mtime match
    directories_processed: int = 0

    @property
    def total_files(self) -> int:
        return self.files_hashed + self.files_mtime_cached

    @property
    def cache_hit_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return self.files_mtime_cached / self.total_files


@dataclass
class MerkleNode:
    """A node in the Merkle tree representing a file or directory."""

    hash: str
    type: Literal["file", "directory"]
    path: str  # Relative path from project root
    children: dict[str, MerkleNode] = field(default_factory=dict)
    size: int | None = None  # For files only
    mtime: float | None = None  # For files only

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage in manifest."""
        result: dict[str, Any] = {
            "hash": self.hash,
            "type": self.type,
            "path": self.path,
        }
        if self.type == "file":
            result["size"] = self.size
            result["mtime"] = self.mtime
        else:
            result["children"] = {
                name: child.to_dict() for name, child in self.children.items()
            }
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MerkleNode:
        """Deserialize from dictionary."""
        children = {}
        if data.get("type") == "directory" and "children" in data:
            children = {
                name: cls.from_dict(child_data)
                for name, child_data in data["children"].items()
            }
        return cls(
            hash=data["hash"],
            type=data["type"],
            path=data["path"],
            children=children,
            size=data.get("size"),
            mtime=data.get("mtime"),
        )


@dataclass
class TreeDiff:
    """Result of comparing two Merkle trees."""

    new: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.new or self.modified or self.deleted)

    @property
    def total_changes(self) -> int:
        """Total number of changed files."""
        return len(self.new) + len(self.modified) + len(self.deleted)


class MerkleTree:
    """Content-addressed tree mirroring directory structure."""

    def __init__(self, root: MerkleNode | None = None):
        self.root = root
        self.build_stats: TreeBuildStats | None = None

    @classmethod
    def build(
        cls,
        project_root: Path,
        extensions: list[str],
        exclude_patterns: list[str],
        previous_tree: MerkleTree | None = None,
    ) -> MerkleTree:
        """
        Build a Merkle tree from the filesystem.

        Args:
            project_root: Root directory to scan
            extensions: File extensions to include (e.g., [".py", ".js"])
            exclude_patterns: Directory/file patterns to exclude
            previous_tree: Optional previous tree for mtime-based hash caching

        Returns:
            A MerkleTree instance with computed hashes
        """
        # Build lookup table from previous tree for O(1) path lookups
        previous_nodes: dict[str, MerkleNode] = {}
        if previous_tree and previous_tree.root:
            _build_path_lookup(previous_tree.root, previous_nodes)

        stats = TreeBuildStats()
        root_node = _build_node(
            path=project_root,
            project_root=project_root,
            extensions=extensions,
            exclude_patterns=exclude_patterns,
            previous_nodes=previous_nodes,
            stats=stats,
        )

        tree = cls(root=root_node)
        tree.build_stats = stats
        return tree

    def compare(self, other: MerkleTree) -> TreeDiff:
        """
        Compare this tree (old) with another tree (new) to find changes.

        Args:
            other: The newer tree (typically current filesystem state)

        Returns:
            TreeDiff with lists of new, modified, and deleted file paths
        """
        diff = TreeDiff()

        if self.root is None and other.root is None:
            return diff

        if self.root is None:
            # Everything in other is new
            _collect_all_files(other.root, diff.new)
            return diff

        if other.root is None:
            # Everything in self is deleted
            _collect_all_files(self.root, diff.deleted)
            return diff

        # Both trees exist - compare them
        _compare_nodes(self.root, other.root, diff)
        return diff

    def to_dict(self) -> dict[str, Any] | None:
        """Serialize tree to dictionary for manifest storage."""
        if self.root is None:
            return None
        return self.root.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MerkleTree:
        """Deserialize tree from manifest dictionary."""
        if data is None:
            return cls(root=None)
        return cls(root=MerkleNode.from_dict(data))


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of file contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_directory_hash(children: dict[str, MerkleNode]) -> str:
    """Compute directory hash from sorted child name+hash pairs."""
    h = hashlib.sha256()
    for name in sorted(children.keys()):
        h.update(f"{name}{children[name].hash}".encode())
    return h.hexdigest()


def is_binary_file(filepath: Path) -> bool:
    """Detect binary files by checking for null bytes in first 8KB."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except OSError:
        return True  # Treat unreadable files as binary


def should_exclude(path: Path, exclude_patterns: list[str]) -> bool:
    """Check if path matches any exclusion pattern."""
    name = path.name
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _build_path_lookup(node: MerkleNode, lookup: dict[str, MerkleNode]) -> None:
    """Build a flat lookup table of path -> node from a tree."""
    lookup[node.path] = node
    for child in node.children.values():
        _build_path_lookup(child, lookup)


def _build_node(
    path: Path,
    project_root: Path,
    extensions: list[str],
    exclude_patterns: list[str],
    previous_nodes: dict[str, MerkleNode],
    stats: TreeBuildStats,
) -> MerkleNode | None:
    """Recursively build a node for a file or directory."""
    if should_exclude(path, exclude_patterns):
        return None

    if path.is_symlink():
        return None

    relative_path = str(path.relative_to(project_root))

    if path.is_file():
        # Check extension
        if extensions and path.suffix not in extensions:
            return None

        # Skip binary files
        if is_binary_file(path):
            return None

        try:
            stat = path.stat()
            current_mtime = stat.st_mtime
            current_size = stat.st_size

            # mtime optimization: reuse hash if mtime and size unchanged
            previous = previous_nodes.get(relative_path)
            if (
                previous is not None
                and previous.type == "file"
                and previous.mtime == current_mtime
                and previous.size == current_size
            ):
                # mtime and size match - reuse cached hash
                stats.files_mtime_cached += 1
                file_hash = previous.hash
            else:
                # mtime or size changed - compute new hash
                stats.files_hashed += 1
                file_hash = compute_file_hash(path)

            return MerkleNode(
                hash=file_hash,
                type="file",
                path=relative_path,
                size=current_size,
                mtime=current_mtime,
            )
        except OSError:
            return None

    elif path.is_dir():
        stats.directories_processed += 1
        children: dict[str, MerkleNode] = {}
        try:
            for child in sorted(path.iterdir()):
                child_node = _build_node(
                    child, project_root, extensions, exclude_patterns,
                    previous_nodes, stats,
                )
                if child_node is not None:
                    children[child.name] = child_node
        except PermissionError:
            return None

        if not children:
            return None  # Skip empty directories

        dir_hash = compute_directory_hash(children)
        return MerkleNode(
            hash=dir_hash,
            type="directory",
            path=relative_path,
            children=children,
        )

    return None


def _collect_all_files(node: MerkleNode | None, file_list: list[str]) -> None:
    """Collect all file paths from a node recursively."""
    if node is None:
        return

    if node.type == "file":
        file_list.append(node.path)
    else:
        for child in node.children.values():
            _collect_all_files(child, file_list)


def _compare_nodes(old_node: MerkleNode, new_node: MerkleNode, diff: TreeDiff) -> None:
    """Recursively compare two nodes and populate diff."""
    # Quick check: if hashes match, entire subtree is unchanged
    if old_node.hash == new_node.hash:
        return

    # For files, a hash difference means modification
    if old_node.type == "file" and new_node.type == "file":
        diff.modified.append(new_node.path)
        return

    # For directories (or type changes), compare children
    old_children = old_node.children if old_node.type == "directory" else {}
    new_children = new_node.children if new_node.type == "directory" else {}

    # Handle type changes (file -> dir or dir -> file)
    if old_node.type != new_node.type:
        _collect_all_files(old_node, diff.deleted)
        _collect_all_files(new_node, diff.new)
        return

    old_names = set(old_children.keys())
    new_names = set(new_children.keys())

    # New entries
    for name in new_names - old_names:
        _collect_all_files(new_children[name], diff.new)

    # Deleted entries
    for name in old_names - new_names:
        _collect_all_files(old_children[name], diff.deleted)

    # Entries in both - recurse
    for name in old_names & new_names:
        _compare_nodes(old_children[name], new_children[name], diff)
