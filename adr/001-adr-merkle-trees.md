# ADR-001: Content-Addressed Merkle Trees for Change Detection

## Status

Accepted

## Context

Lance Code MCP indexes codebases to enable semantic code search. The indexing pipeline must:

1. **Detect changes efficiently** - Avoid re-indexing unchanged files
2. **Handle incremental updates** - Process only what changed since last index
3. **Track file state persistently** - Know what was indexed without rescanning everything
4. **Scale to large codebases** - Support repositories with thousands of files

A naive approach of storing file hashes in a flat list has O(n) comparison time and doesn't capture the hierarchical structure of codebases. We need a data structure that:

- Detects changes at any level of the directory hierarchy
- Enables fast comparison between index states
- Serializes efficiently to the manifest file

## Decision

We use a **content-addressed Merkle tree** that mirrors the project's directory structure.

### Structure

```
MerkleNode:
  hash: str           # SHA256 content hash
  type: file | directory
  path: str           # Relative path from project root
  children: dict      # For directories: {name -> child node}
  size: int           # For files: byte size
  mtime: float        # For files: modification time
```

### Hash Computation

- **File nodes**: `hash = SHA256(file_content)`
- **Directory nodes**: `hash = SHA256(sorted([name + child.hash for children]))`

This creates a deterministic, bottom-up hash propagation where any change to a file automatically invalidates all ancestor directory hashes up to the root.

### Change Detection

Comparing two trees (old vs new) uses the following algorithm:

1. If root hashes match, the entire tree is unchanged (O(1) short-circuit)
2. Otherwise, recursively compare children:
   - Child in new but not old → **new files**
   - Child in old but not new → **deleted files**
   - Child in both with different hash → recurse or mark **modified**

### mtime Optimization

To avoid hashing file contents on every scan, we cache the previous tree and check:

```python
if file.mtime == previous.mtime and file.size == previous.size:
    reuse previous.hash  # Skip content hashing
else:
    compute new hash from content
```

This reduces typical incremental scans from O(total_bytes) to O(number_of_files) for unchanged repositories.

## Rationale

### Why Merkle Trees?

1. **Hierarchical change propagation** - A single file change produces a new root hash, making it trivial to detect "anything changed" in O(1) time.

2. **Structural comparison** - The tree structure naturally maps to filesystem hierarchies, making diff computation intuitive and efficient.

3. **Partial tree comparison** - When hashes match at any node, the entire subtree is unchanged, enabling pruning during comparison.

4. **Deterministic state** - The root hash uniquely identifies the complete indexed state, useful for debugging and verification.

### Why Not Merkle Search Trees (MSTs)?

Merkle Search Trees (B-tree variants with Merkle hashing) are designed for **distributed systems** where:

- Multiple replicas need to synchronize
- Set reconciliation must be efficient across network boundaries
- Order-preserving key traversal is required

Our use case is fundamentally **single-machine, single-writer**:

- One indexer processes one project
- No distributed consensus or sync required
- We compare "before" vs "after" states, not remote replicas

MSTs would add complexity (balancing, key ordering) without providing benefits for our architecture.

## Consequences

### Enables

- **Fast incremental indexing** - Only modified files are re-processed
- **Reliable change detection** - Content-based hashing catches all changes, even if mtime is unreliable
- **Efficient manifest storage** - Tree serializes to JSON in the manifest file
- **Simple diffing** - Three-way classification (new/modified/deleted) falls out naturally

### Requires

- **Full tree in memory** - The tree must fit in memory during comparison (acceptable for code repositories)
- **Manifest persistence** - The previous tree must be loaded from disk on each run
- **Initial full scan** - First index must hash all files (subsequent runs benefit from caching)

### Trade-offs

- We store mtime/size per file, increasing manifest size slightly
- The mtime optimization assumes filesystem timestamps are reliable (true on modern systems)
- Binary files are detected and skipped, not hashed

## References

- [Merkle Tree (Wikipedia)](https://en.wikipedia.org/wiki/Merkle_tree)
- [Git's use of SHA-1 trees](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)
- Implementation: `src/lance_code_mcp/merkle.py`
