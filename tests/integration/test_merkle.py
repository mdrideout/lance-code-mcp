"""Integration tests for Merkle tree change detection.

These tests verify that the Merkle tree correctly:
1. Computes hashes for files and directories
2. Propagates hash changes up the tree when files are modified
3. Detects new, modified, and deleted files via tree comparison
4. Leaves sibling subtrees unchanged when only one branch is modified
"""

import os
import shutil
from pathlib import Path

import pytest

from lance_code_mcp.merkle import (
    MerkleNode,
    MerkleTree,
    TreeDiff,
    compute_file_hash,
    compute_directory_hash,
    is_binary_file,
    should_exclude,
)


class TestMerkleTreeStructure:
    """Tests for building and traversing Merkle trees."""

    @pytest.fixture
    def tree_fixture(self, tmp_path: Path) -> Path:
        """
        Create a test directory structure for Merkle tree testing.

        Structure:
            merkle_test/
            ├── root_file.py
            ├── level1/
            │   ├── file1.py
            │   └── level2/
            │       ├── file2.py
            │       └── level3/
            │           └── file3.py
            ├── sibling/
            │   ├── sibling1.py
            │   └── sibling2.py
            └── excluded/
                └── ignored.py  (in node_modules-like dir)
        """
        root = tmp_path / "merkle_test"
        root.mkdir()

        # Root level file
        (root / "root_file.py").write_text("# Root level\ndef root_func(): pass\n")

        # Nested structure (3 levels deep)
        level1 = root / "level1"
        level1.mkdir()
        (level1 / "file1.py").write_text("# Level 1\ndef level1_func(): pass\n")

        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "file2.py").write_text("# Level 2\ndef level2_func(): pass\n")

        level3 = level2 / "level3"
        level3.mkdir()
        (level3 / "file3.py").write_text("# Level 3\ndef level3_func(): pass\n")

        # Sibling directory (should not be affected by changes in level1)
        sibling = root / "sibling"
        sibling.mkdir()
        (sibling / "sibling1.py").write_text("# Sibling 1\ndef sib1(): pass\n")
        (sibling / "sibling2.py").write_text("# Sibling 2\ndef sib2(): pass\n")

        # Excluded directory (simulates node_modules)
        excluded = root / "node_modules"
        excluded.mkdir()
        (excluded / "ignored.py").write_text("# Should be ignored\n")

        return root

    def test_build_tree_structure(self, tree_fixture: Path):
        """Verify tree structure matches directory structure."""
        tree = MerkleTree.build(
            tree_fixture,
            extensions=[".py"],
            exclude_patterns=["node_modules", "__pycache__"],
        )

        assert tree.root is not None
        assert tree.root.type == "directory"
        assert tree.root.path == "."

        # Check root has expected children
        children = tree.root.children
        assert "root_file.py" in children
        assert "level1" in children
        assert "sibling" in children
        assert "node_modules" not in children  # Excluded

        # Check nested structure
        level1 = children["level1"]
        assert level1.type == "directory"
        assert "file1.py" in level1.children
        assert "level2" in level1.children

        level2 = level1.children["level2"]
        assert "file2.py" in level2.children
        assert "level3" in level2.children

        level3 = level2.children["level3"]
        assert "file3.py" in level3.children

    def test_file_hashes_are_deterministic(self, tree_fixture: Path):
        """Same file content produces same hash."""
        tree1 = MerkleTree.build(tree_fixture, extensions=[".py"], exclude_patterns=[])
        tree2 = MerkleTree.build(tree_fixture, extensions=[".py"], exclude_patterns=[])

        assert tree1.root.hash == tree2.root.hash

    def test_directory_hash_depends_on_children(self, tree_fixture: Path):
        """Directory hash is computed from children's names and hashes."""
        tree = MerkleTree.build(
            tree_fixture,
            extensions=[".py"],
            exclude_patterns=["node_modules"],
        )

        # Get level1 directory and manually compute expected hash
        level1 = tree.root.children["level1"]
        expected_hash = compute_directory_hash(level1.children)
        assert level1.hash == expected_hash


class TestMerkleTreeHashPropagation:
    """Tests for hash propagation when files change."""

    @pytest.fixture
    def tree_fixture(self, tmp_path: Path) -> Path:
        """Create the same fixture structure."""
        root = tmp_path / "merkle_test"
        root.mkdir()

        (root / "root_file.py").write_text("# Root level\ndef root_func(): pass\n")

        level1 = root / "level1"
        level1.mkdir()
        (level1 / "file1.py").write_text("# Level 1\ndef level1_func(): pass\n")

        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "file2.py").write_text("# Level 2\ndef level2_func(): pass\n")

        level3 = level2 / "level3"
        level3.mkdir()
        (level3 / "file3.py").write_text("# Level 3\ndef level3_func(): pass\n")

        sibling = root / "sibling"
        sibling.mkdir()
        (sibling / "sibling1.py").write_text("# Sibling 1\ndef sib1(): pass\n")
        (sibling / "sibling2.py").write_text("# Sibling 2\ndef sib2(): pass\n")

        return root

    def _build_tree(self, root: Path) -> MerkleTree:
        """Helper to build tree with standard config."""
        return MerkleTree.build(root, extensions=[".py"], exclude_patterns=[])

    def _get_all_hashes(self, tree: MerkleTree) -> dict[str, str]:
        """Extract all node hashes from tree."""
        hashes = {}

        def visit(node: MerkleNode):
            hashes[node.path] = node.hash
            for child in node.children.values():
                visit(child)

        if tree.root:
            visit(tree.root)
        return hashes

    def test_root_file_change_only_affects_root(self, tree_fixture: Path):
        """Changing root file changes root hash but not sibling subtrees."""
        # Build initial tree
        tree_before = self._build_tree(tree_fixture)
        hashes_before = self._get_all_hashes(tree_before)

        # Modify root file
        root_file = tree_fixture / "root_file.py"
        root_file.write_text("# MODIFIED ROOT\ndef root_func(): return 42\n")

        # Build new tree
        tree_after = self._build_tree(tree_fixture)
        hashes_after = self._get_all_hashes(tree_after)

        # Root hash changed
        assert hashes_after["."] != hashes_before["."]

        # Root file hash changed
        assert hashes_after["root_file.py"] != hashes_before["root_file.py"]

        # Sibling directory unchanged
        assert hashes_after["sibling"] == hashes_before["sibling"]
        assert hashes_after["sibling/sibling1.py"] == hashes_before["sibling/sibling1.py"]

        # Nested directories unchanged
        assert hashes_after["level1"] == hashes_before["level1"]
        assert hashes_after["level1/level2"] == hashes_before["level1/level2"]

    def test_level1_file_change_propagates_up(self, tree_fixture: Path):
        """Changing level1 file affects level1 and root, not siblings."""
        tree_before = self._build_tree(tree_fixture)
        hashes_before = self._get_all_hashes(tree_before)

        # Modify level1 file
        (tree_fixture / "level1" / "file1.py").write_text("# MODIFIED L1\n")

        tree_after = self._build_tree(tree_fixture)
        hashes_after = self._get_all_hashes(tree_after)

        # Changed: file1.py, level1, root
        assert hashes_after["level1/file1.py"] != hashes_before["level1/file1.py"]
        assert hashes_after["level1"] != hashes_before["level1"]
        assert hashes_after["."] != hashes_before["."]

        # Unchanged: sibling subtree
        assert hashes_after["sibling"] == hashes_before["sibling"]

        # Unchanged: level2/level3 (deeper than the change)
        assert hashes_after["level1/level2"] == hashes_before["level1/level2"]
        assert hashes_after["level1/level2/level3"] == hashes_before["level1/level2/level3"]

    def test_level3_file_change_propagates_all_way_up(self, tree_fixture: Path):
        """Changing deeply nested file affects all ancestors."""
        tree_before = self._build_tree(tree_fixture)
        hashes_before = self._get_all_hashes(tree_before)

        # Modify deepest file
        (tree_fixture / "level1" / "level2" / "level3" / "file3.py").write_text("# MODIFIED L3\n")

        tree_after = self._build_tree(tree_fixture)
        hashes_after = self._get_all_hashes(tree_after)

        # Changed: file3.py, level3, level2, level1, root
        assert hashes_after["level1/level2/level3/file3.py"] != hashes_before["level1/level2/level3/file3.py"]
        assert hashes_after["level1/level2/level3"] != hashes_before["level1/level2/level3"]
        assert hashes_after["level1/level2"] != hashes_before["level1/level2"]
        assert hashes_after["level1"] != hashes_before["level1"]
        assert hashes_after["."] != hashes_before["."]

        # Unchanged: sibling subtree (completely separate branch)
        assert hashes_after["sibling"] == hashes_before["sibling"]
        assert hashes_after["sibling/sibling1.py"] == hashes_before["sibling/sibling1.py"]
        assert hashes_after["sibling/sibling2.py"] == hashes_before["sibling/sibling2.py"]

        # Unchanged: root_file.py (same level as level1 but different branch)
        assert hashes_after["root_file.py"] == hashes_before["root_file.py"]

    def test_sibling_change_does_not_affect_level_branch(self, tree_fixture: Path):
        """Changes in sibling directory don't affect level1 branch."""
        tree_before = self._build_tree(tree_fixture)
        hashes_before = self._get_all_hashes(tree_before)

        # Modify sibling file
        (tree_fixture / "sibling" / "sibling1.py").write_text("# MODIFIED SIBLING\n")

        tree_after = self._build_tree(tree_fixture)
        hashes_after = self._get_all_hashes(tree_after)

        # Changed: sibling1.py, sibling, root
        assert hashes_after["sibling/sibling1.py"] != hashes_before["sibling/sibling1.py"]
        assert hashes_after["sibling"] != hashes_before["sibling"]
        assert hashes_after["."] != hashes_before["."]

        # Unchanged: entire level1 branch
        assert hashes_after["level1"] == hashes_before["level1"]
        assert hashes_after["level1/file1.py"] == hashes_before["level1/file1.py"]
        assert hashes_after["level1/level2"] == hashes_before["level1/level2"]
        assert hashes_after["level1/level2/level3"] == hashes_before["level1/level2/level3"]


class TestMerkleTreeComparison:
    """Tests for tree comparison (diff) functionality."""

    @pytest.fixture
    def tree_fixture(self, tmp_path: Path) -> Path:
        """Create fixture structure."""
        root = tmp_path / "merkle_test"
        root.mkdir()

        (root / "existing.py").write_text("# Existing file\n")

        subdir = root / "subdir"
        subdir.mkdir()
        (subdir / "nested.py").write_text("# Nested file\n")

        return root

    def _build_tree(self, root: Path) -> MerkleTree:
        return MerkleTree.build(root, extensions=[".py"], exclude_patterns=[])

    def test_no_changes_empty_diff(self, tree_fixture: Path):
        """Identical trees produce empty diff."""
        tree1 = self._build_tree(tree_fixture)
        tree2 = self._build_tree(tree_fixture)

        diff = tree1.compare(tree2)

        assert diff.new == []
        assert diff.modified == []
        assert diff.deleted == []
        assert not diff.has_changes

    def test_detect_new_file(self, tree_fixture: Path):
        """New file is detected in diff."""
        tree_before = self._build_tree(tree_fixture)

        # Add new file
        (tree_fixture / "new_file.py").write_text("# New file\n")

        tree_after = self._build_tree(tree_fixture)
        diff = tree_before.compare(tree_after)

        assert "new_file.py" in diff.new
        assert diff.modified == []
        assert diff.deleted == []
        assert diff.has_changes

    def test_detect_new_nested_file(self, tree_fixture: Path):
        """New nested file is detected."""
        tree_before = self._build_tree(tree_fixture)

        # Add new nested file
        (tree_fixture / "subdir" / "new_nested.py").write_text("# New nested\n")

        tree_after = self._build_tree(tree_fixture)
        diff = tree_before.compare(tree_after)

        assert "subdir/new_nested.py" in diff.new
        assert diff.has_changes

    def test_detect_new_directory_with_files(self, tree_fixture: Path):
        """New directory with files detected."""
        tree_before = self._build_tree(tree_fixture)

        # Add new directory with files
        new_dir = tree_fixture / "new_dir"
        new_dir.mkdir()
        (new_dir / "file_a.py").write_text("# File A\n")
        (new_dir / "file_b.py").write_text("# File B\n")

        tree_after = self._build_tree(tree_fixture)
        diff = tree_before.compare(tree_after)

        assert "new_dir/file_a.py" in diff.new
        assert "new_dir/file_b.py" in diff.new
        assert len(diff.new) == 2

    def test_detect_modified_file(self, tree_fixture: Path):
        """Modified file is detected."""
        tree_before = self._build_tree(tree_fixture)

        # Modify existing file
        (tree_fixture / "existing.py").write_text("# MODIFIED content\n")

        tree_after = self._build_tree(tree_fixture)
        diff = tree_before.compare(tree_after)

        assert "existing.py" in diff.modified
        assert diff.new == []
        assert diff.deleted == []

    def test_detect_modified_nested_file(self, tree_fixture: Path):
        """Modified nested file is detected."""
        tree_before = self._build_tree(tree_fixture)

        # Modify nested file
        (tree_fixture / "subdir" / "nested.py").write_text("# MODIFIED nested\n")

        tree_after = self._build_tree(tree_fixture)
        diff = tree_before.compare(tree_after)

        assert "subdir/nested.py" in diff.modified

    def test_detect_deleted_file(self, tree_fixture: Path):
        """Deleted file is detected."""
        tree_before = self._build_tree(tree_fixture)

        # Delete file
        (tree_fixture / "existing.py").unlink()

        tree_after = self._build_tree(tree_fixture)
        diff = tree_before.compare(tree_after)

        assert "existing.py" in diff.deleted
        assert diff.new == []
        assert diff.modified == []

    def test_detect_deleted_directory(self, tree_fixture: Path):
        """Deleted directory and its files are detected."""
        tree_before = self._build_tree(tree_fixture)

        # Delete directory
        shutil.rmtree(tree_fixture / "subdir")

        tree_after = self._build_tree(tree_fixture)
        diff = tree_before.compare(tree_after)

        assert "subdir/nested.py" in diff.deleted

    def test_detect_multiple_changes(self, tree_fixture: Path):
        """Multiple simultaneous changes are all detected."""
        tree_before = self._build_tree(tree_fixture)

        # Add new file
        (tree_fixture / "new.py").write_text("# New\n")
        # Modify existing
        (tree_fixture / "existing.py").write_text("# Modified\n")
        # Delete nested
        (tree_fixture / "subdir" / "nested.py").unlink()

        tree_after = self._build_tree(tree_fixture)
        diff = tree_before.compare(tree_after)

        assert "new.py" in diff.new
        assert "existing.py" in diff.modified
        assert "subdir/nested.py" in diff.deleted
        assert diff.total_changes == 3


class TestMerkleTreeSerialization:
    """Tests for tree serialization/deserialization."""

    @pytest.fixture
    def tree_fixture(self, tmp_path: Path) -> Path:
        root = tmp_path / "merkle_test"
        root.mkdir()
        (root / "file.py").write_text("# Test\n")
        subdir = root / "subdir"
        subdir.mkdir()
        (subdir / "nested.py").write_text("# Nested\n")
        return root

    def test_roundtrip_serialization(self, tree_fixture: Path):
        """Tree survives serialization roundtrip."""
        tree = MerkleTree.build(tree_fixture, extensions=[".py"], exclude_patterns=[])

        # Serialize
        data = tree.to_dict()
        assert data is not None

        # Deserialize
        tree2 = MerkleTree.from_dict(data)

        # Compare
        assert tree2.root is not None
        assert tree2.root.hash == tree.root.hash
        assert tree2.root.children.keys() == tree.root.children.keys()

    def test_empty_tree_serialization(self):
        """Empty tree serializes correctly."""
        tree = MerkleTree(root=None)
        data = tree.to_dict()
        assert data is None

        tree2 = MerkleTree.from_dict(None)
        assert tree2.root is None


class TestMerkleUtilities:
    """Tests for utility functions."""

    def test_compute_file_hash_deterministic(self, tmp_path: Path):
        """Same content produces same hash."""
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        content = "def hello(): pass\n"

        file1.write_text(content)
        file2.write_text(content)

        assert compute_file_hash(file1) == compute_file_hash(file2)

    def test_compute_file_hash_different_content(self, tmp_path: Path):
        """Different content produces different hash."""
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"

        file1.write_text("def hello(): pass\n")
        file2.write_text("def goodbye(): pass\n")

        assert compute_file_hash(file1) != compute_file_hash(file2)

    def test_is_binary_file_with_nulls(self, tmp_path: Path):
        """Binary files are detected."""
        binary = tmp_path / "binary.bin"
        binary.write_bytes(b"\x00\x01\x02\x03")

        assert is_binary_file(binary) is True

    def test_is_binary_file_text(self, tmp_path: Path):
        """Text files are not flagged as binary."""
        text = tmp_path / "text.py"
        text.write_text("# Python code\ndef func(): pass\n")

        assert is_binary_file(text) is False

    def test_should_exclude_patterns(self, tmp_path: Path):
        """Exclusion patterns work correctly."""
        patterns = ["node_modules", "__pycache__", "*.pyc"]

        assert should_exclude(tmp_path / "node_modules", patterns) is True
        assert should_exclude(tmp_path / "__pycache__", patterns) is True
        assert should_exclude(tmp_path / "test.pyc", patterns) is True
        assert should_exclude(tmp_path / "src", patterns) is False
        assert should_exclude(tmp_path / "test.py", patterns) is False
